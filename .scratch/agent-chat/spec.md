# Functional & Technical Specification: AI Agent Chat Interface (Mocked Tools)

## 1. Executive Summary & Objective

Build a lightweight, single-user local web interface that enables users to interact with an LLM-backed AI agent capable of invoking mocked tools. The system must support real-time token streaming via Server-Sent Events (SSE), tool execution state indicators with simulated latency, request cancellation with upstream abort, and persistent chat sessions.

|                            AGENT EXECUTION LOOP                                 |
|                                                                                 |
|   1. CONTEXT ASSEMBLY   -> user input         |
|   2. REASONING & EVAL   -> Evaluates context via model engine          |
|   3. ACTION EXECUTION   -> Executes tool calls OR generates final answer    |
|   4. ITERATIVE FEEDBACK -> Appends tool results to context & repeats loop        |

---

## 2. System Architecture & Tech Stack

```
[ React Client ] 
   │   ▲
   │   │  1. SSE Stream: text-delta / tool-call events
   │   │  2. POST /chat/cancel (AbortController triggered)
   ▼   │
[ FastAPI Backend ]
   │   ├── SQLite (Local DB via SQLAlchemy / SQLModel)
   │   ├── LLM Provider SDK (OpenAI / Anthropic compatible client)
   │   └── Mock Tool Engine (Static registry + 1–10s random sleep)

```

* **Frontend:** React (Vite or Next.js Pages/App Router), Tailwind CSS / shadcn/ui.
* **Backend:** Python 3.11+, FastAPI, Uvicorn, SQLite.
* **LLM Integration:** Real provider client driven by `.env` (`OPENAI_API_KEY`, `OPENAI_MODEL` or Anthropic equivalent) with native tool/function calling support.
* **Transport:** Standard HTTP REST for CRUD + Server-Sent Events (`text/event-stream`) for chat generation.

---

## 3. Data Model (SQLite)

### Table: `conversations`

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT / UUID | PRIMARY KEY | Unique conversation identifier |
| `title` | TEXT | NOT NULL | First 30 characters of the first prompt |
| `created_at` | DATETIME | DEFAULT CURRENT_TIMESTAMP | Creation timestamp |
| `updated_at` | DATETIME | DEFAULT CURRENT_TIMESTAMP | Last activity timestamp |

### Table: `messages`

| Column | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | TEXT / UUID | PRIMARY KEY | Unique message identifier |
| `conversation_id` | TEXT / UUID | FOREIGN KEY -> `conversations.id` | Cascading delete on conversation removal |
| `role` | TEXT | NOT NULL | Check constraint: `user`, `assistant`, `tool` |
| `content` | TEXT | NULLABLE | Text content (NULL if purely a tool invocation) |
| `tool_calls` | JSON / TEXT | NULLABLE | Serialized tool call metadata (name, arguments) |
| `tool_call_id` | TEXT | NULLABLE | Identifier matching parent tool call |
| `created_at` | DATETIME | DEFAULT CURRENT_TIMESTAMP | Message timestamp |

---

## 4. Mock Tool Engine

Tools must be registered in the backend with standard schemas passed to the LLM function calling parameter. Each tool handler must implement simulated network latency using an async sleep: `await asyncio.sleep(random.uniform(1.0, 10.0))`.

### Tool Registry

1. **`get_weather`**
* **Arguments:** `location: string`
* **Mock Return:** `{"temperature": 21, "condition": "Sunny", "humidity": "45%", "location": "<location>"}`
* **Frontend UI Text:** `"Checking weather..."`


2. **`search_database`**
* **Arguments:** `query: string`
* **Mock Return:** `{"results": [{"id": 101, "record": "Mock data result for query: <query>"}]}`
* **Frontend UI Text:** `"Searching database..."`


3. **`calculator`**
* **Arguments:** `expression: string`
* **Mock Return:** Evaluates safe basic math or returns static `{"result": 42}`
* **Frontend UI Text:** `"Calculating..."`



---

## 5. API Contracts & SSE Protocol

### `GET /api/conversations`

Returns list of all conversations sorted by `updated_at` DESC.

### `POST /api/conversations`

Creates an empty conversation session.

### `GET /api/conversations/{id}`

Returns conversation details with complete chronological message history.

### `POST /api/conversations/{id}/chat`

Streams agent response via SSE.

* **Request Body:** `{"prompt": "string"}`
* **SSE Stream Event Contract:**
* `event: delta` → `data: {"text": "chunk"}`
* `event: tool_start` → `data: {"tool": "get_weather", "display_text": "Checking weather..."}`
* `event: tool_end` → `data: {"tool": "get_weather"}`
* `event: done` → `data: {"message_id": "uuid"}`
* `event: error` → `data: {"error": "description"}`



### `POST /api/conversations/{id}/cancel`

Signals backend to abort ongoing generation.

* Cancels upstream `asyncio.Task` running the LLM stream.
* Triggers the HTTP client `abort()` / cancellation token to the LLM API.
* Drops the uncommitted assistant message buffer.

---

## 6. Functional Specifications & User Stories

### Story 1: Starting & Managing Conversations

* **As a user**, I want new conversations auto-named from my prompt so that I can navigate past threads easily.
* **Acceptance Criteria (Gherkin):**
* **Given** I am on a new or empty chat screen,
* **When** I submit my first message `"What is the current temperature in Berlin and calculate 2+2?"`,
* **Then** a new conversation row is created in SQLite with `title = "What is the current temperatur"`,
* **And** it appears at the top of the sidebar.



---

### Story 2: Streaming Generation with Mocked Tool Indicators

* **As a user**, I want visual status indicators while tools run so that I know the agent is waiting on external calls.
* **Acceptance Criteria (Gherkin):**
* **Given** I send a prompt requiring tool usage,
* **When** the LLM outputs a tool call for `get_weather`,
* **Then** the UI renders an inline status pill displaying `Checking weather...` with an animated pulse/spinner,
* **And** the backend pauses execution between 1.0 and 10.0 seconds before returning the mock JSON payload to the LLM context,
* **And** once the tool finishes, the indicator transitions to complete and standard streaming text continues.



---

### Story 3: Request Cancellation & State Rollback

* **As a user**, I want to stop generation mid-stream without corrupting my conversation state.
* **Acceptance Criteria (Gherkin):**
* **Given** the agent is actively streaming text or waiting on a mocked tool,
* **When** I click the **Cancel** button in the UI,
* **Then** the client aborts the incoming SSE connection and fires `POST /api/conversations/{id}/cancel`,
* **And** the backend immediately terminates the upstream LLM request and the running tool sleep task,
* **And** any partial assistant text is wiped from the client display,
* **And** SQLite persists only the user's prompt (the last message in history is the user's input).



---

## 7. Non-Functional & Operational Requirements

* **Local Isolation:** SQLite file stored at `./data/app.db`. No authentication headers or login barriers.
* **Configuration:** Backend reads settings from `.env`:
```ini
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
DATABASE_URL=sqlite+aiosqlite:///./data/app.db

```


* **Error Handling:** If upstream LLM rejects API key or throws a rate-limit error, backend must emit an SSE `event: error` and persist nothing from that failed turn.
