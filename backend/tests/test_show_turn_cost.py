from app.llm import ToolCall
from test_mask_the_prompt import VALID_CARD, _chat
from test_stream_assistant_reply import sse_events


def test_finished_turn_shows_cost_note_on_closing_answer(client, language_model):
    language_model.replies = [["Hello"]]
    language_model.token_totals = [1200]
    conversation_id = client.post("/api/conversations").json()["id"]

    events = _chat(client, conversation_id, "Hi")

    note = "Screen: 1 model call, 1,200 tokens. Today 1,200 of 50,000."
    assert ("prompt", {"text": "Hi"}) in events
    assert ("screen", {"text": note}) in events
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][1]["screen_notes"] == [note]


def test_singular_wording_for_one_call_and_one_token(client, language_model):
    language_model.replies = [["Ok"]]
    conversation_id = client.post("/api/conversations").json()["id"]

    events = _chat(client, conversation_id, "Hi")

    note = "Screen: 1 model call, 1 token. Today 1 of 50,000."
    assert ("screen", {"text": note}) in events
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][1]["screen_notes"] == [note]


def test_cost_counts_lead_and_worker_calls_and_adds_to_today(
    client, language_model, monkeypatch
):
    async def no_wait(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.tools.asyncio.sleep", no_wait)
    language_model.replies = [
        [
            ToolCall(
                id="call_spawn",
                name="spawn_workers",
                arguments={"tasks": ["weather in Paris"]},
            )
        ],
        ["Sunny in Paris."],
        ["Done."],
    ]
    language_model.token_totals = [100, 200, 300]
    conversation_id = client.post("/api/conversations").json()["id"]

    events = _chat(client, conversation_id, "Check Paris")

    note = "Screen: 3 model calls, 600 tokens. Today 600 of 50,000."
    assert ("screen", {"text": note}) in events
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][-1]["screen_notes"] == [note]

    language_model.replies = [["Again."]]
    language_model.token_totals = [400]
    events = _chat(client, conversation_id, "And again")
    second = "Screen: 1 model call, 400 tokens. Today 1,000 of 50,000."
    assert ("screen", {"text": second}) in events
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][-1]["screen_notes"] == [second]


def test_cost_and_mask_notes_survive_reload_in_order(client, language_model):
    language_model.replies = [[f"Card {VALID_CARD} noted."]]
    language_model.token_totals = [50]
    conversation_id = client.post("/api/conversations").json()["id"]

    events = _chat(client, conversation_id, f"My ssn is 123-45-6789")

    prompt_note = "Screen: masked 1 social security number"
    answer_note = "Screen: masked 1 card number"
    cost_note = "Screen: 1 model call, 50 tokens. Today 50 of 50,000."
    assert ("screen", {"text": prompt_note}) in events
    assert ("screen", {"text": answer_note}) in events
    assert ("screen", {"text": cost_note}) in events
    screen_texts = [payload["text"] for name, payload in events if name == "screen"]
    assert screen_texts == [prompt_note, answer_note, cost_note]

    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][0]["screen_notes"] == [prompt_note]
    assert detail["messages"][1]["screen_notes"] == [answer_note, cost_note]


def test_mocked_tool_call_adds_neither_model_call_nor_tokens(client, language_model):
    language_model.replies = [
        [ToolCall(id="call_weather", name="get_weather", arguments={"location": "Berlin"})],
        ["Sunny."],
    ]
    language_model.token_totals = [10, 20]
    conversation_id = client.post("/api/conversations").json()["id"]

    events = _chat(client, conversation_id, "Weather?")

    note = "Screen: 2 model calls, 30 tokens. Today 30 of 50,000."
    assert ("screen", {"text": note}) in events
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][-1]["screen_notes"] == [note]


def test_ordinary_successful_turn_emits_prompt_and_cost_screen(client, language_model):
    language_model.replies = [["Hello", " there"]]
    conversation_id = client.post("/api/conversations").json()["id"]

    with client.stream(
        "POST",
        f"/api/conversations/{conversation_id}/chat",
        json={"prompt": "Say hi"},
    ) as response:
        events = sse_events(response.read().decode())

    note = "Screen: 1 model call, 1 token. Today 1 of 50,000."
    assert events[0] == ("prompt", {"text": "Say hi"})
    assert ("screen", {"text": note}) in events
    assert events[-2] == ("screen", {"text": note})
    assert events[-1][0] == "done"
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][1]["screen_notes"] == [note]
