import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.llm import ToolCall
from test_spawn_workers import _real_sleep
from test_stream_assistant_reply import sse_events

BERLIN_WEATHER = {
    "temperature": 21,
    "condition": "Sunny",
    "humidity": "45%",
    "location": "Berlin",
}


def test_weather_call_shows_progress_then_saves_the_forecast(client, language_model):
    language_model.replies = [
        [ToolCall(id="call_weather", name="get_weather", arguments={"location": "Berlin"})],
        ["Sunny", " in Berlin."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]

    with client.stream(
        "POST",
        f"/api/conversations/{conversation_id}/chat",
        json={"prompt": "What is the weather in Berlin?"},
    ) as response:
        assert response.status_code == 200
        events = sse_events(response.read().decode())

    assert [(name, payload) for name, payload in events if name == "tool_start"] == [
        ("tool_start", {"tool": "get_weather", "display_text": "Checking weather..."}),
    ]
    assert [(name, payload) for name, payload in events if name == "tool_end"] == [
        ("tool_end", {"tool": "get_weather"}),
    ]
    assert [name for name, _payload in events] == [
        "tool_start",
        "tool_end",
        "delta",
        "delta",
        "done",
    ]

    detail = client.get(f"/api/conversations/{conversation_id}").json()
    messages = detail["messages"]
    assert [message["role"] for message in messages] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    tool_call = messages[1]["tool_calls"][0]
    assert tool_call["id"] == "call_weather"
    assert tool_call["function"]["name"] == "get_weather"
    assert json.loads(tool_call["function"]["arguments"]) == {"location": "Berlin"}
    assert messages[2]["tool_call_id"] == "call_weather"
    assert json.loads(messages[2]["content"]) == BERLIN_WEATHER
    assert messages[3]["content"] == "Sunny in Berlin."
    assert messages[3]["id"] == events[-1][1]["message_id"]

    continued = language_model.calls[1]
    assert continued[2]["role"] == "tool"
    assert continued[2]["tool_call_id"] == "call_weather"
    assert json.loads(continued[2]["content"]) == BERLIN_WEATHER


def test_database_search_shows_progress_and_saves_one_matching_record(client, language_model):
    language_model.replies = [
        [
            ToolCall(
                id="call_search",
                name="search_database",
                arguments={"query": "open invoices"},
            )
        ],
        ["Found one record."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]

    with client.stream(
        "POST",
        f"/api/conversations/{conversation_id}/chat",
        json={"prompt": "Search for open invoices"},
    ) as response:
        events = sse_events(response.read().decode())

    assert events[0] == (
        "tool_start",
        {"tool": "search_database", "display_text": "Searching database..."},
    )
    assert events[1][0] == "tool_end"
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert json.loads(detail["messages"][2]["content"]) == {
        "results": [{"id": 101, "record": "Mock data result for query: open invoices"}],
    }
    assert detail["messages"][3]["content"] == "Found one record."


def test_calculator_shows_progress_and_saves_the_value(client, language_model):
    language_model.replies = [
        [ToolCall(id="call_calc", name="calculator", arguments={"expression": "(2 + 3) * 4"})],
        ["The answer is 20."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]

    with client.stream(
        "POST",
        f"/api/conversations/{conversation_id}/chat",
        json={"prompt": "What is (2 + 3) * 4?"},
    ) as response:
        events = sse_events(response.read().decode())

    assert events[0] == (
        "tool_start",
        {"tool": "calculator", "display_text": "Calculating..."},
    )
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert json.loads(detail["messages"][2]["content"]) == {"result": 20}
    assert detail["messages"][3]["content"] == "The answer is 20."


def test_calculator_returns_42_when_the_expression_is_not_safe(client, language_model):
    language_model.replies = [
        [
            ToolCall(
                id="call_calc",
                name="calculator",
                arguments={"expression": "__import__('os').system('ls')"},
            )
        ],
        ["I could not evaluate that."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]
    client.post(
        f"/api/conversations/{conversation_id}/chat",
        json={"prompt": "Run this"},
    )

    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert json.loads(detail["messages"][2]["content"]) == {"result": 42}


def test_each_tool_waits_between_one_and_ten_seconds(client, language_model, monkeypatch):
    bounds: list[tuple[float, float]] = []
    waited: list[float] = []

    def uniform(low: float, high: float) -> float:
        bounds.append((low, high))
        return [4.5, 7.0][len(bounds) - 1]

    async def sleep(seconds: float) -> None:
        waited.append(seconds)

    monkeypatch.setattr("app.tools.random.uniform", uniform)
    monkeypatch.setattr("app.tools.asyncio.sleep", sleep)
    language_model.replies = [
        [
            ToolCall(id="call_weather", name="get_weather", arguments={"location": "Berlin"}),
            ToolCall(id="call_calc", name="calculator", arguments={"expression": "2+2"}),
        ],
        ["Both finished."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]
    client.post(
        f"/api/conversations/{conversation_id}/chat",
        json={"prompt": "Weather and 2+2"},
    )

    assert bounds == [(1.0, 10.0), (1.0, 10.0)]
    assert waited == [4.5, 7.0]


def test_tool_calls_in_one_reply_run_at_the_same_time(client, language_model, monkeypatch):
    state = {"current": 0, "max": 0}

    async def overlap(_seconds: float) -> None:
        state["current"] += 1
        state["max"] = max(state["max"], state["current"])
        await _real_sleep(0.05)
        state["current"] -= 1

    monkeypatch.setattr("app.tools.asyncio.sleep", overlap)
    language_model.replies = [
        [
            ToolCall(id="call_berlin", name="get_weather", arguments={"location": "Berlin"}),
            ToolCall(id="call_paris", name="get_weather", arguments={"location": "Paris"}),
        ],
        ["Both are sunny."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]

    with client.stream(
        "POST",
        f"/api/conversations/{conversation_id}/chat",
        json={"prompt": "Weather in Berlin and Paris"},
    ) as response:
        events = sse_events(response.read().decode())

    assert state["max"] == 2
    starts = [payload for name, payload in events if name == "tool_start"]
    assert [payload["call_id"] for payload in starts] == ["call_berlin", "call_paris"]
    assert [name for name, _payload in events[:4]] == [
        "tool_start",
        "tool_start",
        "tool_end",
        "tool_end",
    ]
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert [message["tool_call_id"] for message in detail["messages"] if message["role"] == "tool"] == [
        "call_berlin",
        "call_paris",
    ]


def test_later_turn_receives_the_stored_tool_result(client, language_model):
    language_model.replies = [
        [ToolCall(id="call_weather", name="get_weather", arguments={"location": "Berlin"})],
        ["It is sunny."],
        ["A light jacket is enough."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]
    client.post(
        f"/api/conversations/{conversation_id}/chat",
        json={"prompt": "What is the weather in Berlin?"},
    )
    client.post(
        f"/api/conversations/{conversation_id}/chat",
        json={"prompt": "Should I bring a coat?"},
    )

    assert language_model.calls[2] == [
        {"role": "user", "content": "What is the weather in Berlin?"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_weather",
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"location": "Berlin"}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_weather",
            "content": '{"temperature": 21, "condition": "Sunny", "humidity": "45%", "location": "Berlin"}',
        },
        {"role": "assistant", "content": "It is sunny."},
        {"role": "user", "content": "Should I bring a coat?"},
    ]


def test_provider_stream_offers_tools_and_runs_a_streamed_tool_call(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_NAME", "gpt-5-nano")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
    )
    completions = _ScriptedCompletions()
    monkeypatch.setattr(
        "app.llm.AsyncOpenAI",
        lambda **_kwargs: SimpleNamespace(chat=SimpleNamespace(completions=completions)),
    )

    from app.main import create_app

    with TestClient(create_app()) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        with client.stream(
            "POST",
            f"/api/conversations/{conversation_id}/chat",
            json={"prompt": "What is the weather in Berlin?"},
        ) as response:
            events = sse_events(response.read().decode())
        detail = client.get(f"/api/conversations/{conversation_id}").json()

    offered = [tool["function"]["name"] for tool in completions.calls[0]["tools"]]
    assert offered == [
        "get_weather",
        "search_database",
        "calculator",
        "spawn_workers",
        "long_term_memory",
    ]
    assert completions.calls[0]["tools"][3]["function"]["parameters"]["required"] == ["tasks"]
    assert completions.calls[0]["tools"][0]["function"]["parameters"]["required"] == ["location"]
    assert completions.calls[0]["tools"][1]["function"]["parameters"]["required"] == ["query"]
    assert completions.calls[0]["tools"][2]["function"]["parameters"]["required"] == ["expression"]
    assert events[0] == (
        "tool_start",
        {"tool": "get_weather", "display_text": "Checking weather..."},
    )
    assert json.loads(detail["messages"][2]["content"]) == BERLIN_WEATHER
    assert detail["messages"][3]["content"] == "It is sunny."
    assert json.loads(completions.calls[1]["messages"][2]["content"]) == BERLIN_WEATHER


class _ScriptedCompletions:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return _ChunkStream(
                [
                    _tool_chunk(0, call_id="call_weather", name="get_weather", arguments=""),
                    _tool_chunk(0, arguments='{"location":'),
                    _tool_chunk(0, arguments=' "Berlin"}'),
                ]
            )
        return _ChunkStream([_text_chunk("It is sunny.")])


class _ChunkStream:
    def __init__(self, chunks: list) -> None:
        self._chunks = chunks

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for chunk in self._chunks:
            yield chunk


def _text_chunk(text: str):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])


def _tool_chunk(index: int, call_id: str | None = None, name: str | None = None, arguments: str | None = None):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            index=index,
                            id=call_id,
                            function=SimpleNamespace(name=name, arguments=arguments),
                        )
                    ],
                )
            )
        ]
    )


@pytest.fixture(autouse=True)
def instant_tool_wait(monkeypatch):
    try:
        import app.tools as tools
    except ModuleNotFoundError:
        return

    async def instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr(tools.random, "uniform", lambda _low, _high: 1.0)
    monkeypatch.setattr(tools.asyncio, "sleep", instant)
