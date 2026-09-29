import asyncio
import time

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode
from fastapi.testclient import TestClient

from app.llm import ToolCall
from test_compact_a_lead_call import COMPACTION_WINDOW, _is_summary, _seed
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


def _turn_and_chats(exporter: InMemorySpanExporter):
    spans = exporter.get_finished_spans()
    turns = [span for span in spans if span.name == "turn"]
    chats = [span for span in spans if span.name.startswith("chat ")]
    assert len(turns) == 1
    return turns[0], chats


def test_finished_lead_reply_emits_a_chat_span_under_the_turn(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    language_model.replies = [["Hello there"]]
    language_model.input_tokens = [12]
    language_model.output_tokens = [34]
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        events = _chat(client, conversation_id, "Say hello")

    assert ("delta", {"text": "Hello there"}) in events
    turn, chats = _turn_and_chats(exporter)
    assert len(chats) == 1
    chat = chats[0]
    assert chat.name == f"chat {MODEL_NAME}"
    assert chat.parent is not None
    assert chat.parent.span_id == turn.context.span_id
    assert chat.kind == SpanKind.INTERNAL
    assert chat.attributes["gen_ai.operation.name"] == "chat"
    assert chat.attributes["gen_ai.provider.name"] == "openai"
    assert chat.attributes["gen_ai.request.model"] == MODEL_NAME
    assert chat.attributes["gen_ai.usage.input_tokens"] == 12
    assert chat.attributes["gen_ai.usage.output_tokens"] == 34
    assert chat.attributes["app.caller"] == "lead"
    assert chat.attributes["app.status"] == "ok"
    assert chat.status.status_code == StatusCode.OK
    assert "error.type" not in (chat.attributes or {})


def test_chat_span_ends_when_the_stream_ends_before_tool_work(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    sleep_finished_ns: list[int] = []

    async def slow_tool(name: str, arguments: dict) -> dict:
        await asyncio.sleep(0.2)
        sleep_finished_ns.append(time.time_ns())
        return {
            "temperature": 21,
            "condition": "Sunny",
            "humidity": "45%",
            "location": arguments.get("location", ""),
        }

    monkeypatch.setattr("app.conversations.run_tool", slow_tool)
    language_model.replies = [
        [
            ToolCall(
                id="call_weather",
                name="get_weather",
                arguments={"location": "Berlin"},
            )
        ],
        ["Sunny."],
    ]
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        _chat(client, conversation_id, "Weather?")

    turn, chats = _turn_and_chats(exporter)
    lead_chats = [span for span in chats if span.attributes.get("app.caller") == "lead"]
    assert len(lead_chats) == 2
    first = min(lead_chats, key=lambda span: span.start_time)
    assert first.parent is not None
    assert first.parent.span_id == turn.context.span_id
    assert sleep_finished_ns
    assert first.end_time < sleep_finished_ns[0]


def test_second_lead_chat_after_tools_is_a_sibling_under_the_turn(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()

    async def instant_tool(name: str, arguments: dict) -> dict:
        return {
            "temperature": 21,
            "condition": "Sunny",
            "humidity": "45%",
            "location": arguments.get("location", ""),
        }

    monkeypatch.setattr("app.conversations.run_tool", instant_tool)
    language_model.replies = [
        [
            ToolCall(
                id="call_weather",
                name="get_weather",
                arguments={"location": "Berlin"},
            )
        ],
        ["Sunny."],
    ]
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        _chat(client, conversation_id, "Weather?")

    turn, chats = _turn_and_chats(exporter)
    lead_chats = [span for span in chats if span.attributes.get("app.caller") == "lead"]
    assert len(lead_chats) == 2
    assert all(span.parent is not None for span in lead_chats)
    assert {span.parent.span_id for span in lead_chats} == {turn.context.span_id}
    assert lead_chats[0].context.span_id != lead_chats[1].context.span_id
    assert all(span.name == f"chat {MODEL_NAME}" for span in lead_chats)


def test_compaction_summary_chat_starts_before_the_lead_chat(
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
                return ["Kept the request."]
            return ["Lead answer"]

        language_model.reply_for = reply_for
        language_model.calls.clear()
        language_model.offered_tools.clear()
        _chat(client, conversation_id, "omega")

    turn, chats = _turn_and_chats(exporter)
    assert len(chats) == 2
    by_caller = {span.attributes["app.caller"]: span for span in chats}
    assert set(by_caller) == {"summary", "lead"}
    summary = by_caller["summary"]
    lead = by_caller["lead"]
    assert summary.parent is not None
    assert lead.parent is not None
    assert summary.parent.span_id == turn.context.span_id
    assert lead.parent.span_id == turn.context.span_id
    assert summary.name == f"chat {MODEL_NAME}"
    assert summary.attributes["app.status"] == "ok"
    assert summary.start_time < lead.start_time


def test_total_without_split_leaves_usage_attributes_unset_and_bills_total(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    language_model.replies = [["Hello"]]
    language_model.token_totals = [1200]
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        events = _chat(client, conversation_id, "Hi")
        note = "Screen: 1 model call, 1,200 tokens. Today 1,200 of 50,000."
        assert ("screen", {"text": note}) in events
        detail = client.get(f"/api/conversations/{conversation_id}").json()
        assert detail["messages"][1]["screen_notes"] == [note]

    _turn, chats = _turn_and_chats(exporter)
    assert len(chats) == 1
    chat = chats[0]
    assert chat.attributes["app.status"] == "ok"
    assert chat.status.status_code == StatusCode.OK
    assert "gen_ai.usage.input_tokens" not in (chat.attributes or {})
    assert "gen_ai.usage.output_tokens" not in (chat.attributes or {})


def test_stand_in_default_total_remains_one(tmp_path, monkeypatch, language_model):
    exporter = InMemorySpanExporter()
    language_model.replies = [["Ok"]]
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        events = _chat(client, conversation_id, "Hi")

    note = "Screen: 1 model call, 1 token. Today 1 of 50,000."
    assert ("screen", {"text": note}) in events
    _turn, chats = _turn_and_chats(exporter)
    assert len(chats) == 1
    assert "gen_ai.usage.input_tokens" not in (chats[0].attributes or {})
    assert "gen_ai.usage.output_tokens" not in (chats[0].attributes or {})
