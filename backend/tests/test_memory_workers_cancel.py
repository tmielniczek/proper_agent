import json
import threading

from app.llm import ProviderRejection, ToolCall
from test_save_and_show_memory import _chat, _instant, _save
from test_spawn_workers import TOOL_NAMES, WORKER_PREFACE, _names, _real_sleep, _spawn


def test_a_worker_does_not_see_memories_and_cannot_save_one(client, language_model, monkeypatch):
    _instant(monkeypatch)
    language_model.replies = [
        [_save("The user lives in Berlin.")],
        ["Saved."],
        [_spawn(["store the password", "weather in Paris"])],
        [ToolCall(id="call_secret", name="long_term_memory", arguments={"fact": "password"})],
        ["Rainy in Paris"],
        ["Paris is rainy. The other task failed."],
        ["You live in Berlin."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]
    _chat(client, conversation_id, "Remember that I live in Berlin")
    _chat(client, conversation_id, "Check Paris and store a password")

    worker_calls = [call for call in language_model.calls if call[0] == WORKER_PREFACE]
    assert worker_calls == [
        [WORKER_PREFACE, {"role": "user", "content": "store the password"}],
        [WORKER_PREFACE, {"role": "user", "content": "weather in Paris"}],
    ]
    assert _names(language_model.offered_tools[-3]) == TOOL_NAMES
    assert _names(language_model.offered_tools[-2]) == TOOL_NAMES
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert json.loads(detail["messages"][-2]["content"])["workers"] == [
        {"task": "store the password", "error": "Unknown tool: long_term_memory"},
        {"task": "weather in Paris", "text": "Rainy in Paris"},
    ]

    _chat(client, conversation_id, "Where do I live?")
    assert language_model.calls[-1][0]["content"] == (
        "Memories, newest first:\n"
        "- The user lives in Berlin.\n"
        "\n"
        "Workers cannot see these memories. If a task needs a fact, write that fact into the task."
    )


def test_a_memory_save_and_a_spawn_run_one_after_another(client, language_model, monkeypatch):
    state = {"current": 0, "max": 0}

    async def overlap(_seconds: float) -> None:
        state["current"] += 1
        state["max"] = max(state["max"], state["current"])
        await _real_sleep(0.05)
        state["current"] -= 1

    monkeypatch.setattr("app.tools.asyncio.sleep", overlap)
    language_model.replies = [
        [
            _save("The user lives in Berlin.", "call_memory"),
            _spawn(["weather in Berlin"], "call_spawn"),
        ],
        [ToolCall(id="call_weather", name="get_weather", arguments={"location": "Berlin"})],
        ["Sunny in Berlin"],
        ["Saved, and Berlin is sunny."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]

    events = _chat(client, conversation_id, "Remember Berlin and check the weather")

    assert state["max"] == 1
    names = [name for name, _payload in events]
    assert names.index("tool_end") < names.index("tool_start", names.index("tool_start") + 1)
    assert [payload["tool"] for name, payload in events if name == "tool_start"] == [
        "long_term_memory",
        "spawn_workers",
        "get_weather",
    ]
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert [message["tool_call_id"] for message in detail["messages"] if message["role"] == "tool"] == [
        "call_memory",
        "call_spawn",
    ]


def test_cancel_during_the_save_wait_stores_nothing(client, language_model, monkeypatch):
    holding = threading.Event()
    release = threading.Event()
    saved = threading.Event()

    async def sleep(_seconds: float) -> None:
        holding.set()
        while not release.is_set():
            await _real_sleep(0.01)
        saved.set()

    monkeypatch.setattr("app.tools.asyncio.sleep", sleep)
    language_model.replies = [
        [_save("The user lives in Berlin.")],
        ["Should not be kept."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]
    prompt = "Remember that I live in Berlin"
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
        assert holding.wait(timeout=2)
        cancelled = client.post(f"/api/conversations/{conversation_id}/cancel")
        assert cancelled.status_code == 204
        reader.join(timeout=2)
        assert not reader.is_alive()
        assert body.get("error") is None
        assert "event: done" not in body.get("text", "")
        detail = client.get(f"/api/conversations/{conversation_id}").json()
        assert [(message["role"], message["content"]) for message in detail["messages"]] == [
            ("user", prompt),
        ]
        assert saved.is_set() is False
    finally:
        release.set()
        reader.join(timeout=2)

    language_model.replies = [["I have nothing stored."]]
    _chat(client, conversation_id, "Where do I live?")
    assert [message["role"] for message in language_model.calls[-1]] == ["user", "user"]


def test_rejection_before_the_save_stores_nothing_and_drops_the_turn(client, language_model):
    language_model.replies = [
        [
            _save("The user lives in Berlin."),
            ProviderRejection("The API key was rejected"),
        ],
        ["Nothing stored."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]

    events = _chat(client, conversation_id, "Remember that I live in Berlin")

    assert [name for name, _payload in events if name == "tool_start"] == []
    assert events[-1] == ("error", {"error": "The API key was rejected"})
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"] == []

    other_id = client.post("/api/conversations").json()["id"]
    _chat(client, other_id, "Where do I live?")
    assert language_model.calls[-1] == [{"role": "user", "content": "Where do I live?"}]


def test_a_finished_save_remains_when_a_later_rejection_drops_the_turn(
    client, language_model, monkeypatch
):
    _instant(monkeypatch)
    language_model.replies = [
        [_save("The user lives in Berlin.")],
        [ProviderRejection("The request was rate-limited")],
        ["You live in Berlin."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]

    events = _chat(client, conversation_id, "Remember that I live in Berlin")

    assert events[0][1]["display_text"] == "Saving a memory..."
    assert events[-1] == ("error", {"error": "The request was rate-limited"})
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"] == []

    other_id = client.post("/api/conversations").json()["id"]
    _chat(client, other_id, "Where do I live?")
    assert language_model.calls[-1][0]["content"].startswith(
        "Memories, newest first:\n- The user lives in Berlin.\n"
    )
