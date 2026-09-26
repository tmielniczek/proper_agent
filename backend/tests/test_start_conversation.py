PROMPT = "What is the current temperature in Berlin and calculate 2+2?"
TITLE = "What is the current temperatur"


def test_first_prompt_names_the_conversation_and_stores_the_prompt(client):
    created = client.post("/api/conversations")
    assert created.status_code == 200
    conversation_id = created.json()["id"]

    with client.stream(
        "POST",
        f"/api/conversations/{conversation_id}/chat",
        json={"prompt": PROMPT},
    ) as response:
        assert response.status_code == 200
        assert "event: done" in response.read().decode()

    listed = client.get("/api/conversations")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == conversation_id
    assert listed.json()[0]["title"] == TITLE

    detail = client.get(f"/api/conversations/{conversation_id}")
    assert detail.status_code == 200
    assert [(message["role"], message["content"]) for message in detail.json()["messages"]] == [
        ("user", PROMPT),
        ("assistant", "stub reply"),
    ]


def test_conversations_are_listed_most_recently_active_first(client):
    older = client.post("/api/conversations").json()["id"]
    newer = client.post("/api/conversations").json()["id"]

    client.post(
        f"/api/conversations/{older}/chat",
        json={"prompt": "alpha prompt that is long enough"},
    )
    client.post(
        f"/api/conversations/{newer}/chat",
        json={"prompt": "beta prompt that is long enough"},
    )

    titles = [conversation["title"] for conversation in client.get("/api/conversations").json()]
    assert titles == [
        "beta prompt that is long enoug",
        "alpha prompt that is long enou",
    ]

    client.post(
        f"/api/conversations/{older}/chat",
        json={"prompt": "follow up on alpha"},
    )

    titles = [conversation["title"] for conversation in client.get("/api/conversations").json()]
    assert titles == [
        "alpha prompt that is long enou",
        "beta prompt that is long enoug",
    ]

    detail = client.get(f"/api/conversations/{older}")
    assert [message["content"] for message in detail.json()["messages"]] == [
        "alpha prompt that is long enough",
        "stub reply",
        "follow up on alpha",
        "stub reply",
    ]
    assert [message["role"] for message in detail.json()["messages"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
