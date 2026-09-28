import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlmodel import col, select

from app import db
from app.models import Memory

_last_saved_at = datetime.min.replace(tzinfo=timezone.utc)
_write_lock: asyncio.Lock | None = None


def _saved_at() -> datetime:
    global _last_saved_at
    now = datetime.now(timezone.utc)
    if now <= _last_saved_at:
        now = _last_saved_at + timedelta(microseconds=1)
    _last_saved_at = now
    return now


def _lock() -> asyncio.Lock:
    global _write_lock
    if _write_lock is None:
        _write_lock = asyncio.Lock()
    return _write_lock


def _one_line(fact: str) -> str:
    return fact.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def format_memories(facts: list[str]) -> str:
    bullets = "\n".join(f"- {_one_line(fact)}" for fact in facts)
    return (
        "Memories, newest first:\n"
        f"{bullets}\n"
        "\n"
        "Workers cannot see these memories. If a task needs a fact, write that fact into the task."
    )


async def save_memory(arguments: dict) -> dict:
    fact = arguments.get("fact")
    if not isinstance(fact, str) or fact.strip() == "":
        return {"error": "Memory needs a fact."}
    stored = fact.strip()
    assert db.session_factory is not None
    async with _lock():
        async with db.session_factory() as session:
            session.add(Memory(id=str(uuid4()), fact=stored, created_at=_saved_at()))
            await session.commit()
    return {"saved": stored}


async def memory_preface() -> str | None:
    assert db.session_factory is not None
    async with db.session_factory() as session:
        result = await session.exec(
            select(Memory).order_by(col(Memory.created_at).desc()).limit(20)
        )
        facts = [memory.fact for memory in result.all()]
    if not facts:
        return None
    return format_memories(facts)
