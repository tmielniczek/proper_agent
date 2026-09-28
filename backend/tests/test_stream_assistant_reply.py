import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

PROMPT = "What is the current temperature in Berlin and calculate 2+2?"


def sse_events(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in body.split("\n\n"):
        if not block.strip() or block.lstrip().startswith(":"):
            continue
        event_name = "message"
        data = None
        for line in block.split("\n"):
            if line.startswith("event:"):
                event_name = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                data = json.loads(line.removeprefix("data:").strip())
        if data is not None:
            events.append((event_name, data))
    return events


def test_prompt_streams_plain_text_and_saves_the_assistant_message(client, language_model):
    language_model.replies = [["Hello", " there"]]
    conversation_id = client.post("/api/conversations").json()["id"]

    with client.stream(
        "POST",
        f"/api/conversations/{conversation_id}/chat",
        json={"prompt": PROMPT},
    ) as response:
        assert response.status_code == 200
        events = sse_events(response.read().decode())

    assert [event for event in events if event[0] in {"tool_start", "tool_end"}] == []
    assert [(name, payload["text"]) for name, payload in events if name == "delta"] == [
        ("delta", "Hello"),
        ("delta", " there"),
    ]
    done = [payload for name, payload in events if name == "done"]
    assert len(done) == 1

    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert [(message["role"], message["content"]) for message in detail["messages"]] == [
        ("user", PROMPT),
        ("assistant", "Hello there"),
    ]
    assert detail["messages"][1]["id"] == done[0]["message_id"]
    assert detail["updated_at"] == detail["messages"][1]["created_at"]
    assert detail["messages"][1]["created_at"] > detail["messages"][0]["created_at"]

    listed = client.get("/api/conversations").json()
    assert listed[0]["id"] == conversation_id
    assert listed[0]["updated_at"] == detail["messages"][1]["created_at"]


def test_follow_up_keeps_earlier_messages_and_moves_the_conversation_to_the_top(
    client, language_model
):
    language_model.replies = [["First answer"], ["Second answer"]]
    conversation_id = client.post("/api/conversations").json()["id"]
    other_id = client.post("/api/conversations").json()["id"]

    client.post(
        f"/api/conversations/{conversation_id}/chat",
        json={"prompt": "What is 2+2?"},
    )
    client.post(
        f"/api/conversations/{other_id}/chat",
        json={"prompt": "Tell me about the other thread"},
    )
    client.post(
        f"/api/conversations/{conversation_id}/chat",
        json={"prompt": "And now double it"},
    )

    assert language_model.calls[2] == [
        {"role": "user", "content": "What is 2+2?"},
        {"role": "assistant", "content": "First answer"},
        {"role": "user", "content": "And now double it"},
    ]

    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert [(message["role"], message["content"]) for message in detail["messages"]] == [
        ("user", "What is 2+2?"),
        ("assistant", "First answer"),
        ("user", "And now double it"),
        ("assistant", "Second answer"),
    ]
    listed = client.get("/api/conversations").json()
    assert [conversation["id"] for conversation in listed] == [conversation_id, other_id]
    assert listed[0]["updated_at"] == detail["messages"][-1]["created_at"]


class _Chunks:
    def __init__(self, texts: list[str]) -> None:
        self._texts = texts

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for text in self._texts:
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=text))]
            )


class _FakeCompletions:
    def __init__(self, recorded: dict) -> None:
        self._recorded = recorded

    async def create(self, **kwargs):
        self._recorded["create"] = kwargs
        return _Chunks(["Plain", " text"])


class _FakeOpenAI:
    def __init__(self, **kwargs) -> None:
        recorded["init"] = kwargs
        self.chat = SimpleNamespace(completions=_FakeCompletions(recorded))


recorded: dict = {}


def test_reply_is_plain_text_from_the_model_named_in_the_environment(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MODEL_NAME", "gpt-5-nano")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
    )
    recorded.clear()
    monkeypatch.setattr("app.llm.AsyncOpenAI", _FakeOpenAI)

    from app.main import create_app

    with TestClient(create_app()) as client:
        conversation_id = client.post("/api/conversations").json()["id"]
        with client.stream(
            "POST",
            f"/api/conversations/{conversation_id}/chat",
            json={"prompt": "Say hello"},
        ) as response:
            assert response.status_code == 200
            events = sse_events(response.read().decode())

        detail = client.get(f"/api/conversations/{conversation_id}")

    assert recorded["init"]["api_key"] == "sk-test"
    assert recorded["create"]["model"] == "gpt-5-nano"
    assert recorded["create"]["messages"] == [{"role": "user", "content": "Say hello"}]
    assert recorded["create"]["stream"] is True
    assert [tool["function"]["name"] for tool in recorded["create"]["tools"]] == [
        "get_weather",
        "search_database",
        "calculator",
        "spawn_workers",
    ]
    assert [(name, payload["text"]) for name, payload in events if name == "delta"] == [
        ("delta", "Plain"),
        ("delta", " text"),
    ]
    assert detail.json()["messages"][1]["content"] == "Plain text"
