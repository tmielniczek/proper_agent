import json

import pytest
from app.llm import ToolCall
from app.screen import (
    STOPPED_CALL_CAP,
    STOPPED_MISSING_COUNT,
    STOPPED_TOKEN_CAP,
)
from test_mask_the_prompt import _chat
from test_spawn_workers import _spawn
from test_stream_assistant_reply import sse_events


def _weather(call_id: str = "call_weather") -> ToolCall:
    return ToolCall(
        id=call_id,
        name="get_weather",
        arguments={"location": "Berlin"},
    )


@pytest.fixture(autouse=True)
def instant_tool_wait(monkeypatch):
    async def instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.tools.asyncio.sleep", instant)


def test_tenth_model_call_starts_and_eleventh_does_not(client, language_model):
    language_model.replies = [[_weather(f"call_{index}")] for index in range(10)] + [
        ["Should not run"]
    ]
    conversation_id = client.post("/api/conversations").json()["id"]

    events = _chat(client, conversation_id, "Keep going")

    assert len(language_model.calls) == 10
    assert [payload["text"] for name, payload in events if name == "delta"] == [
        STOPPED_CALL_CAP
    ]
    assert [name for name, _ in events if name == "screen"] == []
    assert events[-1][0] == "done"

    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][-1]["content"] == STOPPED_CALL_CAP
    assert detail["messages"][-1].get("screen_notes") is None
    tool_messages = [m for m in detail["messages"] if m["role"] == "tool"]
    assert len(tool_messages) == 10


def test_crossing_8000_tokens_stops_the_next_call(client, language_model):
    language_model.replies = [[_weather()], ["Should not run"]]
    language_model.token_totals = [8000]
    conversation_id = client.post("/api/conversations").json()["id"]

    events = _chat(client, conversation_id, "Spend tokens")

    assert len(language_model.calls) == 1
    assert [payload["text"] for name, payload in events if name == "delta"] == [
        STOPPED_TOKEN_CAP
    ]
    assert [name for name, _ in events if name == "screen"] == []
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][-1]["content"] == STOPPED_TOKEN_CAP
    assert detail["messages"][-1].get("screen_notes") is None
    assert any(m["role"] == "tool" for m in detail["messages"])


def test_one_call_over_8000_finishes_with_cost_and_next_turn_is_free(
    client, language_model
):
    language_model.replies = [["Heavy answer."]]
    language_model.token_totals = [8001]
    conversation_id = client.post("/api/conversations").json()["id"]

    events = _chat(client, conversation_id, "One big call")

    cost = "Screen: 1 model call, 8,001 tokens. Today 8,001 of 50,000."
    assert ("delta", {"text": "Heavy answer."}) in events
    assert ("screen", {"text": cost}) in events
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][-1]["screen_notes"] == [cost]

    language_model.replies = [["Next turn."]]
    language_model.token_totals = [1]
    second = _chat(client, conversation_id, "Again")
    assert ("delta", {"text": "Next turn."}) in second
    assert len(language_model.calls) == 2


def test_missing_token_count_stops_the_next_call(client, language_model):
    language_model.replies = [[_weather()], ["Should not run"]]
    language_model.token_totals = [None]
    conversation_id = client.post("/api/conversations").json()["id"]

    events = _chat(client, conversation_id, "Unknown spend")

    assert len(language_model.calls) == 1
    assert [payload["text"] for name, payload in events if name == "delta"] == [
        STOPPED_MISSING_COUNT
    ]
    assert [name for name, _ in events if name == "screen"] == []
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][-1]["content"] == STOPPED_MISSING_COUNT
    assert detail["messages"][-1].get("screen_notes") is None


def test_reported_zero_counts_as_a_real_total(client, language_model):
    language_model.replies = [[_weather()], ["Still going."]]
    language_model.token_totals = [0, 1]
    conversation_id = client.post("/api/conversations").json()["id"]

    events = _chat(client, conversation_id, "Zero is fine")

    assert len(language_model.calls) == 2
    assert ("delta", {"text": "Still going."}) in events
    note = "Screen: 2 model calls, 1 token. Today 1 of 50,000."
    assert ("screen", {"text": note}) in events


def test_call_count_message_wins_when_tokens_also_capped(client, language_model):
    language_model.replies = [[_weather(f"call_{index}")] for index in range(10)] + [
        ["Should not run"]
    ]
    language_model.token_totals = [800] * 10
    conversation_id = client.post("/api/conversations").json()["id"]

    events = _chat(client, conversation_id, "Both caps")

    assert len(language_model.calls) == 10
    assert [payload["text"] for name, payload in events if name == "delta"] == [
        STOPPED_CALL_CAP
    ]
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][-1]["content"] == STOPPED_CALL_CAP


def test_token_message_wins_over_missing_count(client, language_model):
    language_model.replies = [[_weather()], [_weather()], ["Should not run"]]
    language_model.token_totals = [8000, None]
    conversation_id = client.post("/api/conversations").json()["id"]

    events = _chat(client, conversation_id, "Token before missing")

    assert len(language_model.calls) == 1
    assert [payload["text"] for name, payload in events if name == "delta"] == [
        STOPPED_TOKEN_CAP
    ]


def test_per_turn_caps_reset_on_the_next_prompt(client, language_model):
    language_model.replies = [[_weather(f"call_{index}")] for index in range(10)]
    conversation_id = client.post("/api/conversations").json()["id"]
    _chat(client, conversation_id, "Hit the call cap")
    assert len(language_model.calls) == 10

    language_model.replies = [["Fresh turn."]]
    events = _chat(client, conversation_id, "New turn")
    assert ("delta", {"text": "Fresh turn."}) in events
    assert len(language_model.calls) == 11


def test_workers_under_the_cap_finish_and_one_over_returns_stopped_error(
    client, language_model
):
    # 7 lead tool rounds + 1 spawn = 8 calls; two workers claim 9 and 10; third stops.
    language_model.replies = [
        [_weather(f"call_{index}")] for index in range(7)
    ] + [
        [_spawn(["task a", "task b", "task c"])],
        ["Worker a done."],
        ["Worker b done."],
        ["Should not be a lead follow-up"],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]

    events = _chat(client, conversation_id, "Spawn near the cap")

    assert len(language_model.calls) == 10
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    spawn_result = json.loads(
        next(
            m["content"]
            for m in detail["messages"]
            if m["role"] == "tool" and "workers" in (m["content"] or "")
        )
    )
    finished = [w for w in spawn_result["workers"] if "text" in w]
    blocked = [w for w in spawn_result["workers"] if "error" in w]
    assert {w["text"] for w in finished} == {"Worker a done.", "Worker b done."}
    assert len(blocked) == 1
    assert blocked[0]["error"] == STOPPED_CALL_CAP
    assert blocked[0]["task"] in {"task a", "task b", "task c"}
    assert detail["messages"][-1]["content"] == STOPPED_CALL_CAP
    assert detail["messages"][-1].get("screen_notes") is None
    assert [payload["text"] for name, payload in events if name == "delta"] == [
        STOPPED_CALL_CAP
    ]
    assert [name for name, _ in events if name == "screen"] == []


def test_parallel_workers_take_the_last_slot_under_one_lock(client, language_model):
    # 9 lead calls leave one slot; two parallel workers cannot both claim it.
    language_model.replies = [
        [_weather(f"call_{index}")] for index in range(8)
    ] + [
        [_spawn(["first", "second"])],
        ["First worker."],
        ["Should not run"],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]

    events = _chat(client, conversation_id, "Last slot")

    assert len(language_model.calls) == 10
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    spawn_result = json.loads(
        next(
            m["content"]
            for m in detail["messages"]
            if m["role"] == "tool" and "workers" in (m["content"] or "")
        )
    )
    finished = [w for w in spawn_result["workers"] if "text" in w]
    blocked = [w for w in spawn_result["workers"] if w.get("error") == STOPPED_CALL_CAP]
    assert len(finished) == 1
    assert finished[0]["text"] == "First worker."
    assert len(blocked) == 1
    assert detail["messages"][-1]["content"] == STOPPED_CALL_CAP
    assert detail["messages"][-1].get("screen_notes") is None
    assert [payload["text"] for name, payload in events if name == "delta"] == [
        STOPPED_CALL_CAP
    ]


def test_stopped_refusal_is_one_delta_then_done(client, language_model):
    language_model.replies = [[_weather()], ["nope"]]
    language_model.token_totals = [8000]
    conversation_id = client.post("/api/conversations").json()["id"]

    with client.stream(
        "POST",
        f"/api/conversations/{conversation_id}/chat",
        json={"prompt": "Stop shape"},
    ) as response:
        events = sse_events(response.read().decode())

    names = [name for name, _ in events]
    assert names[-2:] == ["delta", "done"]
    assert events[-2] == ("delta", {"text": STOPPED_TOKEN_CAP})
    assert "screen" not in names
