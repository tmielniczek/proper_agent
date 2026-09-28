from test_stream_assistant_reply import sse_events

# Visa test number (Luhn-valid) and a lookalike that fails Luhn.
VALID_CARD = "4111111111111111"
INVALID_CARD = "4111111111111112"
VALID_CARD_SPACED = "4111 1111 1111 1111"
VALID_CARD_DASHED = "4111-1111-1111-1111"
SECOND_VALID_CARD = "5500000000000004"


def _chat(client, conversation_id: str, prompt: str):
    with client.stream(
        "POST",
        f"/api/conversations/{conversation_id}/chat",
        json={"prompt": prompt},
    ) as response:
        assert response.status_code == 200
        return sse_events(response.read().decode())


def test_dashed_ssn_is_masked_in_storage_stream_title_and_later_lead_call(client, language_model):
    language_model.replies = [["Noted."], ["Still noted."]]
    conversation_id = client.post("/api/conversations").json()["id"]
    prompt = "My number is 123-45-6789 please keep it"

    events = _chat(client, conversation_id, prompt)

    assert ("prompt", {"text": "My number is [ssn] please keep it"}) in events
    assert (
        "screen",
        {"text": "Screen: masked 1 social security number"},
    ) in events
    assert [name for name, _ in events].index("prompt") < [
        name for name, _ in events
    ].index("delta")

    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["title"] == "My number is [ssn] please keep"
    user = detail["messages"][0]
    assert user["content"] == "My number is [ssn] please keep it"
    assert user["screen_notes"] == ["Screen: masked 1 social security number"]
    assert language_model.calls[0][-1] == {
        "role": "user",
        "content": "My number is [ssn] please keep it",
    }

    _chat(client, conversation_id, "What did I say?")
    assert language_model.calls[1] == [
        {"role": "user", "content": "My number is [ssn] please keep it"},
        {"role": "assistant", "content": "Noted."},
        {"role": "user", "content": "What did I say?"},
    ]


def test_nine_bare_digits_are_left_as_written(client, language_model):
    conversation_id = client.post("/api/conversations").json()["id"]
    prompt = "Order 123456789 is ready"

    events = _chat(client, conversation_id, prompt)

    assert ("prompt", {"text": prompt}) in events
    assert [payload["text"] for name, payload in events if name == "screen"] == [
        "Screen: 1 model call, 1 token. Today 1 of 50,000."
    ]
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][0]["content"] == prompt
    assert detail["messages"][0].get("screen_notes") is None


def test_luhn_valid_card_is_masked_and_failures_stay_written(client, language_model):
    conversation_id = client.post("/api/conversations").json()["id"]
    prompt = (
        f"Pay with {VALID_CARD} or {VALID_CARD_SPACED} or {VALID_CARD_DASHED} "
        f"not {INVALID_CARD} or 123456789012"
    )

    events = _chat(client, conversation_id, prompt)

    masked = (
        "Pay with [card number] or [card number] or [card number] "
        f"not {INVALID_CARD} or 123456789012"
    )
    assert ("prompt", {"text": masked}) in events
    assert (
        "screen",
        {"text": "Screen: masked 3 card numbers"},
    ) in events
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][0]["content"] == masked
    assert detail["messages"][0]["screen_notes"] == ["Screen: masked 3 card numbers"]
    assert language_model.calls[0][-1]["content"] == masked


def test_labeled_secret_keeps_label_and_skips_card_inside_the_value(client, language_model):
    conversation_id = client.post("/api/conversations").json()["id"]
    prompt = (
        f"Before 123-45-6789 Password: {VALID_CARD} is secret\n"
        f"API_KEY: {SECOND_VALID_CARD}"
    )

    events = _chat(client, conversation_id, prompt)

    masked = "Before [ssn] Password:[secret]\nAPI_KEY:[secret]"
    assert ("prompt", {"text": masked}) in events
    assert (
        "screen",
        {"text": "Screen: masked 1 social security number, 2 secrets"},
    ) in events
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][0]["content"] == masked
    assert detail["messages"][0]["screen_notes"] == [
        "Screen: masked 1 social security number, 2 secrets"
    ]


def test_combined_masks_become_one_screen_note(client, language_model):
    conversation_id = client.post("/api/conversations").json()["id"]
    prompt = (
        f"ssn 123-45-6789 card {VALID_CARD} and {SECOND_VALID_CARD} "
        "password: hunter2"
    )

    events = _chat(client, conversation_id, prompt)

    note = "Screen: masked 1 social security number, 2 card numbers, 1 secret"
    assert ("screen", {"text": note}) in events
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][0]["content"] == (
        "ssn [ssn] card [card number] and [card number] password:[secret]"
    )
    assert detail["messages"][0]["screen_notes"] == [note]


def test_ordinary_prompt_emits_prompt_without_a_screen_note(client, language_model):
    conversation_id = client.post("/api/conversations").json()["id"]
    prompt = "What is 2+2?"

    events = _chat(client, conversation_id, prompt)

    assert events[0] == ("prompt", {"text": prompt})
    assert [payload["text"] for name, payload in events if name == "screen"] == [
        "Screen: 1 model call, 1 token. Today 1 of 50,000."
    ]
    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert detail["messages"][0]["content"] == prompt
    assert detail["messages"][0].get("screen_notes") is None
    assert detail["title"] == prompt
