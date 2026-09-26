import json
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db import get_session
from app.llm import ToolCall, model_from_env
from app.models import Conversation, Message
from app.tools import display_text, run_tool

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

_last_timestamp = datetime.min.replace(tzinfo=timezone.utc)


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
    created_at: str


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


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
    messages = [_message_out(message) for message in result.all()]
    summary = _conversation_out(conversation)
    return ConversationDetail(**summary.model_dump(), messages=messages)


@router.post("/{conversation_id}/chat", response_class=EventSourceResponse)
async def chat(
    conversation_id: str,
    body: ChatIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> AsyncIterator[ServerSentEvent]:
    conversation = await _require_conversation(session, conversation_id)
    existing_user_messages = await session.exec(
        select(Message).where(
            Message.conversation_id == conversation_id,
            Message.role == "user",
        )
    )
    if existing_user_messages.first() is None:
        conversation.title = body.prompt[:30]

    now = next_timestamp()
    user_message = Message(
        id=str(uuid4()),
        conversation_id=conversation_id,
        role="user",
        content=body.prompt,
        created_at=now,
    )
    conversation.updated_at = now
    session.add(user_message)
    session.add(conversation)
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

    while True:
        parts: list[str] = []
        tool_calls: list[ToolCall] = []
        async for event in model.stream(turns):
            if isinstance(event, ToolCall):
                tool_calls.append(event)
                continue
            parts.append(event)
            yield ServerSentEvent(event="delta", data={"text": event})

        if not tool_calls:
            saved_at = next_timestamp()
            assistant_message = Message(
                id=str(uuid4()),
                conversation_id=conversation_id,
                role="assistant",
                content="".join(parts),
                created_at=saved_at,
            )
            conversation.updated_at = saved_at
            session.add(assistant_message)
            session.add(conversation)
            await session.commit()
            yield ServerSentEvent(event="done", data={"message_id": assistant_message.id})
            return

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

        for call in tool_calls:
            yield ServerSentEvent(
                event="tool_start",
                data={"tool": call.name, "display_text": display_text(call.name)},
            )
            result = await run_tool(call.name, call.arguments)
            yield ServerSentEvent(event="tool_end", data={"tool": call.name})
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


def _message_out(message: Message) -> MessageOut:
    return MessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        tool_calls=json.loads(message.tool_calls) if message.tool_calls else None,
        tool_call_id=message.tool_call_id,
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


def _turn(message: Message) -> dict:
    if message.role == "tool":
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id,
            "content": message.content or "",
        }
    if message.tool_calls:
        return {
            "role": "assistant",
            "content": message.content,
            "tool_calls": json.loads(message.tool_calls),
        }
    return {"role": message.role, "content": message.content or ""}


async def _require_conversation(session: AsyncSession, conversation_id: str) -> Conversation:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation
