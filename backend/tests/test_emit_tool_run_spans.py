import asyncio

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode
from fastapi.testclient import TestClient

from app.llm import ToolCall
from test_stream_assistant_reply import sse_events

MODEL_NAME = "gpt-5-nano"
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


def _instant_sleep(monkeypatch) -> None:
    async def sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.tools.asyncio.sleep", sleep)


def _attribute_blob(span) -> str:
    return " ".join(str(value) for value in (span.attributes or {}).values())


def _tool_spans(exporter: InMemorySpanExporter):
    return [span for span in exporter.get_finished_spans() if span.name.startswith("execute_tool ")]


def _requesting_chat(exporter: InMemorySpanExporter):
    chats = [
        span
        for span in exporter.get_finished_spans()
        if span.name.startswith("chat ") and span.attributes.get("app.caller") == "lead"
    ]
    return min(chats, key=lambda span: span.start_time)


def _assert_ok_tool_span(span, *, tool: str, parent_chat):
    assert span.name == f"execute_tool {tool}"
    assert span.parent is not None
    assert span.parent.span_id == parent_chat.context.span_id
    assert span.kind == SpanKind.INTERNAL
    assert span.attributes["gen_ai.operation.name"] == "execute_tool"
    assert span.attributes["gen_ai.tool.name"] == tool
    assert span.attributes["app.status"] == "ok"
    assert span.status.status_code == StatusCode.OK
    assert "error.type" not in (span.attributes or {})


def test_get_weather_emits_execute_tool_under_requesting_chat(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    _instant_sleep(monkeypatch)
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
        _chat(client, conversation_id, "Weather in Berlin?")

    chat = _requesting_chat(exporter)
    tools = _tool_spans(exporter)
    assert len(tools) == 1
    tool = tools[0]
    _assert_ok_tool_span(tool, tool="get_weather", parent_chat=chat)
    assert chat.end_time < tool.start_time
    blob = _attribute_blob(tool)
    assert "Berlin" not in blob
    assert "Sunny" not in blob
    assert "21" not in blob
    assert "call_weather" not in blob


def test_search_database_and_calculator_emit_named_tool_spans(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    _instant_sleep(monkeypatch)
    language_model.replies = [
        [
            ToolCall(
                id="call_search",
                name="search_database",
                arguments={"query": "open invoices"},
            )
        ],
        ["Found one."],
        [
            ToolCall(
                id="call_calc",
                name="calculator",
                arguments={"expression": "(2 + 3) * 4"},
            )
        ],
        ["Twenty."],
    ]
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        _chat(client, conversation_id, "Search invoices")
        _chat(client, conversation_id, "Calculate")

    tools = _tool_spans(exporter)
    by_name = {span.attributes["gen_ai.tool.name"]: span for span in tools}
    assert set(by_name) == {"search_database", "calculator"}

    search = by_name["search_database"]
    calc = by_name["calculator"]
    assert search.name == "execute_tool search_database"
    assert calc.name == "execute_tool calculator"
    assert search.attributes["gen_ai.operation.name"] == "execute_tool"
    assert calc.attributes["gen_ai.operation.name"] == "execute_tool"
    assert search.attributes["app.status"] == "ok"
    assert calc.attributes["app.status"] == "ok"
    assert "open invoices" not in _attribute_blob(search)
    assert "Mock data" not in _attribute_blob(search)
    assert "(2 + 3) * 4" not in _attribute_blob(calc)
    assert "20" not in _attribute_blob(calc)


def test_bad_calculator_expression_stays_ok(tmp_path, monkeypatch, language_model):
    exporter = InMemorySpanExporter()
    _instant_sleep(monkeypatch)
    expression = "__import__('os').system('ls')"
    language_model.replies = [
        [
            ToolCall(
                id="call_calc",
                name="calculator",
                arguments={"expression": expression},
            )
        ],
        ["Could not evaluate."],
    ]
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        _chat(client, conversation_id, "Run this")

    tools = _tool_spans(exporter)
    assert len(tools) == 1
    tool = tools[0]
    chat = _requesting_chat(exporter)
    _assert_ok_tool_span(tool, tool="calculator", parent_chat=chat)
    assert expression not in _attribute_blob(tool)
    assert "42" not in _attribute_blob(tool)


def test_memory_save_emits_tool_span_without_fact_text(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()
    _instant_sleep(monkeypatch)
    fact = "The user lives in Berlin."
    language_model.replies = [
        [
            ToolCall(
                id="call_memory",
                name="long_term_memory",
                arguments={"fact": f"  {fact}  "},
            )
        ],
        ["I will remember that."],
    ]
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        _chat(client, conversation_id, "Remember that I live in Berlin")

    chat = _requesting_chat(exporter)
    tools = _tool_spans(exporter)
    assert len(tools) == 1
    tool = tools[0]
    _assert_ok_tool_span(tool, tool="long_term_memory", parent_chat=chat)
    assert chat.end_time < tool.start_time
    blob = _attribute_blob(tool)
    assert fact not in blob
    assert "Berlin" not in blob
    assert "saved" not in blob


def test_two_parallel_tool_runs_overlap_under_same_chat(
    tmp_path, monkeypatch, language_model
):
    exporter = InMemorySpanExporter()

    async def overlap(_seconds: float) -> None:
        await _real_sleep(0.05)

    monkeypatch.setattr("app.tools.asyncio.sleep", overlap)
    language_model.replies = [
        [
            ToolCall(
                id="call_berlin",
                name="get_weather",
                arguments={"location": "Berlin"},
            ),
            ToolCall(
                id="call_paris",
                name="get_weather",
                arguments={"location": "Paris"},
            ),
        ],
        ["Both sunny."],
    ]
    with _client(tmp_path, monkeypatch, language_model, exporter) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        _chat(client, conversation_id, "Weather in Berlin and Paris?")

    chat = _requesting_chat(exporter)
    tools = _tool_spans(exporter)
    assert len(tools) == 2
    for tool in tools:
        _assert_ok_tool_span(tool, tool="get_weather", parent_chat=chat)
        assert chat.end_time < tool.start_time
    first, second = tools
    assert first.start_time < second.end_time
    assert second.start_time < first.end_time
    blob = " ".join(_attribute_blob(tool) for tool in tools)
    assert "Berlin" not in blob
    assert "Paris" not in blob
