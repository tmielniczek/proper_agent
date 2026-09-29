import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from opentelemetry.trace import (
    Span,
    SpanKind,
    Status,
    StatusCode,
    Tracer,
    set_span_in_context,
)
from pydantic import BaseModel, Field
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app import db
from app.compaction import (
    STOPPED_TOO_LARGE,
    LeadView,
    compaction_line,
    drop_rolling_if_folded_message_was_deleted,
    lead_view,
    remember_rolling,
    rolling_for,
    summary_anchor,
    with_brief,
)
from app.tokens import count_messages
from app.db import get_session
from app.llm import ModelUsage, ProviderRejection, ToolCall, configured_model_name, model_from_env
from app.models import Conversation, Message
from app.memory import memory_preface
from app.screen import (
    DAILY_TOKEN_BUDGET,
    PHRASE_LIST_REFUSAL,
    STOPPED_DAILY_BUDGET,
    STOPPED_MISSING_COUNT,
    TurnSpend,
    mask_prompt,
    matches_phrase_list,
    today_tokens,
)
from app.spawn import run_spawn
from app.tools import LEAD_TOOL_SCHEMAS, SPAWN_WORKERS, display_text, run_tool


router = APIRouter(prefix="/api/conversations", tags=["conversations"])

_last_timestamp = datetime.min.replace(tzinfo=timezone.utc)


@dataclass
class _Run:
    user_message_id: str
    task: asyncio.Task[None] | None = None
    completed: bool = False
    turn_span: Span | None = None


_runs: dict[str, _Run] = {}


def next_timestamp() -> datetime:
    global _last_timestamp
    now = datetime.now(timezone.utc)
    if now <= _last_timestamp:
        now = _last_timestamp + timedelta(microseconds=1)
    _last_timestamp = now
    return now


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class MessageOut(BaseModel):
    id: str
    role: str
    content: str | None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    screen_notes: list[str] | None = None
    created_at: str


class CompactionOut(BaseModel):
    brief: str
    after_message_id: str | None = None


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]
    compaction: CompactionOut | None = None


class TokenStatsOut(BaseModel):
    tokens: int
    context_window: int
    compaction_line: int


class ChatIn(BaseModel):
    prompt: str = Field(min_length=1)


def _conversation_out(conversation: Conversation) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at.isoformat(),
        updated_at=conversation.updated_at.isoformat(),
    )


@router.get("")
async def list_conversations(
    session: AsyncSession = Depends(get_session),
) -> list[ConversationOut]:
    result = await session.exec(select(Conversation).order_by(Conversation.updated_at.desc()))
    return [_conversation_out(conversation) for conversation in result.all()]


@router.post("")
async def create_conversation(
    session: AsyncSession = Depends(get_session),
) -> ConversationOut:
    now = next_timestamp()
    conversation = Conversation(id=str(uuid4()), title="", created_at=now, updated_at=now)
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return _conversation_out(conversation)


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
) -> ConversationDetail:
    conversation = await _require_conversation(session, conversation_id)
    result = await session.exec(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    stored = list(result.all())
    messages = [_message_out(message) for message in stored]
    summary = _conversation_out(conversation)
    rolling = rolling_for(conversation_id)
    compaction = None
    if rolling is not None:
        compaction = CompactionOut(
            brief=rolling.brief,
            after_message_id=summary_anchor([_turn(message) for message in stored], rolling.folded_ids),
        )
    return ConversationDetail(**summary.model_dump(), messages=messages, compaction=compaction)


@router.get("/{conversation_id}/tokens")
async def conversation_tokens(
    conversation_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TokenStatsOut:
    await _require_conversation(session, conversation_id)
    result = await session.exec(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    turns = [_turn(message) for message in result.all()]
    if turns:
        preface = await memory_preface()
        if preface is not None:
            turns.insert(0, {"role": "system", "content": preface})
    window = request.app.state.context_window
    return TokenStatsOut(
        tokens=count_messages(turns),
        context_window=window,
        compaction_line=compaction_line(window),
    )


@router.post("/{conversation_id}/chat", response_class=EventSourceResponse)
async def chat(
    conversation_id: str,
    body: ChatIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> AsyncIterator[ServerSentEvent]:
    with request.app.state.tracer.start_as_current_span(
        "turn", kind=SpanKind.INTERNAL
    ) as turn_span:
        conversation = await _require_conversation(session, conversation_id)
        previous_title = conversation.title
        previous_updated_at = conversation.updated_at
        masked = mask_prompt(body.prompt)
        phrase_refused = matches_phrase_list(body.prompt)
        budget_refused = (not phrase_refused) and (
            await today_tokens() >= DAILY_TOKEN_BUDGET
        )
        refusal = (
            PHRASE_LIST_REFUSAL
            if phrase_refused
            else (STOPPED_DAILY_BUDGET if budget_refused else None)
        )
        existing_user_messages = await session.exec(
            select(Message).where(
                Message.conversation_id == conversation_id,
                Message.role == "user",
            )
        )
        if existing_user_messages.first() is None:
            conversation.title = masked.text[:30]

        now = next_timestamp()
        user_message = Message(
            id=str(uuid4()),
            conversation_id=conversation_id,
            role="user",
            content=masked.text,
            screen_notes=(
                None
                if refusal is not None
                else (json.dumps([masked.note]) if masked.note else None)
            ),
            created_at=now,
        )
        conversation.updated_at = now
        session.add(user_message)
        session.add(conversation)

        if refusal is not None:
            turn_span.set_attribute("app.status", "refused")
            turn_span.set_status(Status(StatusCode.OK))
            refused_at = next_timestamp()
            assistant_message = Message(
                id=str(uuid4()),
                conversation_id=conversation_id,
                role="assistant",
                content=refusal,
                created_at=refused_at,
            )
            conversation.updated_at = refused_at
            session.add(assistant_message)
            session.add(conversation)
            await session.commit()
            yield ServerSentEvent(event="prompt", data={"text": masked.text})
            yield ServerSentEvent(event="delta", data={"text": refusal})
            yield ServerSentEvent(
                event="done", data={"message_id": assistant_message.id}
            )
            return

        await session.commit()

        history = await session.exec(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        turns = [_turn(message) for message in history.all()]

        model = request.app.state.language_model
        if model is None:
            model = model_from_env()
            request.app.state.language_model = model

        queue: asyncio.Queue[ServerSentEvent | None] = asyncio.Queue()
        released = asyncio.Event()
        run = _Run(user_message_id=user_message.id, turn_span=turn_span)
        run.task = asyncio.create_task(
            _reply(
                conversation_id,
                turns,
                model,
                queue,
                run,
                previous_title,
                previous_updated_at,
                released,
                request.app.state.context_window,
                request.app.state.tracer,
            )
        )
        _runs[conversation_id] = run
        try:
            yield ServerSentEvent(event="prompt", data={"text": masked.text})
            if masked.note is not None:
                yield ServerSentEvent(event="screen", data={"text": masked.note})
            released.set()
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            task = run.task
            if task is not None and not task.done():
                task.cancel()
            if task is not None:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            if run.completed and _runs.get(conversation_id) is run:
                del _runs[conversation_id]


@router.post("/{conversation_id}/cancel", status_code=204)
async def cancel_generation(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    conversation = await _require_conversation(session, conversation_id)
    run = _runs.get(conversation_id)
    if run is None or run.task is None:
        return
    if not run.task.done():
        run.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await run.task
    if not run.completed:
        await _drop_messages_after(session, conversation, run.user_message_id)
    if _runs.get(conversation_id) is run:
        del _runs[conversation_id]


async def _reply(
    conversation_id: str,
    turns: list[dict],
    model: Any,
    queue: asyncio.Queue[ServerSentEvent | None],
    run: _Run,
    previous_title: str,
    previous_updated_at: datetime,
    released: asyncio.Event,
    context_window: int,
    tracer: Tracer,
) -> None:
    await released.wait()
    assert db.session_factory is not None
    async with db.session_factory() as session:
        conversation = await session.get(Conversation, conversation_id)
        assert conversation is not None
        preface = await memory_preface()
        if preface is not None:
            turns.insert(0, {"role": "system", "content": preface})
        spend = TurnSpend()
        try:
            while True:
                outgoing = await _lead_messages(
                    turns,
                    model,
                    context_window,
                    conversation_id,
                    spend,
                    queue,
                    tracer,
                )
                if isinstance(outgoing, str):
                    await _stop_turn(
                        session, conversation, conversation_id, outgoing, queue, run
                    )
                    return
                reason = await spend.claim_call()
                if reason is not None:
                    await _stop_turn(
                        session, conversation, conversation_id, reason, queue, run
                    )
                    return

                parts: list[str] = []
                tool_calls: list[ToolCall] = []
                model_name = configured_model_name()
                usage: ModelUsage | None = None
                with tracer.start_as_current_span(
                    f"chat {model_name}", kind=SpanKind.INTERNAL
                ) as chat_span:
                    async for event in model.stream(outgoing, LEAD_TOOL_SCHEMAS):
                        if isinstance(event, ModelUsage):
                            usage = event
                            await spend.record(event.total_tokens)
                            continue
                        if isinstance(event, ToolCall):
                            tool_calls.append(event)
                            continue
                        parts.append(event)
                    _mark_chat_ok(chat_span, model=model_name, caller="lead", usage=usage)

                if not tool_calls:
                    masked = mask_prompt("".join(parts))
                    if masked.text:
                        queue.put_nowait(
                            ServerSentEvent(event="delta", data={"text": masked.text})
                        )
                    notes: list[str] = []
                    if masked.note is not None:
                        notes.append(masked.note)
                        queue.put_nowait(
                            ServerSentEvent(event="screen", data={"text": masked.note})
                        )
                    cost = await spend.note()
                    notes.append(cost)
                    queue.put_nowait(ServerSentEvent(event="screen", data={"text": cost}))
                    saved_at = next_timestamp()
                    assistant_message = Message(
                        id=str(uuid4()),
                        conversation_id=conversation_id,
                        role="assistant",
                        content=masked.text,
                        screen_notes=json.dumps(notes),
                        created_at=saved_at,
                    )
                    conversation.updated_at = saved_at
                    session.add(assistant_message)
                    session.add(conversation)
                    await session.commit()
                    if run.turn_span is not None:
                        run.turn_span.set_attribute("app.status", "ok")
                        run.turn_span.set_status(Status(StatusCode.OK))
                    run.completed = True
                    queue.put_nowait(
                        ServerSentEvent(event="done", data={"message_id": assistant_message.id})
                    )
                    return

                for part in parts:
                    queue.put_nowait(ServerSentEvent(event="delta", data={"text": part}))
                saved_at = next_timestamp()
                assistant_message = Message(
                    id=str(uuid4()),
                    conversation_id=conversation_id,
                    role="assistant",
                    content="".join(parts) or None,
                    tool_calls=json.dumps([_stored_tool_call(call) for call in tool_calls]),
                    created_at=saved_at,
                )
                conversation.updated_at = saved_at
                session.add(assistant_message)
                session.add(conversation)
                await session.commit()
                turns.append(_turn(assistant_message))

                together = len(tool_calls) > 1 and all(
                    call.name != SPAWN_WORKERS for call in tool_calls
                )
                if together:
                    results = await asyncio.gather(
                        *(
                            _run_tool_call(
                                call,
                                model,
                                queue,
                                spend,
                                parallel=True,
                                tracer=tracer,
                                chat_span=chat_span,
                            )
                            for call in tool_calls
                        )
                    )
                else:
                    results = [
                        await _run_tool_call(
                            call,
                            model,
                            queue,
                            spend,
                            parallel=False,
                            tracer=tracer,
                            chat_span=chat_span,
                        )
                        for call in tool_calls
                    ]
                for call, result in zip(tool_calls, results, strict=True):
                    tool_saved_at = next_timestamp()
                    tool_message = Message(
                        id=str(uuid4()),
                        conversation_id=conversation_id,
                        role="tool",
                        content=json.dumps(result),
                        tool_call_id=call.id,
                        created_at=tool_saved_at,
                    )
                    conversation.updated_at = tool_saved_at
                    session.add(tool_message)
                    session.add(conversation)
                    await session.commit()
                    turns.append(_turn(tool_message))

                if spend.stop_reason is not None:
                    await _stop_turn(
                        session,
                        conversation,
                        conversation_id,
                        spend.stop_reason,
                        queue,
                        run,
                    )
                    return
        except asyncio.CancelledError:
            _clear_cancellation()
            raise
        except ProviderRejection as rejection:
            await _drop_rejected_turn(
                session,
                conversation,
                run.user_message_id,
                previous_title,
                previous_updated_at,
            )
            run.completed = True
            queue.put_nowait(ServerSentEvent(event="error", data={"error": str(rejection)}))
        finally:
            queue.put_nowait(None)


async def _stop_turn(
    session: AsyncSession,
    conversation: Conversation,
    conversation_id: str,
    reason: str,
    queue: asyncio.Queue[ServerSentEvent | None],
    run: _Run,
) -> None:
    queue.put_nowait(ServerSentEvent(event="delta", data={"text": reason}))
    saved_at = next_timestamp()
    assistant_message = Message(
        id=str(uuid4()),
        conversation_id=conversation_id,
        role="assistant",
        content=reason,
        created_at=saved_at,
    )
    conversation.updated_at = saved_at
    session.add(assistant_message)
    session.add(conversation)
    await session.commit()
    run.completed = True
    queue.put_nowait(
        ServerSentEvent(event="done", data={"message_id": assistant_message.id})
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _clear_cancellation() -> None:
    task = asyncio.current_task()
    if task is None:
        return
    while task.cancelling():
        task.uncancel()


async def _drop_rejected_turn(
    session: AsyncSession,
    conversation: Conversation,
    user_message_id: str,
    previous_title: str,
    previous_updated_at: datetime,
) -> None:
    user_message = await session.get(Message, user_message_id)
    if user_message is not None:
        result = await session.exec(
            select(Message).where(Message.conversation_id == conversation.id)
        )
        cutoff = _as_utc(user_message.created_at)
        for message in result.all():
            if _as_utc(message.created_at) >= cutoff:
                await session.delete(message)
    conversation.title = previous_title
    conversation.updated_at = previous_updated_at
    session.add(conversation)
    await session.commit()


async def _drop_messages_after(
    session: AsyncSession,
    conversation: Conversation,
    user_message_id: str,
) -> None:
    user_message = await session.get(Message, user_message_id)
    if user_message is None:
        return
    result = await session.exec(
        select(Message).where(Message.conversation_id == conversation.id)
    )
    cutoff = _as_utc(user_message.created_at)
    deleted_ids: list[str] = []
    for message in result.all():
        if _as_utc(message.created_at) > cutoff:
            deleted_ids.append(message.id)
            await session.delete(message)
    conversation.updated_at = user_message.created_at
    session.add(conversation)
    await session.commit()
    drop_rolling_if_folded_message_was_deleted(conversation.id, set(deleted_ids))


def _message_out(message: Message) -> MessageOut:
    return MessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        tool_calls=json.loads(message.tool_calls) if message.tool_calls else None,
        tool_call_id=message.tool_call_id,
        screen_notes=json.loads(message.screen_notes) if message.screen_notes else None,
        created_at=message.created_at.isoformat(),
    )


def _stored_tool_call(call: ToolCall) -> dict[str, Any]:
    return {
        "id": call.id,
        "type": "function",
        "function": {
            "name": call.name,
            "arguments": json.dumps(call.arguments),
        },
    }


async def _run_tool_call(
    call: ToolCall,
    model: Any,
    queue: asyncio.Queue,
    spend: TurnSpend,
    *,
    parallel: bool,
    tracer: Tracer,
    chat_span: Span,
) -> dict:
    if call.name == SPAWN_WORKERS:
        return await run_spawn(call.arguments.get("tasks"), model, queue, spend)
    data = {"tool": call.name, "display_text": display_text(call.name)}
    end = {"tool": call.name}
    if parallel:
        call_id = call.id or str(uuid4())
        data["call_id"] = call_id
        end["call_id"] = call_id
    queue.put_nowait(ServerSentEvent(event="tool_start", data=data))
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
            return result
    finally:
        queue.put_nowait(ServerSentEvent(event="tool_end", data=end))


def _turn(message: Message) -> dict:
    if message.role == "tool":
        turn = {
            "role": "tool",
            "tool_call_id": message.tool_call_id,
            "content": message.content or "",
        }
    elif message.tool_calls:
        turn = {
            "role": "assistant",
            "content": message.content,
            "tool_calls": json.loads(message.tool_calls),
        }
    else:
        turn = {"role": message.role, "content": message.content or ""}
    turn["_id"] = message.id
    return turn


def _announce_compaction(
    queue: asyncio.Queue[ServerSentEvent | None],
    brief: str,
    after_message_id: str | None,
) -> None:
    data: dict[str, str] = {"text": brief}
    if after_message_id is not None:
        data["after_message_id"] = after_message_id
    queue.put_nowait(ServerSentEvent(event="compaction", data=data))


async def _lead_messages(
    turns: list[dict],
    model: Any,
    context_window: int,
    conversation_id: str,
    spend: TurnSpend,
    queue: asyncio.Queue[ServerSentEvent | None],
    tracer: Tracer,
) -> list[dict] | str:
    view = lead_view(turns, context_window, rolling_for(conversation_id))
    if view.stop is not None:
        return view.stop
    if view.summary_messages is None:
        if view.brief is not None:
            _announce_compaction(queue, view.brief, view.after_message_id)
        return view.messages
    reason = await spend.claim_call()
    if reason is not None:
        return reason
    try:
        brief, usage = await _summary_brief(model, view, tracer)
    except ProviderRejection:
        return STOPPED_TOO_LARGE
    await spend.record(usage, spend_turn=False)
    if spend.missing_count:
        return STOPPED_MISSING_COUNT
    if not brief.strip():
        return STOPPED_TOO_LARGE
    brief = brief.strip()
    remember_rolling(conversation_id, brief, view.folded_ids)
    _announce_compaction(queue, brief, view.after_message_id)
    messages = with_brief(view, brief)
    if count_messages(messages) > context_window:
        return STOPPED_TOO_LARGE
    return messages


async def _summary_brief(
    model: Any, view: LeadView, tracer: Tracer
) -> tuple[str, int | None]:
    parts: list[str] = []
    usage: int | None = None
    saw_usage = False
    model_name = configured_model_name()
    model_usage: ModelUsage | None = None
    with tracer.start_as_current_span(
        f"chat {model_name}", kind=SpanKind.INTERNAL
    ) as chat_span:
        async for event in model.stream(view.summary_messages, []):
            if isinstance(event, ModelUsage):
                model_usage = event
                usage = event.total_tokens
                saw_usage = True
                continue
            if isinstance(event, str):
                parts.append(event)
        _mark_chat_ok(chat_span, model=model_name, caller="summary", usage=model_usage)
    if not saw_usage:
        usage = None
    return "".join(parts), usage


def _mark_chat_ok(
    span: Span, *, model: str, caller: str, usage: ModelUsage | None
) -> None:
    span.set_attribute("gen_ai.operation.name", "chat")
    span.set_attribute("gen_ai.provider.name", "openai")
    span.set_attribute("gen_ai.request.model", model)
    span.set_attribute("app.caller", caller)
    span.set_attribute("app.status", "ok")
    span.set_status(Status(StatusCode.OK))
    if usage is None:
        return
    if usage.input_tokens is not None:
        span.set_attribute("gen_ai.usage.input_tokens", usage.input_tokens)
    if usage.output_tokens is not None:
        span.set_attribute("gen_ai.usage.output_tokens", usage.output_tokens)


async def _require_conversation(session: AsyncSession, conversation_id: str) -> Conversation:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation
