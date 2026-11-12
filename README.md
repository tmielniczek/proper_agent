# Agent chat

A local, single-user chat.

## Why I Built This

I built this to learn how AI agents actually work under the hood.

Most chat apps only show you the text streaming in. A real agent does a lot more behind the scenes:

- it calls tools,
- it splits work across helpers that run at the same time,
- it can leak secrets you typed,
- it fills up its memory (the context window),
- and it can burn money with no limit.

This app makes all of that visible in one small local project. Your chat history stays complete. Around it I added spending caps, secret masking, chat compression, and a log of every turn, so you can see what happens without sending your secrets to the model or into the logs.


## Features

- **Live replies.** Text streams in as it's written. Hitting Cancel actually stops the request.
- **Fake tools.** Weather, database search, and a calculator. They're mocked with a short random delay to feel real. If the model asks for several tools at once, they run together.
- **Workers.** The main agent (the "lead") can hand off up to 5 independent tasks to workers. Workers only see their own task, not your chat. They can't create more workers. A 6th task is refused.
- **Memory.** Say "remember that..." and the lead saves it. Future chats include your newest 20 memories. Workers never see them.
- **Safety screen.** 
  - Hides social security numbers, card numbers, and labeled secrets (like `api_key: ...`) in your message and in the lead's final answer.
  - Blocks known "ignore your instructions" phrases.
  - Stops a turn if you've already hit the per-turn or daily token limit.
- **Compression for long chats.** The model's memory holds 50,000 tokens. Once a request would go past 80% of that, the lead gets a shortened version: your first message, a running summary, and the latest messages (a tool call and its results are always kept together). Your saved chat is never cut.
- **Turn tracing.** Each turn prints one OpenTelemetry trace to the console: the turn, each model call, and each tool run. Your prompts, secrets, tool inputs, and memories are never included.

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

Windows:

```bash
.venv\Scripts\activate
pip install -r backend/requirements.txt
copy .env.example .env
```

macOS or Linux:

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

Frontend:

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

Second terminal:

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

Start a conversation and send a prompt. The sidebar keeps past chats. Token use for the open conversation is at `/api/conversations/{id}/tokens`.

- `What's the weather in Berlin?` — the lead calls weather. The thread shows "Checking weather..." until the mocked call returns.
- `Remember that I live in Berlin.` — the lead saves one fact. A later chat can use it.
- `Weather in Berlin, Paris, and Madrid.` — the lead can spawn one worker per city. The thread shows "Asking N workers..." while they run.
- A card number or `api_key: ...` is stored and shown masked. A screen note names the kind of mask, not the value.
- A prompt that asks the model to ignore its instructions is refused before any model call.

The API prints one trace per turn: a `turn` span, then `chat` and `execute_tool` underneath.

## Challenges & Learnings

**Not everything can be masked.** If I masked every model call, some things would break. Tool status messages need to show instantly. Worker tasks and saved memories need to stay exactly as written. So masking only runs on your message and the lead's final answer. The spending check still runs before *every* model call, workers included.

**Compression follows the same idea.** When you reopen a chat, you see all of it. Only the lead's next request gets shortened. A tool call is never sent without its results. If the parts that must be kept (start + latest messages) are already too big, the turn stops instead of summarizing them away.

**Blocked messages still get logged.** A refused prompt still creates a trace, so you can see blocked traffic. But the trace never includes the prompt, the refusal message, tool inputs, or what was masked.

**Workers are kept simple on purpose.** One task each, no chat history, can't create other workers, max 5 at once. If one step depends on another's result, the lead handles it after reading that result.

## License

MIT

## Author

Tomasz Mielniczek
