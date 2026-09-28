from app.compaction import SUMMARY_INSTRUCTION, STOPPED_TOO_LARGE
from app.llm import ProviderRejection
from app.tokens import count_messages, text_with_tokens
from test_compact_a_lead_call import COMPACTION_WINDOW, SUMMARY_MARK, _is_summary, _lead_calls, _summary_calls
from test_mask_the_prompt import _chat


def _no_screen(events) -> None:
    assert [payload["text"] for name, payload in events if name == "delta"] == [
        STOPPED_TOO_LARGE
    ]
    assert [name for name, _ in events if name == "screen"] == []


def _seed_short(client, language_model, conversation_id: str) -> None:
    language_model.reply_for = None
    language_model.replies = [["Noted."]]
    for prompt in ("alpha", "beta", "gamma", "delta"):
        _chat(client, conversation_id, prompt)


def _seed_long_middle(client, language_model, conversation_id: str) -> None:
    language_model.reply_for = None
    language_model.replies = [[text_with_tokens(150)], ["Noted."]]
    for prompt in ("alpha", "beta", "gamma", "delta"):
        _chat(client, conversation_id, prompt)


def test_head_and_tail_over_the_line_stop_before_a_summary_call(client, language_model):
    conversation_id = client.post("/api/conversations").json()["id"]
    _seed_short(client, language_model, conversation_id)
    client.app.state.context_window = 10
    language_model.calls.clear()
    language_model.offered_tools.clear()

    events = _chat(client, conversation_id, "omega")

    assert language_model.calls == []
    _no_screen(events)
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][-2]["content"] == "omega"
    assert detail["messages"][-1]["content"] == STOPPED_TOO_LARGE
    assert detail["messages"][-1].get("screen_notes") is None


def test_summary_input_over_the_window_stops_and_exactly_the_window_is_sent(
    client, language_model
):
    conversation_id = client.post("/api/conversations").json()["id"]
    language_model.replies = [[text_with_tokens(120)], ["a"], ["b"], ["c"]]
    for prompt in ("head", "m2", "p2", "p3"):
        _chat(client, conversation_id, prompt)
    client.app.state.context_window = 100
    language_model.calls.clear()
    language_model.offered_tools.clear()

    events = _chat(client, conversation_id, "latest")

    assert language_model.calls == []
    _no_screen(events)

    fitted = _middle_text_for_summary_window(200)
    other = client.post("/api/conversations").json()["id"]
    language_model.reply_for = None
    language_model.replies = [[fitted], ["Noted."]]
    for prompt in ("alpha", "beta", "gamma", "delta"):
        _chat(client, other, prompt)
    client.app.state.context_window = 200
    language_model.reply_for = lambda messages: (
        ["Short brief."] if _is_summary(messages) else ["Lead answer"]
    )
    language_model.calls.clear()
    language_model.offered_tools.clear()

    _chat(client, other, "omega")

    assert len(_summary_calls(language_model)) == 1
    assert len(_lead_calls(language_model)) == 1


def _middle_text_for_summary_window(window: int) -> str:
    instruction = count_messages([{"role": "system", "content": SUMMARY_INSTRUCTION}])
    # The seeded middle is this reply plus the next user message "beta".
    for size in range(window):
        body = text_with_tokens(size) + "\nbeta"
        total = instruction + count_messages([{"role": "user", "content": body}])
        if total == window:
            return text_with_tokens(size)
    raise AssertionError("no middle size lands on the context window")


def test_a_blank_or_rejected_brief_stops_and_leaves_the_previous_summary(
    client, language_model
):
    conversation_id = client.post("/api/conversations").json()["id"]
    _seed_long_middle(client, language_model, conversation_id)
    client.app.state.context_window = COMPACTION_WINDOW
    language_model.reply_for = lambda messages: (
        ["  Kept.  "] if _is_summary(messages) else ["Lead answer"]
    )
    language_model.calls.clear()
    language_model.offered_tools.clear()
    _chat(client, conversation_id, "omega")
    assert len(_summary_calls(language_model)) == 1

    language_model.reply_for = lambda messages: (
        ["   \n  "] if _is_summary(messages) else ["Should not run"]
    )
    language_model.calls.clear()
    language_model.offered_tools.clear()

    events = _chat(client, conversation_id, "psi")

    assert _lead_calls(language_model) == []
    _no_screen(events)
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][-2]["content"] == "psi"

    language_model.reply_for = lambda messages: (
        ["Next."] if _is_summary(messages) else ["After."]
    )
    language_model.calls.clear()
    language_model.offered_tools.clear()
    _chat(client, conversation_id, "rho")
    assert _summary_calls(language_model)[0][1]["content"].startswith("Kept.")

    language_model.reply_for = lambda messages: (
        [ProviderRejection("rejected")] if _is_summary(messages) else ["No lead"]
    )
    language_model.calls.clear()
    language_model.offered_tools.clear()
    events = _chat(client, conversation_id, "sigma")
    assert _lead_calls(language_model) == []
    _no_screen(events)
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert any(message["content"] == "sigma" for message in detail["messages"])


def test_a_compacted_list_over_the_window_stops_and_keeps_the_brief(client, language_model):
    conversation_id = client.post("/api/conversations").json()["id"]
    language_model.reply_for = None
    language_model.replies = [[text_with_tokens(20)], ["Noted."]]
    for prompt in ("alpha", "beta", "gamma", "delta"):
        _chat(client, conversation_id, prompt)
    client.app.state.context_window = COMPACTION_WINDOW
    huge = text_with_tokens(60)

    def reply_for(messages):
        if _is_summary(messages):
            return [huge]
        return ["Should not run"]

    language_model.reply_for = reply_for
    language_model.calls.clear()
    language_model.offered_tools.clear()

    events = _chat(client, conversation_id, text_with_tokens(135))

    assert len(_summary_calls(language_model)) == 1
    assert _lead_calls(language_model) == []
    _no_screen(events)

    language_model.reply_for = lambda messages: (
        ["Later."] if _is_summary(messages) else ["Done."]
    )
    language_model.calls.clear()
    language_model.offered_tools.clear()
    _chat(client, conversation_id, "psi")
    summary = _summary_calls(language_model)[0][1]["content"]
    assert summary.startswith(huge)
    lead = _lead_calls(language_model)[0]
    assert any(message["content"] == f"{SUMMARY_MARK}Later." for message in lead)
