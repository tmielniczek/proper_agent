from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode
from fastapi.testclient import TestClient

from app.llm import ProviderRejection, ToolCall
from app.tools import SPAWN_WORKERS
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


def _attribute_blob(span) -> str:
    return " ".join(str(value) for value in (span.attributes or {}).values())


def _spans(exporter: InMemorySpanExporter):
    return list(exporter.get_finished_spans())


def _lead_chat(exporter: InMemorySpanExporter):
    chats = [
        span
        for span in _spans(exporter)
        if span.name.startswith("chat ") and span.attributes.get("app.caller") == "lead"
    ]
    return min(chats, key=lambda span: span.start_time)


def _spawn_span(exporter: InMemorySpanExporter):
    matches = [
        span
        for span in _spans(exporter)
        if span.name == f"execute_tool {SPAWN_WORKERS}"
    ]
    assert len(matches) == 1
    return matches[0]


def _worker_chats(exporter: InMemorySpanExporter):
    return [
        span
        for span in _spans(exporter)
        if span.name.startswith("chat ") and span.attributes.get("app.caller") == "worker"
    ]


def _worker_tool_spans(exporter: InMemorySpanExporter):
    return [
        span
        for span in _spans(exporter)
        if span.name.startswith("execute_tool ")
        and span.attributes.get("gen_ai.tool.name") != SPAWN_WORKERS
    ]


def test_spawn_workers_hangs_off_the_lead_chat_that_requested_it(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    _instant_sleep(monkeypatch)
    language_model.replies = [
        [_spawn(["weather in Berlin"])],
        ["Sunny in Berlin"],
        ["Done."],
    ]
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        _chat(client, conversation_id, "Weather in Berlin?")

    lead = _lead_chat(exporter)
    spawn = _spawn_span(exporter)
    assert spawn.parent is not None
    assert spawn.parent.span_id == lead.context.span_id
    assert spawn.kind == SpanKind.INTERNAL
    assert spawn.attributes["gen_ai.operation.name"] == "execute_tool"
    assert spawn.attributes["gen_ai.tool.name"] == SPAWN_WORKERS
    assert spawn.attributes["app.status"] == "ok"
    assert spawn.status.status_code == StatusCode.OK
    assert "error.type" not in (spawn.attributes or {})
    assert lead.end_time < spawn.start_time


def test_worker_chat_and_tool_hang_off_spawn_and_worker_chat(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    _instant_sleep(monkeypatch)
    language_model.replies = [
        [_spawn(["weather in Berlin", "weather in Paris"])],
        [ToolCall(id="call_berlin", name="get_weather", arguments={"location": "Berlin"})],
        [ToolCall(id="call_paris", name="get_weather", arguments={"location": "Paris"})],
        ["Sunny in Berlin"],
        ["Rainy in Paris"],
        ["Both done."],
    ]
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        _chat(client, conversation_id, "Compare Berlin and Paris")

    spawn = _spawn_span(exporter)
    workers = _worker_chats(exporter)
    # Each worker: one chat that requests the tool, then one chat for the final text.
    assert len(workers) == 4
    for chat in workers:
        assert chat.parent is not None
        assert chat.parent.span_id == spawn.context.span_id
        assert chat.name == f"chat {MODEL_NAME}"
        assert chat.kind == SpanKind.INTERNAL
        assert chat.attributes["gen_ai.operation.name"] == "chat"
        assert chat.attributes["gen_ai.provider.name"] == "openai"
        assert chat.attributes["gen_ai.request.model"] == MODEL_NAME
        assert chat.attributes["app.caller"] == "worker"
        assert chat.attributes["app.status"] == "ok"
        assert chat.status.status_code == StatusCode.OK
        assert "error.type" not in (chat.attributes or {})

    tools = _worker_tool_spans(exporter)
    assert len(tools) == 2
    worker_ids = {chat.context.span_id for chat in workers}
    for tool in tools:
        assert tool.parent is not None
        assert tool.parent.span_id in worker_ids
        assert tool.name == "execute_tool get_weather"
        assert tool.attributes["gen_ai.operation.name"] == "execute_tool"
        assert tool.attributes["gen_ai.tool.name"] == "get_weather"
        assert tool.attributes["app.status"] == "ok"
        parent_chat = next(
            chat for chat in workers if chat.context.span_id == tool.parent.span_id
        )
        assert parent_chat.end_time < tool.start_time


def test_tasks_past_the_fifth_add_no_worker_span_and_count_as_refused(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    _instant_sleep(monkeypatch)
    tasks = [f"city {number}" for number in range(1, 8)]
    language_model.replies = [
        [_spawn(tasks)],
        ["one"],
        ["two"],
        ["three"],
        ["four"],
        ["five"],
        ["Five cities."],
    ]
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        _chat(client, conversation_id, "Check seven cities")

    spawn = _spawn_span(exporter)
    assert spawn.attributes["app.refused_tasks"] == 2
    assert spawn.attributes["app.status"] == "ok"
    workers = _worker_chats(exporter)
    assert len(workers) == 5  # five final-text chats; none for refused tasks
    blob = " ".join(_attribute_blob(span) for span in [spawn, *workers])
    assert "city 6" not in blob
    assert "city 7" not in blob


def test_spawn_with_no_refused_task_sets_refused_tasks_to_zero(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    _instant_sleep(monkeypatch)
    language_model.replies = [
        [_spawn(["weather in Berlin"])],
        ["Sunny"],
        ["Done."],
    ]
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        _chat(client, conversation_id, "Weather?")

    spawn = _spawn_span(exporter)
    assert spawn.attributes["app.refused_tasks"] == 0
    assert spawn.attributes["app.status"] == "ok"


def test_task_text_absent_from_spawn_and_worker_chat(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    _instant_sleep(monkeypatch)
    task = "weather in Berlin secret-task-phrase"
    language_model.replies = [
        [_spawn([task])],
        [ToolCall(id="call_weather", name="get_weather", arguments={"location": "Berlin"})],
        ["Sunny"],
        ["Done."],
    ]
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        _chat(client, conversation_id, "Weather?")

    spawn = _spawn_span(exporter)
    workers = _worker_chats(exporter)
    assert len(workers) == 2
    blob = " ".join(_attribute_blob(span) for span in [spawn, *workers])
    assert task not in blob
    assert "secret-task-phrase" not in blob
    assert "Berlin" not in blob
    tools = _worker_tool_spans(exporter)
    assert "Berlin" not in _attribute_blob(tools[0])
    assert "Sunny" not in _attribute_blob(tools[0])


def test_spawn_that_returns_its_batch_stays_ok_when_a_worker_fails(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    _instant_sleep(monkeypatch)
    language_model.replies = [
        [_spawn(["weather in Berlin", "weather in Paris"])],
        [ProviderRejection("The request was rate-limited")],
        ["Sunny in Paris"],
        ["Paris is sunny."],
    ]
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        _chat(client, conversation_id, "Compare Berlin and Paris")

    spawn = _spawn_span(exporter)
    assert spawn.attributes["app.status"] == "ok"
    assert spawn.status.status_code == StatusCode.OK
    assert "error.type" not in (spawn.attributes or {})
    assert spawn.attributes["app.refused_tasks"] == 0
    workers = _worker_chats(exporter)
    assert len(workers) == 1
    assert workers[0].attributes["app.status"] == "ok"


def test_blank_task_starts_no_worker_span_and_leaves_spawn_ok(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    _instant_sleep(monkeypatch)
    language_model.replies = [
        [_spawn(["weather in Berlin", "   ", "weather in Paris"])],
        ["Sunny in Berlin"],
        ["Rainy in Paris"],
        ["Two forecasts."],
    ]
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        _chat(client, conversation_id, "Two cities and a gap")

    spawn = _spawn_span(exporter)
    assert spawn.attributes["app.status"] == "ok"
    assert spawn.attributes["app.refused_tasks"] == 0
    assert len(_worker_chats(exporter)) == 2


def test_missing_empty_or_non_list_tasks_emit_error_spawn_with_no_worker(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    _instant_sleep(monkeypatch)

    cases = [
        ToolCall(id="call_missing", name=SPAWN_WORKERS, arguments={}),
        _spawn([]),
        ToolCall(id="call_bad", name=SPAWN_WORKERS, arguments={"tasks": "not-a-list"}),
    ]
    for index, call in enumerate(cases):
        language_model.replies = [[call], [f"Need a task {index}."]]
        exporter.clear()
        with _client(tmp_path, monkeypatch, language_model, exporter) as client:
            conversation_id = client.post("/api/conversations").json()["id"]
            _chat(client, conversation_id, f"Spawn case {index}")

        spawn = _spawn_span(exporter)
        assert spawn.attributes["app.status"] == "error"
        assert spawn.attributes["error.type"] == "error"
        assert spawn.status.status_code == StatusCode.ERROR
        assert spawn.attributes["gen_ai.operation.name"] == "execute_tool"
        assert spawn.attributes["gen_ai.tool.name"] == SPAWN_WORKERS
        assert _worker_chats(exporter) == []
        assert "app.refused_tasks" not in (spawn.attributes or {})


def test_blocked_worker_tool_adds_no_tool_span_and_leaves_chat_ok(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    _instant_sleep(monkeypatch)
    language_model.replies = [
        [_spawn(["delegate further", "remember something"])],
        [ToolCall(id="nested", name=SPAWN_WORKERS, arguments={"tasks": ["nope"]})],
        [ToolCall(id="memory", name="long_term_memory", arguments={"fact": "secret"})],
        ["Could not split."],
    ]
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        _chat(client, conversation_id, "Split and remember")

    spawn = _spawn_span(exporter)
    assert spawn.attributes["app.status"] == "ok"
    workers = _worker_chats(exporter)
    assert len(workers) == 2
    for chat in workers:
        assert chat.attributes["app.status"] == "ok"
        assert chat.status.status_code == StatusCode.OK
    assert _worker_tool_spans(exporter) == []
    blob = " ".join(_attribute_blob(span) for span in workers)
    assert "nope" not in blob
    assert "secret" not in blob
