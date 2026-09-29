import asyncio
import threading

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from fastapi.testclient import TestClient

from app.compaction import STOPPED_TOO_LARGE
from app.llm import ToolCall
from app.screen import STOPPED_CALL_CAP, STOPPED_TOKEN_CAP
from app.tokens import text_with_tokens
from test_stream_assistant_reply import sse_events

MODEL_NAME = "gpt-5-nano"
PROMPT = "What is the weather in Berlin?"
_real_sleep = asyncio.sleep


def _client(tmp_path, monkeypatch, language_model, exporter: InMemorySpanExporter):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{database_path.as_posix()}",
    )
    monkeypatch.setenv("MODEL_NAME", MODEL_NAME)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    from app.main import create_app

    return TestClient(create_app(language_model, span_exporter=exporter))


def _chat(client, conversation_id: str, prompt: str):
    with client.stream(
        "POST",
        f"/api/conversations/{conversation_id}/chat",
        json={"prompt": prompt},
    ) as response:
        assert response.status_code == 200
        return sse_events(response.read().decode())


def _spans_by_name(exporter: InMemorySpanExporter, prefix: str = ""):
    spans = exporter.get_finished_spans()
    if prefix:
        return [span for span in spans if span.name.startswith(prefix)]
    return list(spans)


def _assert_not_error(span) -> None:
    assert span.status.status_code == StatusCode.OK
    assert "error.type" not in (span.attributes or {})


def _cancel_while_holding(client, conversation_id: str, holding: threading.Event, release: threading.Event):
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
    finally:
        release.set()
        reader.join(timeout=2)
    return body


def test_cancel_during_model_stream_marks_chat_and_turn_cancelled(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    language_model.replies = [["Hello", " there"]]
    language_model.hold_after_chunks = 1
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        _cancel_while_holding(
            client, conversation_id, language_model.holding, language_model.release
        )

    turn = _spans_by_name(exporter, "turn")
    chats = _spans_by_name(exporter, "chat ")
    assert len(turn) == 1
    assert len(chats) == 1
    assert turn[0].attributes["app.status"] == "cancelled"
    assert chats[0].attributes["app.status"] == "cancelled"
    _assert_not_error(turn[0])
    _assert_not_error(chats[0])


def test_finished_chat_stays_ok_when_later_cancel_arrives(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    language_model.replies = [
        [
            "Looking",
            ToolCall(id="call_weather", name="get_weather", arguments={"location": "Berlin"}),
        ],
        ["Should not continue"],
    ]
    holding = threading.Event()
    release = threading.Event()

    async def sleep(_seconds: float) -> None:
        holding.set()
        while not release.is_set():
            await _real_sleep(0.01)

    monkeypatch.setattr("app.tools.asyncio.sleep", sleep)
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        _cancel_while_holding(client, conversation_id, holding, release)

    chats = _spans_by_name(exporter, "chat ")
    tools = _spans_by_name(exporter, "execute_tool ")
    turn = _spans_by_name(exporter, "turn")
    assert len(chats) == 1
    assert len(tools) == 1
    assert len(turn) == 1
    assert chats[0].attributes["app.status"] == "ok"
    assert tools[0].attributes["app.status"] == "cancelled"
    assert turn[0].attributes["app.status"] == "cancelled"
    _assert_not_error(chats[0])
    _assert_not_error(tools[0])
    _assert_not_error(turn[0])


def test_cancel_during_tool_marks_tool_and_turn_cancelled(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    language_model.replies = [
        [
            "Looking",
            ToolCall(id="call_weather", name="get_weather", arguments={"location": "Berlin"}),
        ],
        ["Should not continue"],
    ]
    holding = threading.Event()
    release = threading.Event()

    async def sleep(_seconds: float) -> None:
        holding.set()
        while not release.is_set():
            await _real_sleep(0.01)

    monkeypatch.setattr("app.tools.asyncio.sleep", sleep)
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        _cancel_while_holding(client, conversation_id, holding, release)

    chats = _spans_by_name(exporter, "chat ")
    tools = _spans_by_name(exporter, "execute_tool ")
    turn = _spans_by_name(exporter, "turn")
    assert chats[0].attributes["app.status"] == "ok"
    assert tools[0].attributes["app.status"] == "cancelled"
    assert tools[0].attributes["gen_ai.tool.name"] == "get_weather"
    assert turn[0].attributes["app.status"] == "cancelled"
    _assert_not_error(tools[0])
    _assert_not_error(turn[0])


def test_call_cap_stop_before_next_call_marks_turn_stopped_without_extra_chat(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()

    async def instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.tools.asyncio.sleep", instant)
    language_model.replies = [
        [ToolCall(id=f"call_{index}", name="get_weather", arguments={"location": "Berlin"})]
        for index in range(10)
    ] + [["Should not run"]]
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        events = _chat(client, conversation_id, "Keep going")

    assert [payload["text"] for name, payload in events if name == "delta"] == [
        STOPPED_CALL_CAP
    ]
    assert len(language_model.calls) == 10
    turn = _spans_by_name(exporter, "turn")
    chats = _spans_by_name(exporter, "chat ")
    assert len(turn) == 1
    assert len(chats) == 10
    assert turn[0].attributes["app.status"] == "stopped"
    assert all(span.attributes["app.status"] == "ok" for span in chats)
    _assert_not_error(turn[0])


def test_token_cap_after_finished_call_keeps_chat_ok_and_stops_turn(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()

    async def instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.tools.asyncio.sleep", instant)
    language_model.replies = [
        [ToolCall(id="call_weather", name="get_weather", arguments={"location": "Berlin"})],
        ["Should not run"],
    ]
    language_model.token_totals = [8000]
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        events = _chat(client, conversation_id, "Spend tokens")

    assert [payload["text"] for name, payload in events if name == "delta"] == [
        STOPPED_TOKEN_CAP
    ]
    assert len(language_model.calls) == 1
    turn = _spans_by_name(exporter, "turn")
    chats = _spans_by_name(exporter, "chat ")
    assert len(turn) == 1
    assert len(chats) == 1
    assert chats[0].attributes["app.status"] == "ok"
    assert turn[0].attributes["app.status"] == "stopped"
    _assert_not_error(chats[0])
    _assert_not_error(turn[0])


def test_context_window_stop_before_any_model_call_marks_turn_stopped(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    language_model.replies = [["Noted."]]
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        for prompt in ("alpha", "beta", "gamma", "delta"):
            _chat(client, conversation_id, prompt)
        client.app.state.context_window = 10
        language_model.calls.clear()
        exporter.clear()

        events = _chat(client, conversation_id, "omega")

    assert language_model.calls == []
    assert [payload["text"] for name, payload in events if name == "delta"] == [
        STOPPED_TOO_LARGE
    ]
    turn = _spans_by_name(exporter, "turn")
    chats = _spans_by_name(exporter, "chat ")
    assert len(turn) == 1
    assert chats == []
    assert turn[0].attributes["app.status"] == "stopped"
    _assert_not_error(turn[0])


def test_ended_sibling_chat_keeps_ok_when_later_chat_is_cancelled(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    language_model.replies = [
        [ToolCall(id="call_weather", name="get_weather", arguments={"location": "Berlin"})],
        ["Hello", " there"],
    ]
    language_model.hold_after_chunks = 1

    async def instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.tools.asyncio.sleep", instant)
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        _cancel_while_holding(
            client, conversation_id, language_model.holding, language_model.release
        )

    chats = sorted(_spans_by_name(exporter, "chat "), key=lambda span: span.start_time)
    tools = _spans_by_name(exporter, "execute_tool ")
    turn = _spans_by_name(exporter, "turn")
    assert len(chats) == 2
    assert len(tools) == 1
    assert chats[0].attributes["app.status"] == "ok"
    assert tools[0].attributes["app.status"] == "ok"
    assert chats[1].attributes["app.status"] == "cancelled"
    assert turn[0].attributes["app.status"] == "cancelled"
    _assert_not_error(chats[0])
    _assert_not_error(chats[1])
    _assert_not_error(turn[0])


def test_cancel_during_summary_stream_marks_that_chat_cancelled(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    language_model.replies = [[text_with_tokens(150)], ["Noted."]]
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        for prompt in ("alpha", "beta", "gamma", "delta"):
            _chat(client, conversation_id, prompt)
        exporter.clear()
        client.app.state.context_window = 200
        language_model.replies = [["Kept."]]
        language_model.hold_after_chunks = 0
        language_model.holding.clear()
        language_model.release.clear()
        _cancel_while_holding(
            client, conversation_id, language_model.holding, language_model.release
        )

    chats = _spans_by_name(exporter, "chat ")
    turn = _spans_by_name(exporter, "turn")
    assert len(chats) == 1
    assert chats[0].attributes["app.caller"] == "summary"
    assert chats[0].attributes["app.status"] == "cancelled"
    assert turn[0].attributes["app.status"] == "cancelled"
    _assert_not_error(chats[0])
    _assert_not_error(turn[0])
