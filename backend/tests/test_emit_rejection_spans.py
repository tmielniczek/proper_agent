from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from fastapi.testclient import TestClient

from app.compaction import STOPPED_TOO_LARGE
from app.llm import ProviderRejection, ToolCall
from app.tools import SPAWN_WORKERS
from test_compact_a_lead_call import COMPACTION_WINDOW, _is_summary, _seed
from test_spawn_workers import _spawn
from test_stream_assistant_reply import sse_events

MODEL_NAME = "gpt-5-nano"


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


def _instant_sleep(monkeypatch) -> None:
    async def sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.tools.asyncio.sleep", sleep)


def _spans(exporter: InMemorySpanExporter):
    return list(exporter.get_finished_spans())


def _turn(exporter: InMemorySpanExporter):
    matches = [span for span in _spans(exporter) if span.name == "turn"]
    assert len(matches) == 1
    return matches[0]


def _chats(exporter: InMemorySpanExporter, caller: str):
    return [
        span
        for span in _spans(exporter)
        if span.name.startswith("chat ") and span.attributes.get("app.caller") == caller
    ]


def _attribute_blob(span) -> str:
    return " ".join(str(value) for value in (span.attributes or {}).values())


def _assert_provider_rejection(span, *, error_type: str) -> None:
    assert span.attributes["app.status"] == "provider_rejection"
    assert span.attributes["error.type"] == error_type
    assert span.status.status_code == StatusCode.ERROR


def _assert_error(span, *, error_type: str) -> None:
    assert span.attributes["app.status"] == "error"
    assert span.attributes["error.type"] == error_type
    assert span.status.status_code == StatusCode.ERROR


def test_lead_401_marks_chat_and_turn_provider_rejection_and_still_drops(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    language_model.replies = [
        [ProviderRejection("The API key was rejected", status_code=401)],
    ]
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        events = _chat(client, conversation_id, "Say hello")
        detail = client.get(f"/api/conversations/{conversation_id}").json()

    assert events[-1] == ("error", {"error": "The API key was rejected"})
    assert detail["messages"] == []
    chats = _chats(exporter, "lead")
    assert len(chats) == 1
    _assert_provider_rejection(chats[0], error_type="401")
    _assert_error(_turn(exporter), error_type="401")


def test_lead_429_marks_chat_and_turn_with_rate_limit_text(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    language_model.replies = [
        [ProviderRejection("The request was rate-limited", status_code=429)],
    ]
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        events = _chat(client, conversation_id, "Say hello")

    assert events[-1] == ("error", {"error": "The request was rate-limited"})
    chats = _chats(exporter, "lead")
    assert len(chats) == 1
    _assert_provider_rejection(chats[0], error_type="429")
    _assert_error(_turn(exporter), error_type="429")


def test_unknown_lead_tool_marks_tool_and_turn_error(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    _instant_sleep(monkeypatch)
    language_model.replies = [
        [
            ToolCall(
                id="call_unknown",
                name="not_a_tool",
                arguments={"secret": "hide-me"},
            )
        ],
    ]
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        _chat(client, conversation_id, "Use a missing tool")

    tools = [
        span for span in _spans(exporter) if span.name == "execute_tool not_a_tool"
    ]
    assert len(tools) == 1
    tool = tools[0]
    _assert_error(tool, error_type="ValueError")
    assert tool.attributes["gen_ai.tool.name"] == "not_a_tool"
    assert "hide-me" not in _attribute_blob(tool)
    assert "secret" not in _attribute_blob(tool)
    _assert_error(_turn(exporter), error_type="ValueError")
    lead = _chats(exporter, "lead")[0]
    assert lead.attributes["app.status"] == "ok"
    assert "error.type" not in (lead.attributes or {})
    assert lead.status.status_code == StatusCode.OK


def test_unexpected_exception_marks_failed_span_and_turn(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    language_model.replies = [[RuntimeError("boom")]]
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        events = _chat(client, conversation_id, "Blow up")

    assert events[-1] == ("error", {"error": "boom"})
    chats = _chats(exporter, "lead")
    assert len(chats) == 1
    _assert_error(chats[0], error_type="RuntimeError")
    _assert_error(_turn(exporter), error_type="RuntimeError")


def test_summary_rejection_marks_chat_provider_rejection_and_turn_stopped(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        _seed(client, language_model, conversation_id, long_middle=True)
        client.app.state.context_window = COMPACTION_WINDOW
        exporter.clear()

        def reply_for(messages):
            if _is_summary(messages):
                return [ProviderRejection("The API key was rejected", status_code=401)]
            return ["Should not run"]

        language_model.reply_for = reply_for
        language_model.calls.clear()
        language_model.offered_tools.clear()
        events = _chat(client, conversation_id, "omega")

    assert [payload["text"] for name, payload in events if name == "delta"] == [
        STOPPED_TOO_LARGE
    ]
    summaries = _chats(exporter, "summary")
    assert len(summaries) == 1
    _assert_provider_rejection(summaries[0], error_type="401")
    turn = _turn(exporter)
    assert turn.attributes["app.status"] == "stopped"
    assert turn.status.status_code == StatusCode.OK
    assert "error.type" not in (turn.attributes or {})
    assert _chats(exporter, "lead") == []


def test_worker_rejection_stays_on_worker_spawn_and_turn_ok(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    _instant_sleep(monkeypatch)
    task = "weather in Berlin"
    language_model.replies = [
        [_spawn([task, "weather in Paris"])],
        [ProviderRejection("The request was rate-limited", status_code=429)],
        ["Sunny in Paris"],
        ["Paris is sunny."],
    ]
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        _chat(client, conversation_id, "Compare Berlin and Paris")

    spawn = [
        span
        for span in _spans(exporter)
        if span.name == f"execute_tool {SPAWN_WORKERS}"
    ][0]
    assert spawn.attributes["app.status"] == "ok"
    assert spawn.status.status_code == StatusCode.OK
    assert "error.type" not in (spawn.attributes or {})
    workers = _chats(exporter, "worker")
    rejected = [
        span for span in workers if span.attributes["app.status"] == "provider_rejection"
    ]
    assert len(rejected) == 1
    _assert_provider_rejection(rejected[0], error_type="429")
    assert task not in _attribute_blob(rejected[0])
    assert task not in _attribute_blob(spawn)
    turn = _turn(exporter)
    assert turn.attributes["app.status"] == "ok"
    assert turn.status.status_code == StatusCode.OK
    assert "error.type" not in (turn.attributes or {})
    lead = _chats(exporter, "lead")
    assert all(span.attributes["app.status"] == "ok" for span in lead)
