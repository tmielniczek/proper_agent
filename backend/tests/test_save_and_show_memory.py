import asyncio
import json

from app.llm import ToolCall
from test_stream_assistant_reply import sse_events

_real_sleep = asyncio.sleep
MEMORY_NOTE = (
    "Workers cannot see these memories. If a task needs a fact, write that fact into the task."
)


def _instant(monkeypatch) -> None:
    async def sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.tools.asyncio.sleep", sleep)


def _chat(client, conversation_id: str, prompt: str) -> list[tuple[str, dict]]:
    with client.stream(
        "POST",
        f"/api/conversations/{conversation_id}/chat",
        json={"prompt": prompt},
    ) as response:
        assert response.status_code == 200
        return sse_events(response.read().decode())


def _save(fact: object, call_id: str = "call_memory") -> ToolCall:
    arguments = {} if fact is None else {"fact": fact}
    return ToolCall(id=call_id, name="long_term_memory", arguments=arguments)


def _system_messages(call: list[dict]) -> list[dict]:
    return [message for message in call if message["role"] == "system"]


def test_lead_is_offered_memory_and_an_empty_store_adds_nothing(client, language_model):
    language_model.replies = [["Nothing saved."]]
    conversation_id = client.post("/api/conversations").json()["id"]

    _chat(client, conversation_id, "Hello")

    offered = language_model.offered_tools[0]
    assert offered is not None
    memory_tool = next(tool for tool in offered if tool["function"]["name"] == "long_term_memory")
    description = memory_tool["function"]["description"]
    assert "remember" in description
    assert "store" in description
    assert memory_tool["function"]["parameters"]["required"] == ["fact"]
    assert language_model.calls[0] == [{"role": "user", "content": "Hello"}]
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert [message["role"] for message in detail["messages"]] == ["user", "assistant"]


def test_save_trims_the_fact_shows_the_pill_and_keeps_the_call(client, language_model, monkeypatch):
    waited: list[float] = []

    def uniform(low: float, high: float) -> float:
        assert (low, high) == (1.0, 10.0)
        return 3.5

    async def sleep(seconds: float) -> None:
        waited.append(seconds)

    monkeypatch.setattr("app.tools.random.uniform", uniform)
    monkeypatch.setattr("app.tools.asyncio.sleep", sleep)
    language_model.replies = [
        [_save("  The user lives in Berlin.  ")],
        ["I will remember that."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]

    events = _chat(client, conversation_id, "Remember that I live in Berlin")

    assert events[0] == ("prompt", {"text": "Remember that I live in Berlin"})
    assert events[1] == (
        "tool_start",
        {"tool": "long_term_memory", "display_text": "Saving a memory..."},
    )
    assert events[2][0] == "tool_end"
    assert waited == [3.5]
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    messages = detail["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant", "tool", "assistant"]
    assert [message["role"] for message in messages if message["role"] == "system"] == []
    tool_call = messages[1]["tool_calls"][0]
    assert tool_call["function"]["name"] == "long_term_memory"
    assert json.loads(tool_call["function"]["arguments"]) == {"fact": "  The user lives in Berlin.  "}
    assert json.loads(messages[2]["content"]) == {"saved": "The user lives in Berlin."}
    assert messages[3]["content"] == "I will remember that."
    assert _system_messages(language_model.calls[0]) == []
    assert _system_messages(language_model.calls[1]) == []


def test_bad_fact_waits_returns_an_error_and_stores_nothing(client, language_model, monkeypatch):
    waited: list[float] = []

    async def sleep(seconds: float) -> None:
        waited.append(seconds)

    monkeypatch.setattr("app.tools.asyncio.sleep", sleep)
    conversation_id = client.post("/api/conversations").json()["id"]
    language_model.replies = [
        [_save(None, "call_missing")],
        ["Which fact?"],
        [_save(12, "call_number")],
        ["That was not text."],
        [_save("   ", "call_blank")],
        ["Nothing to keep."],
        ["Still nothing."],
    ]

    for prompt in ("Remember", "Remember a number", "Remember blanks"):
        events = _chat(client, conversation_id, prompt)
        assert events[0] == ("prompt", {"text": prompt})
        assert events[1][1]["display_text"] == "Saving a memory..."
        assert events[2][0] == "tool_end"

    assert len(waited) == 3
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    errors = [
        json.loads(message["content"])
        for message in detail["messages"]
        if message["role"] == "tool"
    ]
    assert errors == [{"error": "Memory needs a fact."}] * 3
    _chat(client, conversation_id, "What do you know?")
    assert _system_messages(language_model.calls[-1]) == []


def test_later_turns_list_memories_newest_first_without_storing_the_list(
    client, language_model, monkeypatch
):
    _instant(monkeypatch)
    language_model.replies = [
        [_save("The user lives in Berlin.", "call_berlin")],
        ["Saved Berlin."],
        [_save("The user lives in Berlin.", "call_berlin_again")],
        ["Saved Berlin again."],
        [_save("The user prefers tea.", "call_tea")],
        ["Saved tea."],
        ["You prefer tea, and you live in Berlin."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]
    _chat(client, conversation_id, "Remember Berlin")
    _chat(client, conversation_id, "Remember Berlin again")

    events = _chat(client, conversation_id, "Remember tea")
    assert events[0] == ("prompt", {"text": "Remember tea"})
    assert events[1][1]["display_text"] == "Saving a memory..."
    opening = language_model.calls[-2]
    after_tool = language_model.calls[-1]
    assert len(_system_messages(opening)) == 1
    assert len(_system_messages(after_tool)) == 1
    assert opening[0] == after_tool[0]
    assert "The user prefers tea." not in opening[0]["content"]
    assert opening[0]["content"] == (
        "Memories, newest first:\n"
        "- The user lives in Berlin.\n"
        "- The user lives in Berlin.\n"
        "\n"
        f"{MEMORY_NOTE}"
    )
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert all(message["role"] != "system" for message in detail["messages"])

    _chat(client, conversation_id, "What should I drink?")
    assert language_model.calls[-1][0]["content"] == (
        "Memories, newest first:\n"
        "- The user prefers tea.\n"
        "- The user lives in Berlin.\n"
        "- The user lives in Berlin.\n"
        "\n"
        f"{MEMORY_NOTE}"
    )

    other_id = client.post("/api/conversations").json()["id"]
    language_model.replies.append(["Tea, and you live in Berlin."])
    _chat(client, other_id, "Where do I live?")
    assert language_model.calls[-1][0]["role"] == "system"
    assert language_model.calls[-1][0]["content"] == language_model.calls[-2][0]["content"]
    assert language_model.calls[-1][1] == {"role": "user", "content": "Where do I live?"}


def test_a_fact_saved_this_turn_joins_the_list_on_the_next_turn(
    client, language_model, monkeypatch
):
    _instant(monkeypatch)
    language_model.replies = [
        [_save("First fact.")],
        ["Saved the first."],
        [_save("Second fact.")],
        ["Saved the second."],
        ["Second, then first."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]
    _chat(client, conversation_id, "Remember the first")
    _chat(client, conversation_id, "Remember the second")

    during = language_model.calls[-1][0]["content"]
    assert "First fact." in during
    assert "Second fact." not in during
    assert json.loads(
        client.get(f"/api/conversations/{conversation_id}").json()["messages"][-2]["content"]
    ) == {"saved": "Second fact."}

    _chat(client, conversation_id, "What did I ask you to keep?")
    listed = language_model.calls[-1][0]["content"]
    assert listed.index("- Second fact.") < listed.index("- First fact.")


def test_the_twenty_first_older_memory_is_left_out_of_the_request(
    client, language_model, monkeypatch
):
    _instant(monkeypatch)
    replies: list[list[object]] = []
    for index in range(1, 22):
        replies.append([_save(f"fact {index}", f"call_{index}")])
        replies.append([f"Saved {index}."])
    replies.append(["The newest facts."])
    language_model.replies = replies
    conversation_id = client.post("/api/conversations").json()["id"]
    for index in range(1, 22):
        _chat(client, conversation_id, f"Remember {index}")

    _chat(client, conversation_id, "List what you kept")
    content = language_model.calls[-1][0]["content"]
    bullets = [line for line in content.splitlines() if line.startswith("- ")]
    assert bullets == [f"- fact {index}" for index in range(21, 1, -1)]
    assert "- fact 1\n" not in content


def test_line_breaks_stay_in_the_stored_fact_and_become_spaces_in_the_list(
    client, language_model, monkeypatch
):
    _instant(monkeypatch)
    language_model.replies = [
        [_save("The user\r\nlives in Berlin.")],
        ["Saved."],
        ["You live in Berlin."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]
    _chat(client, conversation_id, "Remember this address")
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert json.loads(detail["messages"][2]["content"]) == {
        "saved": "The user\r\nlives in Berlin."
    }

    _chat(client, conversation_id, "Where do I live?")
    content = language_model.calls[-1][0]["content"]
    assert "- The user lives in Berlin.\n" in content
    assert "\r" not in content.split("Workers", 1)[0]


def test_two_saves_in_one_reply_run_with_other_tools(client, language_model, monkeypatch):
    state = {"current": 0, "max": 0}

    async def overlap(_seconds: float) -> None:
        state["current"] += 1
        state["max"] = max(state["max"], state["current"])
        await _real_sleep(0.05)
        state["current"] -= 1

    monkeypatch.setattr("app.tools.asyncio.sleep", overlap)
    language_model.replies = [
        [
            _save("Likes tea.", "call_tea"),
            _save("Lives in Berlin.", "call_berlin"),
            ToolCall(id="call_weather", name="get_weather", arguments={"location": "Berlin"}),
        ],
        ["Saved both and checked the weather."],
        ["Tea in Berlin."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]
    events = _chat(client, conversation_id, "Remember tea and Berlin, and check the weather")

    assert state["max"] == 3
    starts = [payload for name, payload in events if name == "tool_start"]
    assert [payload["tool"] for payload in starts] == [
        "long_term_memory",
        "long_term_memory",
        "get_weather",
    ]
    assert all(payload["display_text"] == "Saving a memory..." for payload in starts[:2])
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    saved = [
        json.loads(message["content"])
        for message in detail["messages"]
        if message["role"] == "tool" and message["tool_call_id"] != "call_weather"
    ]
    assert saved == [{"saved": "Likes tea."}, {"saved": "Lives in Berlin."}]

    _chat(client, conversation_id, "What did you keep?")
    content = language_model.calls[-1][0]["content"]
    assert "- Lives in Berlin.\n" in content
    assert "- Likes tea.\n" in content
