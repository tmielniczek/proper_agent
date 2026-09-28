import asyncio
import json
import threading
from types import SimpleNamespace

from app.llm import ToolCall
from test_mask_the_prompt import _chat
from test_stream_assistant_reply import sse_events

PROMPT = "What is the weather in Berlin?"
MASKED_PROMPT = "My number is [ssn] please keep it"
MASK_NOTE = "Screen: masked 1 social security number"
_real_sleep = asyncio.sleep


def test_cancel_during_streaming_keeps_only_the_prompt(client, language_model):
    language_model.replies = [["Hello", " there"]]
    language_model.hold_after_chunks = 1
    conversation_id = client.post("/api/conversations").json()["id"]
    body: dict = {}

    def read_stream() -> None:
        try:
            with client.stream(
                "POST",
                f"/api/conversations/{conversation_id}/chat",
                json={"prompt": PROMPT},
            ) as response:
                body["status"] = response.status_code
                body["text"] = response.read().decode()
        except Exception as exc:
            body["error"] = exc

    reader = threading.Thread(target=read_stream)
    reader.start()
    try:
        assert language_model.holding.wait(timeout=2)
        cancelled = client.post(f"/api/conversations/{conversation_id}/cancel")
        assert cancelled.status_code == 204
        reader.join(timeout=2)
        assert not reader.is_alive()
        assert body.get("error") is None
        assert "event: done" not in body.get("text", "")

        detail = client.get(f"/api/conversations/{conversation_id}").json()
        assert [(message["role"], message["content"]) for message in detail["messages"]] == [
            ("user", PROMPT),
        ]
        assert language_model.yielded == ["Hello"]
        assert len(language_model.calls) == 1
    finally:
        language_model.release.set()
        reader.join(timeout=2)


def test_cancel_keeps_masked_prompt_and_screen_note(client, language_model):
    language_model.replies = [["Hello", " there"]]
    language_model.hold_after_chunks = 1
    conversation_id = client.post("/api/conversations").json()["id"]
    prompt = "My number is 123-45-6789 please keep it"
    body: dict = {}

    def read_stream() -> None:
        try:
            with client.stream(
                "POST",
                f"/api/conversations/{conversation_id}/chat",
                json={"prompt": prompt},
            ) as response:
                body["text"] = response.read().decode()
        except Exception as exc:
            body["error"] = exc

    reader = threading.Thread(target=read_stream)
    reader.start()
    try:
        assert language_model.holding.wait(timeout=2)
        cancelled = client.post(f"/api/conversations/{conversation_id}/cancel")
        assert cancelled.status_code == 204
        reader.join(timeout=2)
        assert not reader.is_alive()
        assert body.get("error") is None
        assert "event: done" not in body.get("text", "")

        events = sse_events(body.get("text", ""))
        assert ("prompt", {"text": MASKED_PROMPT}) in events
        assert ("screen", {"text": MASK_NOTE}) in events

        detail = client.get(f"/api/conversations/{conversation_id}").json()
        assert [(message["role"], message["content"]) for message in detail["messages"]] == [
            ("user", MASKED_PROMPT),
        ]
        assert detail["messages"][0]["screen_notes"] == [MASK_NOTE]
        assert "123-45-6789" not in json.dumps(detail)
        assert "Hello" not in json.dumps(detail)
    finally:
        language_model.release.set()
        reader.join(timeout=2)


def test_cancel_does_not_refund_finished_model_call_tokens(
    client, language_model, monkeypatch
):
    language_model.replies = [
        [
            "Looking",
            ToolCall(id="call_weather", name="get_weather", arguments={"location": "Berlin"}),
        ],
        ["Should not continue"],
        ["Later."],
    ]
    language_model.token_totals = [500, 10]
    holding = threading.Event()
    release = threading.Event()

    async def sleep(_seconds: float) -> None:
        holding.set()
        while not release.is_set():
            await _real_sleep(0.01)

    monkeypatch.setattr("app.tools.asyncio.sleep", sleep)
    conversation_id = client.post("/api/conversations").json()["id"]
    body: dict = {}

    def read_stream() -> None:
        try:
            with client.stream(
                "POST",
                f"/api/conversations/{conversation_id}/chat",
                json={"prompt": PROMPT},
            ) as response:
                body["text"] = response.read().decode()
        except Exception as exc:
            body["error"] = exc

    reader = threading.Thread(target=read_stream)
    reader.start()
    try:
        assert holding.wait(timeout=2)
        cancelled = client.post(f"/api/conversations/{conversation_id}/cancel")
        assert cancelled.status_code == 204
        reader.join(timeout=2)
        assert not reader.is_alive()
        assert body.get("error") is None

        detail = client.get(f"/api/conversations/{conversation_id}").json()
        assert [(message["role"], message["content"]) for message in detail["messages"]] == [
            ("user", PROMPT),
        ]
    finally:
        release.set()
        reader.join(timeout=2)

    events = _chat(client, conversation_id, "Say later")
    assert (
        "screen",
        {"text": "Screen: 1 model call, 10 tokens. Today 510 of 50,000."},
    ) in events


def test_cancel_during_tool_wait_keeps_only_the_prompt(client, language_model, monkeypatch):
    language_model.replies = [
        ["Earlier answer"],
        [
            "Looking",
            ToolCall(id="call_weather", name="get_weather", arguments={"location": "Berlin"}),
        ],
        ["Should not continue"],
    ]
    holding = threading.Event()
    release = threading.Event()
    tool_finished = threading.Event()

    async def sleep(_seconds: float) -> None:
        holding.set()
        while not release.is_set():
            await _real_sleep(0.01)
        tool_finished.set()

    monkeypatch.setattr("app.tools.asyncio.sleep", sleep)
    conversation_id = client.post("/api/conversations").json()["id"]
    client.post(
        f"/api/conversations/{conversation_id}/chat",
        json={"prompt": "Say hello"},
    )
    body: dict = {}

    def read_stream() -> None:
        try:
            with client.stream(
                "POST",
                f"/api/conversations/{conversation_id}/chat",
                json={"prompt": PROMPT},
            ) as response:
                body["text"] = response.read().decode()
        except Exception as exc:
            body["error"] = exc

    reader = threading.Thread(target=read_stream)
    reader.start()
    try:
        assert holding.wait(timeout=2)
        cancelled = client.post(f"/api/conversations/{conversation_id}/cancel")
        assert cancelled.status_code == 204
        reader.join(timeout=2)
        assert not reader.is_alive()
        assert body.get("error") is None
        assert "event: done" not in body.get("text", "")

        detail = client.get(f"/api/conversations/{conversation_id}").json()
        assert [(message["role"], message["content"]) for message in detail["messages"]] == [
            ("user", "Say hello"),
            ("assistant", "Earlier answer"),
            ("user", PROMPT),
        ]
        assert len(language_model.calls) == 2
        assert tool_finished.is_set() is False
    finally:
        release.set()
        reader.join(timeout=2)


def test_cancel_aborts_the_model_request(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_NAME", "gpt-5-nano")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
    )
    started = threading.Event()
    closed = threading.Event()

    class _Stream:
        def __aiter__(self):
            return self._iter()

        async def _iter(self):
            yield _text_chunk("Hello")
            started.set()
            await _real_sleep(30)
            yield _text_chunk(" there")

        async def close(self) -> None:
            closed.set()

    class _Completions:
        async def create(self, **_kwargs):
            return _Stream()

    monkeypatch.setattr(
        "app.llm.AsyncOpenAI",
        lambda **_kwargs: SimpleNamespace(chat=SimpleNamespace(completions=_Completions())),
    )

    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        body: dict = {}

        def read_stream() -> None:
            try:
                with client.stream(
                    "POST",
                    f"/api/conversations/{conversation_id}/chat",
                    json={"prompt": PROMPT},
                ) as response:
                    body["text"] = response.read().decode()
            except Exception as exc:
                body["error"] = exc

        reader = threading.Thread(target=read_stream)
        reader.start()
        try:
            assert started.wait(timeout=2)
            cancelled = client.post(f"/api/conversations/{conversation_id}/cancel")
            assert cancelled.status_code == 204
            assert closed.wait(timeout=2)
            reader.join(timeout=2)
            assert not reader.is_alive()

            detail = client.get(f"/api/conversations/{conversation_id}").json()
            assert [(message["role"], message["content"]) for message in detail["messages"]] == [
                ("user", PROMPT),
            ]
            assert "event: done" not in body.get("text", "")
        finally:
            reader.join(timeout=2)


def _text_chunk(text: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=text, tool_calls=None))]
    )
