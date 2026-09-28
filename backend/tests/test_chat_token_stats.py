from app.compaction import CONTEXT_WINDOW, compaction_line
from app.memory import format_memories
from app.tokens import count_messages
from test_mask_the_prompt import _chat


def test_token_stats_count_the_lead_list_and_leave_out_screen_notes(client, language_model):
    language_model.replies = [["Noted."]]
    conversation_id = client.post("/api/conversations").json()["id"]
    _chat(client, conversation_id, "My number is 123-45-6789 please keep it")

    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][0]["screen_notes"] == ["Screen: masked 1 social security number"]
    stats = client.get(f"/api/conversations/{conversation_id}/tokens").json()
    stored = [
        {"role": message["role"], "content": message["content"] or ""}
        for message in detail["messages"]
    ]

    assert stats == {
        "tokens": count_messages(stored),
        "context_window": CONTEXT_WINDOW,
        "compaction_line": compaction_line(CONTEXT_WINDOW),
    }


def test_token_stats_include_the_memory_preface(client, language_model, monkeypatch):
    preface = format_memories(["Lives in Lisbon"])

    async def stored_preface() -> str:
        return preface

    monkeypatch.setattr("app.conversations.memory_preface", stored_preface)
    language_model.replies = [["Noted."]]
    conversation_id = client.post("/api/conversations").json()["id"]
    _chat(client, conversation_id, "Hi")

    detail = client.get(f"/api/conversations/{conversation_id}").json()
    stats = client.get(f"/api/conversations/{conversation_id}/tokens").json()
    turns = [{"role": "system", "content": preface}] + [
        {"role": message["role"], "content": message["content"] or ""}
        for message in detail["messages"]
    ]

    assert stats["tokens"] == count_messages(turns)


def test_an_empty_conversation_counts_as_zero_tokens(client):
    conversation_id = client.post("/api/conversations").json()["id"]

    stats = client.get(f"/api/conversations/{conversation_id}/tokens").json()

    assert stats["tokens"] == 0
    assert stats["compaction_line"] == compaction_line(stats["context_window"])
