from app.llm import ToolCall
from app.screen import (
    STOPPED_CALL_CAP,
    STOPPED_DAILY_BUDGET,
    STOPPED_MISSING_COUNT,
    STOPPED_TOKEN_CAP,
)
from app.tokens import count_messages, text_with_tokens
from test_compact_a_lead_call import (
    COMPACTION_WINDOW,
    SUMMARY_MARK,
    _is_summary,
    _lead_calls,
    _summary_calls,
    _window_for_line,
)
from test_mask_the_prompt import VALID_CARD, _chat


def _weather(call_id: str = "call_weather") -> ToolCall:
    return ToolCall(id=call_id, name="get_weather", arguments={"location": "Berlin"})


def _seed_over_the_line(client, language_model, conversation_id: str) -> None:
    language_model.replies = [[text_with_tokens(150)], ["Noted."]]
    language_model.reply_for = None
    for prompt in ("alpha", "beta", "gamma", "delta"):
        _chat(client, conversation_id, prompt)
    client.app.state.context_window = COMPACTION_WINDOW
    language_model.calls.clear()
    language_model.offered_tools.clear()


def test_a_summary_that_would_pass_10_calls_does_not_start(client, language_model):
    language_model.replies = [[text_with_tokens(1_700)], ["Noted."]]
    conversation_id = client.post("/api/conversations").json()["id"]
    for prompt in ("alpha", "beta", "gamma", "delta"):
        _chat(client, conversation_id, prompt)
    client.app.state.context_window = 2_000
    language_model.calls.clear()
    language_model.offered_tools.clear()

    def reply_for(messages):
        if _is_summary(messages):
            return ["  Brief.  "]
        return [_weather()]

    language_model.reply_for = reply_for
    events = _chat(client, conversation_id, "omega")

    assert len(language_model.calls) == 10
    assert _summary_calls(language_model)
    assert [payload["text"] for name, payload in events if name == "delta"] == [
        STOPPED_CALL_CAP
    ]
    assert [name for name, _ in events if name == "screen"] == []
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][-1]["content"] == STOPPED_CALL_CAP
    assert any(message["content"] == "omega" for message in detail["messages"])
    assert detail["messages"][-1].get("screen_notes") is None


def test_turn_tokens_stop_a_summary_before_todays_budget(client, language_model):
    language_model.replies = [["Spent."]]
    language_model.token_totals = [42_000]
    other = client.post("/api/conversations").json()["id"]
    _chat(client, other, "Fill part of today")

    language_model.replies = [[text_with_tokens(100)], ["Noted."]]
    conversation_id = client.post("/api/conversations").json()["id"]
    for prompt in ("alpha", "beta", "gamma", "delta"):
        _chat(client, conversation_id, prompt)
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    prompt = "omega"
    full = [
        {"role": message["role"], "content": message["content"] or ""}
        for message in detail["messages"]
    ]
    full.append({"role": "user", "content": prompt})
    client.app.state.context_window = _window_for_line(count_messages(full))
    language_model.replies = [[_weather()], ["Should not run"]]
    language_model.token_totals = [8_000]
    language_model.calls.clear()
    language_model.offered_tools.clear()

    events = _chat(client, conversation_id, prompt)

    assert len(language_model.calls) == 1
    assert language_model.offered_tools[0]
    assert [payload["text"] for name, payload in events if name == "delta"] == [
        STOPPED_TOKEN_CAP
    ]
    assert [name for name, _ in events if name == "screen"] == []


def test_todays_budget_stops_before_the_summary_starts(client, language_model):
    language_model.replies = [["Spent."]]
    language_model.token_totals = [50_000]
    other = client.post("/api/conversations").json()["id"]
    _chat(client, other, "Use the budget")

    conversation_id = client.post("/api/conversations").json()["id"]
    _seed_over_the_line(client, language_model, conversation_id)
    language_model.reply_for = lambda messages: (
        ["  Brief.  "] if _is_summary(messages) else ["Should not run"]
    )
    events = _chat(client, conversation_id, "omega")

    assert language_model.calls == []
    assert [payload["text"] for name, payload in events if name == "delta"] == [
        STOPPED_DAILY_BUDGET
    ]
    assert [name for name, _ in events if name == "screen"] == []


def test_a_summary_that_crosses_todays_budget_blocks_the_lead(client, language_model):
    language_model.replies = [["Spent."]]
    language_model.token_totals = [49_990]
    other = client.post("/api/conversations").json()["id"]
    _chat(client, other, "Almost today")

    conversation_id = client.post("/api/conversations").json()["id"]
    _seed_over_the_line(client, language_model, conversation_id)
    language_model.token_totals = [20]
    language_model.reply_for = lambda messages: (
        ["  Kept.  "] if _is_summary(messages) else ["Should not run"]
    )
    events = _chat(client, conversation_id, "omega")

    assert len(_summary_calls(language_model)) == 1
    assert _lead_calls(language_model) == []
    assert [payload["text"] for name, payload in events if name == "delta"] == [
        STOPPED_DAILY_BUDGET
    ]
    assert [name for name, _ in events if name == "screen"] == []
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][-1]["content"] == STOPPED_DAILY_BUDGET
    assert detail["messages"][-1].get("screen_notes") is None


def test_a_missing_summary_count_stops_the_lead_and_adds_nothing(client, language_model):
    conversation_id = client.post("/api/conversations").json()["id"]
    _seed_over_the_line(client, language_model, conversation_id)
    language_model.token_totals = [None]
    language_model.reply_for = lambda messages: (
        ["  Kept.  "] if _is_summary(messages) else ["Should not run"]
    )
    events = _chat(client, conversation_id, "omega")

    assert len(_summary_calls(language_model)) == 1
    assert _lead_calls(language_model) == []
    assert [payload["text"] for name, payload in events if name == "delta"] == [
        STOPPED_MISSING_COUNT
    ]

    language_model.reply_for = None
    language_model.replies = [["Counted."]]
    language_model.token_totals = [1]
    client.app.state.context_window = 50_000
    follow = _chat(client, conversation_id, "psi")
    assert ("screen", {"text": "Screen: 1 model call, 1 token. Today 5 of 50,000."}) in follow


def test_a_zero_summary_count_is_real_and_the_lead_still_runs(client, language_model):
    conversation_id = client.post("/api/conversations").json()["id"]
    _seed_over_the_line(client, language_model, conversation_id)
    language_model.token_totals = [0, 5]
    language_model.reply_for = lambda messages: (
        ["  Kept.  "] if _is_summary(messages) else ["Lead answer"]
    )
    events = _chat(client, conversation_id, "omega")

    assert len(_summary_calls(language_model)) == 1
    assert len(_lead_calls(language_model)) == 1
    assert ("delta", {"text": "Lead answer"}) in events
    assert (
        "screen",
        {"text": "Screen: 2 model calls, 5 tokens. Today 9 of 50,000."},
    ) in events


def test_the_cost_note_counts_the_summary_outside_the_turn_figure(client, language_model):
    conversation_id = client.post("/api/conversations").json()["id"]
    _seed_over_the_line(client, language_model, conversation_id)
    language_model.token_totals = [8_000, 1]
    language_model.reply_for = lambda messages: (
        ["  Kept.  "] if _is_summary(messages) else ["Lead answer"]
    )
    events = _chat(client, conversation_id, "omega")

    cost = "Screen: 2 model calls, 1 token. Today 8,005 of 50,000."
    assert ("delta", {"text": "Lead answer"}) in events
    assert ("screen", {"text": cost}) in events
    assert all("compact" not in payload.get("text", "") for name, payload in events if name == "screen")
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][-1]["screen_notes"] == [cost]


def test_the_summary_text_is_unmasked_and_the_closing_answer_is_masked(
    client, language_model
):
    conversation_id = client.post("/api/conversations").json()["id"]
    _seed_over_the_line(client, language_model, conversation_id)
    brief = f"Card {VALID_CARD} stays"
    answer = f"Card {VALID_CARD} done"
    language_model.reply_for = lambda messages: (
        [f"  {brief}  "] if _is_summary(messages) else [answer]
    )
    events = _chat(client, conversation_id, "omega")

    lead = _lead_calls(language_model)[0]
    assert any(message["content"] == f"{SUMMARY_MARK}{brief}" for message in lead)
    masked = answer.replace(VALID_CARD, "[card number]")
    assert ("delta", {"text": masked}) in events
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][-1]["content"] == masked
