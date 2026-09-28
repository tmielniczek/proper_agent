import json

from app.llm import ToolCall
from app.tokens import count_messages
from test_compact_a_lead_call import (
    SUMMARY_MARK,
    _is_summary,
    _lead_calls,
    _summary_calls,
    _window_for_line,
)
from test_mask_the_prompt import _chat
from test_spawn_workers import _spawn


def _instant(monkeypatch) -> None:
    async def instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.tools.asyncio.sleep", instant)


def _call(name: str, arguments: dict, call_id: str) -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments=arguments)


def _over_the_line(client, turns: list[dict]) -> None:
    client.app.state.context_window = _window_for_line(count_messages(turns) - 1)


def test_tail_grows_so_a_tool_burst_stays_whole(client, language_model, monkeypatch):
    _instant(monkeypatch)
    burst = [
        _call("get_weather", {"location": "Berlin"}, "call_berlin"),
        _call("search_database", {"query": "berlin"}, "call_search"),
        _call("calculator", {"expression": "2+2"}, "call_calc"),
    ]
    language_model.replies = [
        ["Noted."],
        burst,
        ["Warm."],
        ["Noted."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]
    _chat(client, conversation_id, "alpha")
    _chat(client, conversation_id, "beta")
    _chat(client, conversation_id, "gamma")

    def reply_for(messages):
        if _is_summary(messages):
            return ["Kept the burst."]
        return ["Lead answer"]

    language_model.reply_for = reply_for
    language_model.calls.clear()
    language_model.offered_tools.clear()
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    prior = [
        {"role": message["role"], "content": message["content"], **(
            {"tool_calls": message["tool_calls"]} if message["tool_calls"] else {}
        ), **(
            {"tool_call_id": message["tool_call_id"]} if message["tool_call_id"] else {}
        )}
        for message in detail["messages"]
    ]
    latest = "omega"
    _over_the_line(client, [*prior, {"role": "user", "content": latest}])

    _chat(client, conversation_id, latest)

    assert _summary_calls(language_model)[0][0]["role"] == "system"
    assert language_model.offered_tools[0] == []
    summary = _summary_calls(language_model)[0][1]["content"]
    assert "beta" in summary
    assert "call_berlin" not in summary
    lead = _lead_calls(language_model)[0]
    assert [message["content"] for message in lead].count("alpha") == 1
    assert all(message.get("content") != "beta" for message in lead)
    tool_ids = [
        message["tool_call_id"] for message in lead if message.get("role") == "tool"
    ]
    assert tool_ids == ["call_berlin", "call_search", "call_calc"]
    assistant = next(message for message in lead if message.get("tool_calls"))
    assert [call["id"] for call in assistant["tool_calls"]] == tool_ids
    assistant_at = lead.index(assistant)
    assert [message["role"] for message in lead[assistant_at : assistant_at + 4]] == [
        "assistant",
        "tool",
        "tool",
        "tool",
    ]
    assert len(lead) == 10


def test_spawn_result_in_the_middle_is_folded_into_the_brief(client, language_model):
    language_model.replies = [
        [_spawn(["Note the weather"])],
        ["Sunny in Berlin"],
        ["Compared."],
        ["Noted."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]
    _chat(client, conversation_id, "Compare")
    for prompt in ("alpha", "beta", "gamma", "delta"):
        _chat(client, conversation_id, prompt)
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    tool_message = next(message for message in detail["messages"] if message["role"] == "tool")
    stored_result = tool_message["content"]
    assert "Sunny in Berlin" in stored_result

    def reply_for(messages):
        if _is_summary(messages):
            return ["Folded the spawn."]
        return ["Lead answer"]

    language_model.reply_for = reply_for
    language_model.calls.clear()
    language_model.offered_tools.clear()
    client.app.state.context_window = 20

    _chat(client, conversation_id, "omega")

    summary = _summary_calls(language_model)[0][1]["content"]
    assert stored_result in summary
    lead = _lead_calls(language_model)[0]
    assert all(message.get("content") != stored_result for message in lead)
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert next(message for message in detail["messages"] if message["role"] == "tool")["content"] == stored_result


def test_a_later_lead_call_compacts_the_list_that_includes_new_tool_results(
    client, language_model, monkeypatch
):
    _instant(monkeypatch)
    language_model.replies = [["Noted."]]
    conversation_id = client.post("/api/conversations").json()["id"]
    for prompt in ("alpha", "beta", "gamma", "delta"):
        _chat(client, conversation_id, prompt)
    client.app.state.context_window = 20
    state = {"lead": 0}

    def reply_for(messages):
        if _is_summary(messages):
            return ["Brief."]
        if state["lead"] == 0:
            state["lead"] = 1
            return [_call("get_weather", {"location": "Berlin"}, "call_weather")]
        return ["Done."]

    language_model.reply_for = reply_for
    language_model.calls.clear()
    language_model.offered_tools.clear()

    _chat(client, conversation_id, "omega")

    lead_calls = _lead_calls(language_model)
    assert len(lead_calls) == 2
    second = lead_calls[1]
    tool_message = next(message for message in second if message.get("role") == "tool")
    assert "Sunny" in tool_message["content"]
    assert any(str(message.get("content", "")).startswith(SUMMARY_MARK) for message in second)
    assert all(message.get("content") != "beta" for message in second)
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    stored = next(
        message
        for message in detail["messages"]
        if message["role"] == "tool" and message["tool_call_id"] == "call_weather"
    )
    assert stored["content"] == tool_message["content"]
