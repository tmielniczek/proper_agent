from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime
from sqlmodel import Field, SQLModel


class Conversation(SQLModel, table=True):
    __tablename__ = "conversations"

    id: str = Field(primary_key=True)
    title: str
    created_at: datetime = Field(sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(sa_type=DateTime(timezone=True))


class Memory(SQLModel, table=True):
    __tablename__ = "memories"

    id: str = Field(primary_key=True)
    fact: str
    created_at: datetime = Field(sa_type=DateTime(timezone=True))


class DailyTokenTotal(SQLModel, table=True):
    __tablename__ = "daily_token_totals"

    local_date: str = Field(primary_key=True)
    tokens: int = 0


class Message(SQLModel, table=True):
    __tablename__ = "messages"
    __table_args__ = (CheckConstraint("role IN ('user', 'assistant', 'tool')"),)

    id: str = Field(primary_key=True)
    conversation_id: str = Field(foreign_key="conversations.id", ondelete="CASCADE")
    role: str
    content: str | None = None
    tool_calls: str | None = None
    tool_call_id: str | None = None
    screen_notes: str | None = None
    created_at: datetime = Field(sa_type=DateTime(timezone=True))
