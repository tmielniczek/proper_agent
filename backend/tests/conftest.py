import pytest
from fastapi.testclient import TestClient


class RecordingModel:
    def __init__(self) -> None:
        self.replies: list[list[object]] = [["stub reply"]]
        self.calls: list[list[dict]] = []

    async def stream(self, messages: list[dict]):
        self.calls.append([dict(message) for message in messages])
        chunks = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        for chunk in chunks:
            yield chunk


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
