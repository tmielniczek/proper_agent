import asyncio
import json
from dataclasses import dataclass
from uuid import uuid4

from fastapi.sse import ServerSentEvent

from app.llm import LanguageModel, ModelUsage, ProviderRejection, ToolCall
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


async def run_spawn(
    raw: object, model: LanguageModel, queue: asyncio.Queue, spend: TurnSpend
) -> dict:
    plan = _plan(raw)
    if isinstance(plan, str):
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
        *(_slot_result(slot, model, queue, spend) for slot in plan.slots)
    )
    queue.put_nowait(ServerSentEvent(event="tool_end", data={"tool": SPAWN_WORKERS}))
    return {"workers": list(results), "refused": plan.refused}


async def _slot_result(
    slot: _Slot, model: LanguageModel, queue: asyncio.Queue, spend: TurnSpend
) -> dict:
    if slot.error is not None:
        return {"task": slot.task, "error": slot.error}
    try:
        return await _run_worker(slot.task, model, queue, spend)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return {"task": slot.task, "error": str(exc)}


async def _run_worker(
    task: str, model: LanguageModel, queue: asyncio.Queue, spend: TurnSpend
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
            async for event in model.stream(turns, TOOL_SCHEMAS):
                if isinstance(event, ModelUsage):
                    spend.record(event.total_tokens)
                    continue
                if isinstance(event, ToolCall):
                    tool_calls.append(event)
                    continue
                parts.append(event)
            if not tool_calls:
                return {"task": task, "text": "".join(parts)}
            turns.append(_assistant_turn("".join(parts), tool_calls))
            for call in tool_calls:
                blocked = _blocked_tool(call)
                if blocked is not None:
                    return {"task": task, "error": blocked}
                failure = await _run_worker_tool(task, call, turns, queue)
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
    task: str, call: ToolCall, turns: list[dict], queue: asyncio.Queue
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
        result = await run_tool(call.name, call.arguments)
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
