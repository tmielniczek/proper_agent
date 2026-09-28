import json

from fastapi.testclient import TestClient

from app.llm import ToolCall
from app.main import create_app
from app.memory import format_memories
from test_compact_a_lead_call import SUMMARY_MARK, _is_summary, _lead_calls, _summary_calls

COMPACTION_WINDOW = 200
from app.tokens import text_with_tokens
from test_mask_the_prompt import _chat
from test_save_and_show_memory import _save


def _instant(monkeypatch) -> None:
    async def instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.tools.asyncio.sleep", instant)


def _weather_burst() -> list[ToolCall]:
    return [
        ToolCall(id=f"call_{index}", name="get_weather", arguments={"location": f"City {index}"})
        for index in range(5)
    ]


def _summary_reply(brief: str):
    def reply_for(messages):
        if _is_summary(messages):
            return [f"  {brief}  "]
        return ["Lead answer"]

    return reply_for


def _compact(client, language_model, conversation_id: str, brief: str) -> None:
    language_model.reply_for = _summary_reply(brief)
    language_model.calls.clear()
    language_model.offered_tools.clear()
    client.app.state.context_window = COMPACTION_WINDOW
    _chat(client, conversation_id, "omega")


def test_later_summary_reads_the_previous_brief_and_only_the_new_middle(
    client, language_model
):
    language_model.replies = [[text_with_tokens(150)], ["Noted."]]
    conversation_id = client.post("/api/conversations").json()["id"]
    for prompt in ("alpha", "beta", "gamma", "delta"):
        _chat(client, conversation_id, prompt)
    _compact(client, language_model, conversation_id, "First brief.")
    first = _summary_calls(language_model)[0]
    assert "beta" in first[1]["content"]
    assert "gamma" not in first[1]["content"]
    assert "Fold the new messages" not in first[0]["content"]

    language_model.calls.clear()
    language_model.offered_tools.clear()
    _chat(client, conversation_id, "psi")

    folded = _summary_calls(language_model)
    assert len(folded) == 1
    assert "Fold the new messages into the previous brief" in folded[0][0]["content"]
    assert folded[0][1]["content"].startswith("First brief.")
    assert "gamma" in folded[0][1]["content"]
    assert "beta" not in folded[0][1]["content"]
    lead = _lead_calls(language_model)[0]
    assert any(message["content"] == f"{SUMMARY_MARK}First brief." for message in lead)


def test_unchanged_middle_reuses_the_brief_and_a_new_memory_changes_the_preface(
    client, language_model, monkeypatch
):
    _instant(monkeypatch)
    language_model.replies = [[text_with_tokens(400)], _weather_burst(), ["Warm."], ["Noted."]]
    conversation_id = client.post("/api/conversations").json()["id"]
    _chat(client, conversation_id, "alpha")
    _chat(client, conversation_id, "beta")
    language_model.reply_for = _summary_reply("Held brief.")
    language_model.calls.clear()
    language_model.offered_tools.clear()
    client.app.state.context_window = 500
    _chat(client, conversation_id, "omega")
    assert len(_summary_calls(language_model)) == 1

    saver = client.post("/api/conversations").json()["id"]
    language_model.reply_for = None
    language_model.replies = [[_save("User likes tea.")], ["Saved."]]
    client.app.state.context_window = 50_000
    _chat(client, saver, "Remember that I like tea")

    language_model.reply_for = _summary_reply("Should not run.")
    language_model.calls.clear()
    language_model.offered_tools.clear()
    client.app.state.context_window = 500
    _chat(client, conversation_id, "psi")

    assert _summary_calls(language_model) == []
    lead = _lead_calls(language_model)[0]
    assert lead[0] == {"role": "system", "content": format_memories(["User likes tea."])}
    assert any(message["content"] == f"{SUMMARY_MARK}Held brief." for message in lead)
    assert any(
        message.get("role") == "tool" and "City 0" in (message.get("content") or "")
        for message in lead
    )


def test_another_conversation_keeps_its_own_rolling_summary(client, language_model):
    language_model.replies = [[text_with_tokens(150)], ["Noted."]]
    first = client.post("/api/conversations").json()["id"]
    second = client.post("/api/conversations").json()["id"]
    for conversation_id in (first, second):
        language_model.replies = [[text_with_tokens(150)], ["Noted."]]
        language_model.reply_for = None
        for prompt in ("alpha", "beta", "gamma", "delta"):
            _chat(client, conversation_id, prompt)
    _compact(client, language_model, first, "Brief A.")
    _compact(client, language_model, second, "Brief B.")
    language_model.calls.clear()
    language_model.offered_tools.clear()
    language_model.reply_for = _summary_reply("Brief A2.")

    _chat(client, first, "psi")

    summary = _summary_calls(language_model)[0][1]["content"]
    assert summary.startswith("Brief A.")
    assert "Brief B." not in summary


def test_a_new_app_has_no_rolling_summary(client, language_model):
    language_model.replies = [[text_with_tokens(150)], ["Noted."]]
    conversation_id = client.post("/api/conversations").json()["id"]
    for prompt in ("alpha", "beta", "gamma", "delta"):
        _chat(client, conversation_id, prompt)
    _compact(client, language_model, conversation_id, "First brief.")

    with TestClient(create_app(language_model)) as restarted:
        restarted.app.state.context_window = COMPACTION_WINDOW
        language_model.reply_for = _summary_reply("Second brief.")
        language_model.calls.clear()
        language_model.offered_tools.clear()
        _chat(restarted, conversation_id, "psi")

    summary = _summary_calls(language_model)[0]
    assert "Fold the new messages" not in summary[0]["content"]
    assert "beta" in summary[1]["content"]
    assert "First brief." not in summary[1]["content"]


def test_cancel_keeps_the_rolling_summary_when_folded_messages_remain(
    client, language_model
):
    import threading

    language_model.replies = [[text_with_tokens(150)], ["Noted."]]
    conversation_id = client.post("/api/conversations").json()["id"]
    for prompt in ("alpha", "beta", "gamma", "delta"):
        _chat(client, conversation_id, prompt)
    client.app.state.context_window = COMPACTION_WINDOW

    def reply_for(messages):
        if _is_summary(messages):
            return ["  Kept.  "]
        language_model.hold_after_chunks = 0
        return ["Should stop"]

    language_model.reply_for = reply_for
    body: dict = {}

    def read_stream() -> None:
        try:
            with client.stream(
                "POST",
                f"/api/conversations/{conversation_id}/chat",
                json={"prompt": "omega"},
            ) as response:
                body["text"] = response.read().decode()
        except Exception as exc:
            body["error"] = exc

    reader = threading.Thread(target=read_stream)
    reader.start()
    try:
        assert language_model.holding.wait(timeout=2)
        cancelled = client.post(f"/api/conversations/{conversation_id}/cancel")
        assert cancelled.status_code == 204
        reader.join(timeout=2)
    finally:
        language_model.release.set()
        reader.join(timeout=2)

    assert body.get("error") is None
    language_model.hold_after_chunks = None
    language_model.reply_for = _summary_reply("Next.")
    language_model.calls.clear()
    language_model.offered_tools.clear()
    _chat(client, conversation_id, "psi")

    summary = _summary_calls(language_model)[0][1]["content"]
    assert summary.startswith("Kept.")
    assert "beta" not in summary


def test_cancel_discards_the_rolling_summary_when_it_deletes_a_folded_message(
    client, language_model, monkeypatch
):
    import threading

    _instant(monkeypatch)
    language_model.replies = [[text_with_tokens(150)], ["Noted."]]
    conversation_id = client.post("/api/conversations").json()["id"]
    for prompt in ("alpha", "beta", "gamma", "delta"):
        _chat(client, conversation_id, prompt)
    client.app.state.context_window = COMPACTION_WINDOW
    state = {"tools": 0}

    def reply_for(messages):
        if _is_summary(messages):
            return ["  Running brief.  "]
        if state["tools"] < 4:
            state["tools"] += 1
            return [ToolCall(id=f"call_{state['tools']}", name="get_weather", arguments={"location": "Berlin"})]
        language_model.hold_after_chunks = 0
        return ["Should stop"]

    language_model.reply_for = reply_for
    body: dict = {}

    def read_stream() -> None:
        try:
            with client.stream(
                "POST",
                f"/api/conversations/{conversation_id}/chat",
                json={"prompt": "omega"},
            ) as response:
                body["text"] = response.read().decode()
        except Exception as exc:
            body["error"] = exc

    reader = threading.Thread(target=read_stream)
    reader.start()
    try:
        assert language_model.holding.wait(timeout=5)
        detail = client.get(f"/api/conversations/{conversation_id}").json()
        folded_tool = next(
            message for message in detail["messages"] if message["role"] == "tool"
        )
        cancelled = client.post(f"/api/conversations/{conversation_id}/cancel")
        assert cancelled.status_code == 204
        reader.join(timeout=5)
    finally:
        language_model.release.set()
        reader.join(timeout=2)

    assert body.get("error") is None
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert all(message["id"] != folded_tool["id"] for message in detail["messages"])
    language_model.hold_after_chunks = None
    language_model.reply_for = _summary_reply("After cancel.")
    language_model.calls.clear()
    language_model.offered_tools.clear()
    _chat(client, conversation_id, "psi")

    summary = _summary_calls(language_model)[0]
    assert "Fold the new messages" not in summary[0]["content"]
    assert "beta" in summary[1]["content"]
    assert "Running brief." not in summary[1]["content"]
    assert folded_tool["content"] not in json.dumps(language_model.calls)
