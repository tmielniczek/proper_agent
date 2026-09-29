import asyncio
import json
from dataclasses import dataclass
from uuid import uuid4

from fastapi.sse import ServerSentEvent
from opentelemetry.trace import (
    Span,
    SpanKind,
    Status,
    StatusCode,
    Tracer,
    set_span_in_context,
)

from app.llm import LanguageModel, ModelUsage, ProviderRejection, ToolCall, configured_model_name
from app.screen import TurnSpend
from app.tools import (
    DISPLAY_TEXT,
    SPAWN_WORKERS,
    TOOL_SCHEMAS,
    asking_label,
    refused_label,
    run_tool,
    worker_tool_label,
)

WORKER_INSTRUCTIONS = (
    "Answer the task. Use get_weather, search_database, and calculator when you need them. "
    "Your final message is the whole result."
)


@dataclass(frozen=True)
class _Slot:
    task: str
    error: str | None


@dataclass(frozen=True)
class _Plan:
    slots: list[_Slot]
    refused: list[str]


def _plan(raw: object) -> _Plan | str:
    if not isinstance(raw, list):
        return "Spawn needs a list of tasks."
    if len(raw) == 0:
        return "Spawn needs at least one task."
    return _Plan([_slot(item) for item in raw[:5]], [_refused_text(item) for item in raw[5:]])


def _slot(item: object) -> _Slot:
    if not isinstance(item, str):
        return _Slot("", "Task must be text.")
    if item.strip() == "":
        return _Slot(item, "Task is blank.")
    return _Slot(item, None)


def _refused_text(item: object) -> str:
    if isinstance(item, str):
        return item
    return ""


def _mark_spawn_ok(span: Span, *, refused_tasks: int) -> None:
    span.set_attribute("gen_ai.operation.name", "execute_tool")
    span.set_attribute("gen_ai.tool.name", SPAWN_WORKERS)
    span.set_attribute("app.refused_tasks", refused_tasks)
    span.set_attribute("app.status", "ok")
    span.set_status(Status(StatusCode.OK))


def _mark_spawn_error(span: Span) -> None:
    span.set_attribute("gen_ai.operation.name", "execute_tool")
    span.set_attribute("gen_ai.tool.name", SPAWN_WORKERS)
    span.set_attribute("app.status", "error")
    span.set_attribute("error.type", "error")
    span.set_attribute("app.refused_tasks", 0)
    span.set_status(Status(StatusCode.ERROR))


def _mark_worker_chat_ok(
    span: Span, *, model: str, usage: ModelUsage | None
) -> None:
    span.set_attribute("gen_ai.operation.name", "chat")
    span.set_attribute("gen_ai.provider.name", "openai")
    span.set_attribute("gen_ai.request.model", model)
    span.set_attribute("app.caller", "worker")
    span.set_attribute("app.status", "ok")
    span.set_status(Status(StatusCode.OK))
    if usage is None:
        return
    if usage.input_tokens is not None:
        span.set_attribute("gen_ai.usage.input_tokens", usage.input_tokens)
    if usage.output_tokens is not None:
        span.set_attribute("gen_ai.usage.output_tokens", usage.output_tokens)


async def run_spawn(
    raw: object,
    model: LanguageModel,
    queue: asyncio.Queue,
    spend: TurnSpend,
    *,
    tracer: Tracer,
    spawn_span: Span,
) -> dict:
    plan = _plan(raw)
    if isinstance(plan, str):
        _mark_spawn_error(spawn_span)
        return {"error": plan}
    started = sum(slot.error is None for slot in plan.slots)
    queue.put_nowait(
        ServerSentEvent(
            event="tool_start",
            data={"tool": SPAWN_WORKERS, "display_text": asking_label(started)},
        )
    )
    for task in plan.refused:
        queue.put_nowait(
            ServerSentEvent(event="refused_task", data={"display_text": refused_label(task)})
        )
    results = await asyncio.gather(
        *(_slot_result(slot, model, queue, spend, tracer=tracer, spawn_span=spawn_span) for slot in plan.slots)
    )
    queue.put_nowait(ServerSentEvent(event="tool_end", data={"tool": SPAWN_WORKERS}))
    _mark_spawn_ok(spawn_span, refused_tasks=len(plan.refused))
    return {"workers": list(results), "refused": plan.refused}


async def _slot_result(
    slot: _Slot,
    model: LanguageModel,
    queue: asyncio.Queue,
    spend: TurnSpend,
    *,
    tracer: Tracer,
    spawn_span: Span,
) -> dict:
    if slot.error is not None:
        return {"task": slot.task, "error": slot.error}
    try:
        return await _run_worker(
            slot.task, model, queue, spend, tracer=tracer, spawn_span=spawn_span
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return {"task": slot.task, "error": str(exc)}


async def _run_worker(
    task: str,
    model: LanguageModel,
    queue: asyncio.Queue,
    spend: TurnSpend,
    *,
    tracer: Tracer,
    spawn_span: Span,
) -> dict:
    turns: list[dict] = [
        {"role": "system", "content": WORKER_INSTRUCTIONS},
        {"role": "user", "content": task},
    ]
    try:
        while True:
            reason = await spend.claim_call()
            if reason is not None:
                return {"task": task, "error": reason}
            parts: list[str] = []
            tool_calls: list[ToolCall] = []
            usage: ModelUsage | None = None
            model_name = configured_model_name()
            parent_ctx = set_span_in_context(spawn_span)
            with tracer.start_as_current_span(
                f"chat {model_name}",
                context=parent_ctx,
                kind=SpanKind.INTERNAL,
            ) as chat_span:
                async for event in model.stream(turns, TOOL_SCHEMAS):
                    if isinstance(event, ModelUsage):
                        usage = event
                        await spend.record(event.total_tokens)
                        continue
                    if isinstance(event, ToolCall):
                        tool_calls.append(event)
                        continue
                    parts.append(event)
                _mark_worker_chat_ok(chat_span, model=model_name, usage=usage)
            if not tool_calls:
                return {"task": task, "text": "".join(parts)}
            turns.append(_assistant_turn("".join(parts), tool_calls))
            for call in tool_calls:
                blocked = _blocked_tool(call)
                if blocked is not None:
                    return {"task": task, "error": blocked}
                failure = await _run_worker_tool(
                    task, call, turns, queue, tracer=tracer, chat_span=chat_span
                )
                if failure is not None:
                    return failure
    except asyncio.CancelledError:
        raise
    except ProviderRejection as rejection:
        return {"task": task, "error": str(rejection)}


def _blocked_tool(call: ToolCall) -> str | None:
    if call.name == SPAWN_WORKERS:
        return "Workers cannot start workers."
    if call.name not in DISPLAY_TEXT:
        return f"Unknown tool: {call.name}"
    return None


async def _run_worker_tool(
    task: str,
    call: ToolCall,
    turns: list[dict],
    queue: asyncio.Queue,
    *,
    tracer: Tracer,
    chat_span: Span,
) -> dict | None:
    call_id = str(uuid4())
    queue.put_nowait(
        ServerSentEvent(
            event="tool_start",
            data={
                "tool": call.name,
                "display_text": worker_tool_label(call.name, task),
                "call_id": call_id,
            },
        )
    )
    try:
        parent_ctx = set_span_in_context(chat_span)
        with tracer.start_as_current_span(
            f"execute_tool {call.name}",
            context=parent_ctx,
            kind=SpanKind.INTERNAL,
        ) as tool_span:
            result = await run_tool(call.name, call.arguments)
            tool_span.set_attribute("gen_ai.operation.name", "execute_tool")
            tool_span.set_attribute("gen_ai.tool.name", call.name)
            tool_span.set_attribute("app.status", "ok")
            tool_span.set_status(Status(StatusCode.OK))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        queue.put_nowait(
            ServerSentEvent(event="tool_end", data={"tool": call.name, "call_id": call_id})
        )
        return {"task": task, "error": str(exc)}
    queue.put_nowait(ServerSentEvent(event="tool_end", data={"tool": call.name, "call_id": call_id}))
    turns.append(
        {"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)}
    )
    return None


def _assistant_turn(content: str, tool_calls: list[ToolCall]) -> dict:
    return {
        "role": "assistant",
        "content": content or None,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for call in tool_calls
        ],
    }
