import json
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db import get_session
from app.models import Conversation, Message

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
    messages = [
        MessageOut(
            id=message.id,
            role=message.role,
            content=message.content,
            created_at=message.created_at.isoformat(),
        )
        for message in result.all()
    ]
    summary = _conversation_out(conversation)
    return ConversationDetail(**summary.model_dump(), messages=messages)


@router.post("/{conversation_id}/chat")
async def chat(
    conversation_id: str,
    body: ChatIn,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
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
    message = Message(
        id=str(uuid4()),
        conversation_id=conversation_id,
        role="user",
        content=body.prompt,
        created_at=now,
    )
    conversation.updated_at = now
    session.add(message)
    session.add(conversation)
    await session.commit()

    return StreamingResponse(
        _done_event(message.id),
        media_type="text/event-stream",
    )


async def _done_event(message_id: str) -> AsyncIterator[str]:
    payload = json.dumps({"message_id": message_id})
    yield f"event: done\ndata: {payload}\n\n"


async def _require_conversation(session: AsyncSession, conversation_id: str) -> Conversation:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation
