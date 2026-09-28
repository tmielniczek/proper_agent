import os
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

engine: AsyncEngine | None = None
session_factory: async_sessionmaker[AsyncSession] | None = None


def database_url() -> str:
    configured = os.environ.get("DATABASE_URL")
    if configured:
        return configured
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{(data_dir / 'app.db').as_posix()}"


def init_engine() -> None:
    global engine, session_factory
    engine = create_async_engine(database_url())
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _add_message_tool_columns(sync_connection) -> None:
    rows = sync_connection.execute(text("PRAGMA table_info(messages)")).fetchall()
    names = {row[1] for row in rows}
    if "tool_calls" not in names:
        sync_connection.execute(text("ALTER TABLE messages ADD COLUMN tool_calls TEXT"))
    if "tool_call_id" not in names:
        sync_connection.execute(text("ALTER TABLE messages ADD COLUMN tool_call_id TEXT"))
    if "screen_notes" not in names:
        sync_connection.execute(text("ALTER TABLE messages ADD COLUMN screen_notes TEXT"))


async def init_db() -> None:
    # Register table metadata before create_all.
    from app.models import DailyTokenTotal  # noqa: F401

    assert engine is not None
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
        await connection.run_sync(_add_message_tool_columns)



async def get_session() -> AsyncIterator[AsyncSession]:
    assert session_factory is not None
    async with session_factory() as session:
        yield session


async def dispose_engine() -> None:
    global engine, session_factory
    if engine is not None:
        await engine.dispose()
    engine = None
    session_factory = None
