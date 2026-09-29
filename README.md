# Agent chat

A local, single-user chat where a lead answers each turn, can call mocked tools, and can hand independent tasks to workers.

## Why I Built This

A chat box that only streams tokens hides the rest of an agent: tool runs, parallel work, secrets in the transcript, a context window that fills up, and spend with no ceiling. This app is a small local demo of that loop. The thread you read stays the full conversation. Caps, masking, compaction, and a console trace sit around it so a turn is visible without sending secrets to the model or into telemetry.

## Features

- Streaming replies over server-sent events, with cancel that aborts the turn upstream.
- Mocked tools with a short random delay: weather, database search, and a calculator. Several tool calls in one reply run together.
- A lead that can spawn up to five workers on independent tasks. Workers do not see the conversation, cannot spawn, and tasks past the fifth are refused.
- App-wide memory: when you ask the lead to remember a fact, later turns include the newest memories (up to twenty). Workers never see that list.
- A screen that masks social security numbers, card numbers, and labeled secrets in your prompt and in the lead's closing answer, refuses a fixed list of "ignore instructions" phrases, and stops a turn when a per-turn or daily token cap is already hit.
- Compaction for long chats: the stored transcript stays complete, and a lead call past 80% of a 50,000-token window is sent the first message, a rolling summary, and a recent tail that keeps a tool burst whole.
- One OpenTelemetry trace per turn, printed to the console. Spans cover the turn, model calls, and tool runs. Prompt text, secrets, tool arguments, and memory stay off the trace.

## Tech Stack

- Python, FastAPI, Uvicorn
- SQLModel and SQLite (aiosqlite)
- OpenAI SDK and tiktoken
- OpenTelemetry (console exporter)
- React, TypeScript, Vite, Tailwind CSS
- pytest and httpx

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js (current LTS)
- An OpenAI API key

### Installation

```bash
git clone <repo-url>
cd proper_agent
python -m venv .venv
```

On Windows:

```bash
.venv\Scripts\activate
pip install -r backend/requirements.txt
copy .env.example .env
```

On macOS or Linux:

```bash
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
```

Put your key in `.env` at the repo root:

```
OPENAI_API_KEY=sk-...
MODEL_NAME=gpt-5-nano
```

Then install the frontend:

```bash
cd frontend
npm install
```

### Running

Start the API from `backend` (so `app` is on the import path):

```bash
cd backend
uvicorn app.main:app --reload
```

In a second terminal:

```bash
cd frontend
npm run dev
```

Open the Vite URL (usually `http://127.0.0.1:5173`). The dev server proxies `/api` to `http://127.0.0.1:8000`. Conversations are stored in `backend/data/`.

Tests:

```bash
cd backend
pytest
```

## Usage

Start a conversation and send a prompt. The sidebar keeps past chats. Token use for the open conversation is available from the API at `/api/conversations/{id}/tokens`.

Examples:

- `What's the weather in Berlin?` — the lead calls weather and the thread shows "Checking weather..." until the mocked call returns.
- `Remember that I live in Berlin.` — the lead saves one fact. A later chat can use it without you repeating it.
- `Weather in Berlin, Paris, and Madrid.` — the lead can spawn one worker per city. The thread shows "Asking N workers..." while they run.
- A prompt that contains a card number or `api_key: ...` is stored and shown masked, with a screen note that names the kind of mask and not the value.
- A prompt that asks the model to ignore its instructions is refused before any model call.

The API process prints one trace per turn: a `turn` span, then `chat` and `execute_tool` spans underneath it.

## Challenges & Learnings

Masking every model call would have been simpler and wrong. Tool narration has to stream immediately, and worker tasks and saved memories are meant to stay as written. The screen therefore sits on the user's prompt and the lead's closing answer, while the cost check still runs before every model call, including workers.

Compaction has the same split. The transcript you reopen is the full thread. Only the lead's next model call is shortened, and a tool call is never sent without the results that belong to it. If the protected head and tail are already over the line, the turn stops instead of summarizing those messages away.

Traces were the other place secrets could leak. A refusal still emits a turn, so gated prompts show up as traffic, but the span does not carry the prompt, the refusal sentence, tool arguments, or the screen note.

Workers stay shallow on purpose: one task, no conversation, no nested spawn, and a hard cap of five in flight. Dependent steps stay with the lead after it reads a result.

## License

MIT

## Author

Tomasz Mielniczek
