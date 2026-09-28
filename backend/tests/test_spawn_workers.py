import asyncio
import json
import threading

import pytest
from app.llm import ProviderRejection, ToolCall
from app.tools import SPAWN_WORKERS, worker_tool_label
from test_stream_assistant_reply import sse_events

_real_sleep = asyncio.sleep
TOOL_NAMES = ["get_weather", "search_database", "calculator"]
WORKER_PREFACE = {
    "role": "system",
    "content": (
        "Answer the task. Use get_weather, search_database, and calculator when you need them. "
        "Your final message is the whole result."
    ),
}


def _spawn(tasks: list[str], call_id: str = "call_spawn") -> ToolCall:
    return ToolCall(id=call_id, name=SPAWN_WORKERS, arguments={"tasks": tasks})


def _names(tools: list[dict] | None) -> list[str]:
    assert tools is not None
    return [tool["function"]["name"] for tool in tools]


def test_spawn_runs_independent_workers_and_stores_only_their_final_text(
    client, language_model, monkeypatch
):
    state = {"current": 0, "max": 0}

    async def overlap(_seconds: float) -> None:
        state["current"] += 1
        state["max"] = max(state["max"], state["current"])
        await _real_sleep(0.05)
        state["current"] -= 1

    monkeypatch.setattr("app.tools.asyncio.sleep", overlap)
    language_model.replies = [
        [_spawn(["weather in Berlin", "weather in Paris"])],
        [ToolCall(id="call_berlin", name="get_weather", arguments={"location": "Berlin"})],
        [ToolCall(id="call_paris", name="get_weather", arguments={"location": "Paris"})],
        ["Sunny in Berlin"],
        ["Rainy in Paris"],
        ["Berlin is sunny and Paris is rainy."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]

    with client.stream(
        "POST",
        f"/api/conversations/{conversation_id}/chat",
        json={"prompt": "Compare Berlin and Paris"},
    ) as response:
        events = sse_events(response.read().decode())

    assert state["max"] == 2
    assert _names(language_model.offered_tools[0]) == [
        *TOOL_NAMES,
        SPAWN_WORKERS,
        "long_term_memory",
    ]
    assert _names(language_model.offered_tools[1]) == TOOL_NAMES
    assert language_model.calls[1] == [
        WORKER_PREFACE,
        {"role": "user", "content": "weather in Berlin"},
    ]
    assert language_model.calls[2][-1] == {"role": "user", "content": "weather in Paris"}

    starts = [payload for name, payload in events if name == "tool_start"]
    assert starts[0] == {"tool": SPAWN_WORKERS, "display_text": "Asking 2 workers..."}
    assert starts[1]["display_text"] == "Checking weather... · weather in Berlin"
    assert starts[2]["display_text"] == "Checking weather... · weather in Paris"
    assert starts[1]["call_id"] != starts[2]["call_id"]
    ends = {
        payload["call_id"]: payload["tool"]
        for name, payload in events
        if name == "tool_end" and "call_id" in payload
    }
    assert ends[starts[1]["call_id"]] == "get_weather"
    assert ends[starts[2]["call_id"]] == "get_weather"
    assert [name for name, _payload in events if name == "refused_task"] == []

    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert [message["role"] for message in detail["messages"]] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    assert json.loads(detail["messages"][2]["content"]) == {
        "workers": [
            {"task": "weather in Berlin", "text": "Sunny in Berlin"},
            {"task": "weather in Paris", "text": "Rainy in Paris"},
        ],
        "refused": [],
    }
    assert detail["messages"][3]["content"] == "Berlin is sunny and Paris is rainy."


def test_tasks_past_the_fifth_are_refused_and_the_first_five_start(client, language_model):
    tasks = [f"city {number}" for number in range(1, 8)]
    language_model.replies = [
        [_spawn(tasks)],
        ["one"],
        ["two"],
        ["three"],
        ["four"],
        ["five"],
        ["Five cities, two left out."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]

    with client.stream(
        "POST",
        f"/api/conversations/{conversation_id}/chat",
        json={"prompt": "Check seven cities"},
    ) as response:
        events = sse_events(response.read().decode())

    assert events[0] == ("prompt", {"text": "Check seven cities"})
    assert events[1] == (
        "tool_start",
        {"tool": SPAWN_WORKERS, "display_text": "Asking 5 workers..."},
    )
    assert events[2] == ("refused_task", {"display_text": "Not started · city 6"})
    assert events[3] == ("refused_task", {"display_text": "Not started · city 7"})
    assert events[4][0] == "tool_end"
    worker_calls = [
        call[-1]["content"]
        for call in language_model.calls
        if call[-1]["role"] == "user" and call[-1]["content"] in tasks
    ]
    assert worker_calls == ["city 1", "city 2", "city 3", "city 4", "city 5"]
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    stored = json.loads(detail["messages"][2]["content"])
    assert [worker["text"] for worker in stored["workers"]] == [
        "one",
        "two",
        "three",
        "four",
        "five",
    ]
    assert stored["refused"] == ["city 6", "city 7"]


def test_a_blank_slot_is_an_error_and_the_other_tasks_still_start(client, language_model):
    language_model.replies = [
        [_spawn(["weather in Berlin", "   ", "weather in Paris"])],
        ["Sunny in Berlin"],
        ["Rainy in Paris"],
        ["Two forecasts."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]

    with client.stream(
        "POST",
        f"/api/conversations/{conversation_id}/chat",
        json={"prompt": "Two cities and a gap"},
    ) as response:
        events = sse_events(response.read().decode())

    assert events[0] == ("prompt", {"text": "Two cities and a gap"})
    assert events[1] == (
        "tool_start",
        {"tool": SPAWN_WORKERS, "display_text": "Asking 2 workers..."},
    )
    assert [name for name, _payload in events if name == "refused_task"] == []
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert json.loads(detail["messages"][2]["content"]) == {
        "workers": [
            {"task": "weather in Berlin", "text": "Sunny in Berlin"},
            {"task": "   ", "error": "Task is blank."},
            {"task": "weather in Paris", "text": "Rainy in Paris"},
        ],
        "refused": [],
    }


def test_an_empty_spawn_returns_an_error_and_starts_nothing(client, language_model):
    language_model.replies = [
        [_spawn([])],
        ["I need a task."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]

    with client.stream(
        "POST",
        f"/api/conversations/{conversation_id}/chat",
        json={"prompt": "Spawn nobody"},
    ) as response:
        events = sse_events(response.read().decode())

    assert [name for name, _payload in events if name in {"tool_start", "refused_task"}] == []
    assert len(language_model.calls) == 2
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert json.loads(detail["messages"][2]["content"]) == {
        "error": "Spawn needs at least one task.",
    }
    assert detail["messages"][3]["content"] == "I need a task."


def test_a_worker_failure_leaves_the_other_workers_and_the_prompt(client, language_model):
    language_model.replies = [
        [_spawn(["weather in Berlin", "weather in Paris"])],
        [ProviderRejection("The request was rate-limited")],
        ["Sunny in Paris"],
        ["Paris is sunny. Berlin was rate-limited."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]
    client.post(
        f"/api/conversations/{conversation_id}/chat",
        json={"prompt": "Compare Berlin and Paris"},
    )

    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][0]["content"] == "Compare Berlin and Paris"
    assert json.loads(detail["messages"][2]["content"]) == {
        "workers": [
            {"task": "weather in Berlin", "error": "The request was rate-limited"},
            {"task": "weather in Paris", "text": "Sunny in Paris"},
        ],
        "refused": [],
    }
    assert detail["messages"][3]["content"] == "Paris is sunny. Berlin was rate-limited."


def test_a_worker_cannot_spawn_another_worker(client, language_model):
    language_model.replies = [
        [_spawn(["delegate further"])],
        [ToolCall(id="nested", name=SPAWN_WORKERS, arguments={"tasks": ["nope"]})],
        ["I could not split that further."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]
    client.post(
        f"/api/conversations/{conversation_id}/chat",
        json={"prompt": "Split this again"},
    )

    assert _names(language_model.offered_tools[1]) == TOOL_NAMES
    assert len(language_model.calls) == 3
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert json.loads(detail["messages"][2]["content"])["workers"] == [
        {"task": "delegate further", "error": "Workers cannot start workers."},
    ]


def test_a_second_spawn_starts_after_the_first_batch_finishes(
    client, language_model, monkeypatch
):
    holding = threading.Event()
    release = threading.Event()

    async def sleep(_seconds: float) -> None:
        holding.set()
        while not release.is_set():
            await _real_sleep(0.01)

    monkeypatch.setattr("app.tools.asyncio.sleep", sleep)
    language_model.replies = [
        [
            _spawn(["weather in Berlin"], "call_first"),
            _spawn(["summarise the forecast"], "call_second"),
        ],
        [ToolCall(id="call_weather", name="get_weather", arguments={"location": "Berlin"})],
        ["Sunny in Berlin"],
        ["The forecast is sunny."],
        ["Berlin is sunny."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]
    body: dict = {}

    def read_stream() -> None:
        try:
            with client.stream(
                "POST",
                f"/api/conversations/{conversation_id}/chat",
                json={"prompt": "Weather, then summarise"},
            ) as response:
                body["text"] = response.read().decode()
        except Exception as exc:
            body["error"] = exc

    reader = threading.Thread(target=read_stream)
    reader.start()
    try:
        assert holding.wait(timeout=2)
        assert [
            call[-1]["content"] for call in language_model.calls if call[0]["role"] == "system"
        ] == ["weather in Berlin"]
        release.set()
        reader.join(timeout=2)
        assert not reader.is_alive()
        assert body.get("error") is None
    finally:
        release.set()
        reader.join(timeout=2)

    worker_tasks = [
        call[-1]["content"]
        for call in language_model.calls
        if call[0]["role"] == "system" and call[-1]["role"] == "user"
    ]
    assert worker_tasks == ["weather in Berlin", "summarise the forecast"]
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert [message["tool_call_id"] for message in detail["messages"] if message["role"] == "tool"] == [
        "call_first",
        "call_second",
    ]


def test_cancel_during_a_worker_tool_keeps_only_the_prompt(client, language_model, monkeypatch):
    holding = threading.Event()
    release = threading.Event()
    tool_finished = threading.Event()

    async def sleep(_seconds: float) -> None:
        holding.set()
        while not release.is_set():
            await _real_sleep(0.01)
        tool_finished.set()

    monkeypatch.setattr("app.tools.asyncio.sleep", sleep)
    language_model.replies = [
        [_spawn(["weather in Berlin"])],
        [ToolCall(id="call_weather", name="get_weather", arguments={"location": "Berlin"})],
        ["Should not continue"],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]
    body: dict = {}

    def read_stream() -> None:
        try:
            with client.stream(
                "POST",
                f"/api/conversations/{conversation_id}/chat",
                json={"prompt": "Weather in Berlin"},
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
            ("user", "Weather in Berlin"),
        ]
        assert tool_finished.is_set() is False
    finally:
        release.set()
        reader.join(timeout=2)


def test_a_long_task_is_trimmed_on_the_worker_tool_pill(client, language_model):
    task = "weather in " + ("Berlin " * 20)
    language_model.replies = [
        [_spawn([task])],
        [ToolCall(id="call_weather", name="get_weather", arguments={"location": "Berlin"})],
        ["Sunny"],
        ["Done."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]

    with client.stream(
        "POST",
        f"/api/conversations/{conversation_id}/chat",
        json={"prompt": "Long task"},
    ) as response:
        events = sse_events(response.read().decode())

    assert events[0] == ("prompt", {"text": "Long task"})
    assert events[1][1]["display_text"] == "Asking 1 worker..."
    display = events[2][1]["display_text"]
    assert display == worker_tool_label("get_weather", task)
    assert display.endswith("…")
    assert "Checking weather... · " in display


def test_the_next_turn_sees_the_spawn_result_and_not_the_worker_loop(client, language_model):
    language_model.replies = [
        [_spawn(["weather in Berlin"])],
        ["Sunny in Berlin"],
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

    follow_up = language_model.calls[-1]
    assert [message["role"] for message in follow_up] == [
        "user",
        "assistant",
        "tool",
        "assistant",
        "user",
    ]
    assert all(message["role"] != "system" for message in follow_up)
    assert json.loads(follow_up[2]["content"])["workers"][0]["text"] == "Sunny in Berlin"


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
