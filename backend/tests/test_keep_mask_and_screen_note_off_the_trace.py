from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from fastapi.testclient import TestClient

from test_stream_assistant_reply import sse_events


SECRET = "123-45-6789"
MASK_NOTE = "Screen: masked 1 social security number"
COST_NOTE = "Screen: 1 model call, 1 token. Today 1 of 50,000."


def _client(tmp_path, monkeypatch, language_model, exporter: InMemorySpanExporter):
    database_path = tmp_path / "test.db"
    monkeypatch.setenv(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{database_path.as_posix()}",
    )
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


def _attribute_values(span) -> list[object]:
    return list((span.attributes or {}).values())


def test_masked_finished_turn_keeps_screen_and_leaves_secret_off_spans(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    language_model.replies = [["Noted."]]
    prompt = f"My number is {SECRET} please keep it"
    masked = "My number is [ssn] please keep it"

    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        events = _chat(client, conversation_id, prompt)
        detail = client.get(f"/api/conversations/{conversation_id}").json()

    assert ("prompt", {"text": masked}) in events
    assert ("screen", {"text": MASK_NOTE}) in events
    assert ("screen", {"text": COST_NOTE}) in events
    assert ("delta", {"text": "Noted."}) in events

    user, assistant = detail["messages"]
    assert user["content"] == masked
    assert SECRET not in user["content"]
    assert user["screen_notes"] == [MASK_NOTE]
    assert assistant["screen_notes"] == [COST_NOTE]

    spans = exporter.get_finished_spans()
    turn_spans = [span for span in spans if span.name == "turn"]
    chat_spans = [span for span in spans if span.name.startswith("chat ")]
    assert len(turn_spans) == 1
    assert len(chat_spans) == 1
    assert {span.name for span in spans} == {turn_spans[0].name, chat_spans[0].name}
    assert turn_spans[0].attributes["app.status"] == "ok"
    assert chat_spans[0].attributes["app.status"] == "ok"

    for span in spans:
        values = _attribute_values(span)
        assert SECRET not in values
        assert MASK_NOTE not in values
        assert COST_NOTE not in values
        assert prompt not in values
        for value in values:
            if isinstance(value, str):
                assert SECRET not in value
                assert MASK_NOTE not in value
                assert COST_NOTE not in value
                assert "Screen:" not in value
