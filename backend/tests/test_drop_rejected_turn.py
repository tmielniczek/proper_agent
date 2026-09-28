import json
from types import SimpleNamespace

import httpx2
from fastapi.testclient import TestClient
from openai import AuthenticationError, RateLimitError

FIRST_PROMPT = "Say hello"
FOLLOW_UP = "And now the secret"
OTHER_PROMPT = "Other thread"


def sse_events(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in body.split("\n\n"):
        if not block.strip() or block.lstrip().startswith(":"):
            continue
        event_name = "message"
        data = None
        for line in block.split("\n"):
            if line.startswith("event:"):
                event_name = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                data = json.loads(line.removeprefix("data:").strip())
        if data is not None:
            events.append((event_name, data))
    return events


def _status_error(error_type, status_code: int):
    request = httpx2.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx2.Response(status_code, request=request)
    return error_type("rejected", response=response, body=None)


def _text_chunk(text: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=text, tool_calls=None))]
    )


class _TextStream:
    def __init__(self, texts: list[str], error: Exception | None = None) -> None:
        self._texts = texts
        self._error = error

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for text in self._texts:
            yield _text_chunk(text)
        if self._error is not None:
            raise self._error

    async def close(self) -> None:
        return None


class _Completions:
    def __init__(self, steps: list) -> None:
        self._steps = steps

    async def create(self, **_kwargs):
        step = self._steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def _open_client(tmp_path, monkeypatch, steps: list) -> TestClient:
    monkeypatch.setenv("MODEL_NAME", "gpt-5-nano")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
    )
    monkeypatch.setattr(
        "app.llm.AsyncOpenAI",
        lambda **_kwargs: SimpleNamespace(chat=SimpleNamespace(completions=_Completions(steps))),
    )
    from app.main import create_app

    return TestClient(create_app())


def _chat(client: TestClient, conversation_id: str, prompt: str) -> list[tuple[str, dict]]:
    with client.stream(
        "POST",
        f"/api/conversations/{conversation_id}/chat",
        json={"prompt": prompt},
    ) as response:
        assert response.status_code == 200
        return sse_events(response.read().decode())


def test_rejected_api_key_drops_the_turn_and_leaves_the_sidebar(tmp_path, monkeypatch):
    steps = [
        _TextStream(["Hello"]),
        _TextStream(["There"]),
        _status_error(AuthenticationError, 401),
    ]
    with _open_client(tmp_path, monkeypatch, steps) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        _chat(client, conversation_id, FIRST_PROMPT)
        other_id = client.post("/api/conversations").json()["id"]
        _chat(client, other_id, OTHER_PROMPT)
        sidebar_before = client.get("/api/conversations").json()

        events = _chat(client, conversation_id, FOLLOW_UP)

        detail = client.get(f"/api/conversations/{conversation_id}").json()
        sidebar_after = client.get("/api/conversations").json()

    assert events[-1] == ("error", {"error": "The API key was rejected"})
    assert [name for name, _payload in events if name == "done"] == []
    assert [(message["role"], message["content"]) for message in detail["messages"]] == [
        ("user", FIRST_PROMPT),
        ("assistant", "Hello"),
    ]
    assert FOLLOW_UP not in json.dumps(detail)
    assert sidebar_after == sidebar_before
    assert [conversation["id"] for conversation in sidebar_after] == [other_id, conversation_id]
    assert sidebar_after[1]["title"] == FIRST_PROMPT


def test_rate_limit_drops_partial_text_and_leaves_the_sidebar(tmp_path, monkeypatch):
    prompt = "What is the current temperature in Berlin?"
    steps = [
        _TextStream(["Partial"], error=_status_error(RateLimitError, 429)),
    ]
    with _open_client(tmp_path, monkeypatch, steps) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        other_id = client.post("/api/conversations").json()["id"]
        sidebar_before = client.get("/api/conversations").json()

        events = _chat(client, conversation_id, prompt)

        detail = client.get(f"/api/conversations/{conversation_id}").json()
        sidebar_after = client.get("/api/conversations").json()

    assert [(name, payload.get("text")) for name, payload in events if name == "delta"] == []
    assert events[-1] == ("error", {"error": "The request was rate-limited"})
    assert [name for name, _payload in events if name == "done"] == []
    assert detail["messages"] == []
    assert detail["title"] == ""
    assert "Partial" not in json.dumps(detail)
    assert prompt not in json.dumps(detail)
    assert sidebar_after == sidebar_before
    assert [conversation["id"] for conversation in sidebar_after] == [other_id, conversation_id]
