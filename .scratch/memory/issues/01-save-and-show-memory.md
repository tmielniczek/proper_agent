# 01: Save a memory and show it on the lead's next turn

**What to build:** When the user asks to remember or store something, the lead calls `long_term_memory` with one short fact. The thread shows "Saving a memory..." for a 1–10 second wait, then the lead is told the fact was saved, and that call stays in the conversation. A later turn, in this conversation or another, sends the lead every saved memory, newest first, up to twenty. That list is not a message in the thread. An empty store leaves the lead's request unchanged.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [x] The lead is offered `long_term_memory` and calls it with one `fact` string when asked to remember or store something
- [x] The stored text is that fact with surrounding whitespace removed
- [x] A successful save returns `{"saved": "<stored fact>"}`
- [x] The thread shows "Saving a memory..." for the whole 1–10 second wait, then the pill completes and the answer continues
- [x] The conversation keeps the tool call, the tool result, and the answer
- [x] Reopening the conversation labels that call "Saving a memory..."
- [x] A missing fact, a non-string, or a blank or whitespace-only fact returns `{"error": "Memory needs a fact."}`, stores nothing, and still shows the pill and the wait
- [x] Saving the same fact again appends another memory
- [x] A later turn in the same conversation, and the first turn of another conversation, send the lead the memories
- [x] The list is a system message at the front of the lead's request and is not stored in the conversation
- [x] An empty store adds no system message, so the lead's request is the conversation alone
- [x] The message lists at most twenty memories, newest first, in this shape:

```
Memories, newest first:
- {fact}

Workers cannot see these memories. If a task needs a fact, write that fact into the task.
```

- [x] Two saves on two turns list the later fact first on the following turn
- [x] A twenty-first, older memory is left out of the request and remains saved
- [x] The list is added once at the start of the turn, so the model call after a tool returns contains it once
- [x] A memory saved during this turn is in the tool result now and in the list on the next turn, not in this turn's opening list
- [x] Two saves in one reply both finish and both are kept, and they run at the same time as other ordinary tool calls in that reply
- [x] Line breaks inside a fact stay in the stored fact and appear as spaces in the list, so one memory stays one bullet
