import json

from app.llm import ToolCall
from test_mask_the_prompt import VALID_CARD, _chat
from test_stream_assistant_reply import sse_events


def test_closing_answer_is_held_masked_then_streamed(client, language_model):
    language_model.replies = [
        [f"Your card is {VALID_CARD}", " and your ssn is 123-45-6789."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]

    events = _chat(client, conversation_id, "What do you know?")

    masked = "Your card is [card number] and your ssn is [ssn]."
    note = "Screen: masked 1 social security number, 1 card number"
    deltas = [(name, payload["text"]) for name, payload in events if name == "delta"]
    assert deltas == [("delta", masked)]
    assert [name for name, _ in events].index("delta") > [
        name for name, _ in events
    ].index("prompt")
    assert ("screen", {"text": note}) in events
    screen_indexes = [i for i, (name, _) in enumerate(events) if name == "screen"]
    delta_index = [i for i, (name, _) in enumerate(events) if name == "delta"][0]
    assert screen_indexes[-1] > delta_index

    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assistant = detail["messages"][1]
    assert assistant["content"] == masked
    assert assistant["screen_notes"] == [note]


def test_labeled_secret_in_closing_answer_is_masked(client, language_model):
    language_model.replies = [["password: hunter2 stays secret"]]
    conversation_id = client.post("/api/conversations").json()["id"]

    events = _chat(client, conversation_id, "Tell me")

    assert [("delta", payload["text"]) for name, payload in events if name == "delta"] == [
        ("delta", "password:[secret]")
    ]
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][1]["content"] == "password:[secret]"
    assert detail["messages"][1]["screen_notes"] == ["Screen: masked 1 secret"]


def test_tool_call_narration_streams_immediately_and_stays_unmasked(client, language_model):
    narration = f"Looking up card {VALID_CARD} now."
    language_model.replies = [
        [
            "Looking up card ",
            f"{VALID_CARD} now.",
            ToolCall(id="call_weather", name="get_weather", arguments={"location": "Berlin"}),
        ],
        ["Done."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]

    with client.stream(
        "POST",
        f"/api/conversations/{conversation_id}/chat",
        json={"prompt": "Check Berlin"},
    ) as response:
        events = sse_events(response.read().decode())

    names = [name for name, _ in events]
    first_delta = names.index("delta")
    assert names[first_delta : first_delta + 2] == ["delta", "delta"]
    assert names.index("tool_start") > first_delta + 1
    assert [(name, payload["text"]) for name, payload in events if name == "delta"][:2] == [
        ("delta", "Looking up card "),
        ("delta", f"{VALID_CARD} now."),
    ]
    assert ("screen", {"text": "Screen: masked 1 card number"}) not in [
        event for event in events if event[0] == "screen"
    ]

    detail = client.get(f"/api/conversations/{conversation_id}").json()
    tool_message = detail["messages"][1]
    assert tool_message["content"] == narration
    assert tool_message.get("screen_notes") is None
    assert tool_message["tool_calls"][0]["function"]["name"] == "get_weather"


def test_memory_preface_keeps_a_card_number(client, language_model, monkeypatch):
    async def no_wait(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.tools.asyncio.sleep", no_wait)
    language_model.replies = [
        [
            ToolCall(
                id="call_mem",
                name="long_term_memory",
                arguments={"fact": f"Card is {VALID_CARD}"},
            )
        ],
        ["Saved."],
        ["I remember it."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]
    _chat(client, conversation_id, "Remember my card")
    _chat(client, conversation_id, "What is my card?")

    preface = language_model.calls[-1][0]["content"]
    assert VALID_CARD in preface
    assert "[card number]" not in preface


def test_worker_task_keeps_a_card_number_copied_by_the_lead(client, language_model, monkeypatch):
    async def no_wait(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.tools.asyncio.sleep", no_wait)
    task = f"Charge card {VALID_CARD}"
    language_model.replies = [
        [
            ToolCall(
                id="call_spawn",
                name="spawn_workers",
                arguments={"tasks": [task]},
            )
        ],
        ["Worker done."],
        ["All done."],
    ]
    conversation_id = client.post("/api/conversations").json()["id"]
    _chat(client, conversation_id, "Please charge")

    worker_call = language_model.calls[1]
    assert worker_call[-1] == {"role": "user", "content": task}
    assert VALID_CARD in worker_call[-1]["content"]

    detail = client.get(f"/api/conversations/{conversation_id}").json()
    tool_result = json.loads(detail["messages"][2]["content"])
    assert tool_result["workers"][0]["task"] == task
