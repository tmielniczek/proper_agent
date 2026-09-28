import asyncio
import threading

import pytest
from fastapi.testclient import TestClient

_pause = asyncio.sleep


class RecordingModel:
    def __init__(self) -> None:
        self.replies: list[list[object]] = [["stub reply"]]
        self.calls: list[list[dict]] = []
        self.offered_tools: list[list[dict] | None] = []
        self.token_totals: list[int | None] = []
        self.reply_for = None
        self.hold_after_chunks: int | None = None
        self.holding = threading.Event()
        self.release = threading.Event()
        self.yielded: list[object] = []

    async def stream(self, messages: list[dict], tools: list[dict] | None = None):
        from app.llm import ModelUsage

        self.calls.append([dict(message) for message in messages])
        self.offered_tools.append(tools)
        if self.reply_for is not None:
            chunks = self.reply_for(messages)
        else:
            chunks = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        for index, chunk in enumerate(chunks):
            if self.hold_after_chunks is not None and index == self.hold_after_chunks:
                self.holding.set()
                while not self.release.is_set():
                    await _pause(0.01)
            if isinstance(chunk, BaseException):
                raise chunk
            self.yielded.append(chunk)
            yield chunk
        total = self.token_totals.pop(0) if self.token_totals else 1
        yield ModelUsage(total_tokens=total)


@pytest.fixture
def language_model():
    return RecordingModel()


@pytest.fixture
def client(tmp_path, monkeypatch, language_model):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{database_path.as_posix()}",
    )
    from app.main import create_app

    with TestClient(create_app(language_model)) as test_client:
        yield test_client
