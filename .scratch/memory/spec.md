# Memory

**Status:** ready-for-agent

## Problem Statement

The lead can look things up and hand tasks to workers, but anything the user asks it to keep is only in that conversation's messages. A new conversation starts blank. Asking "what's the weather where I live?" cannot use "I live in Berlin" from an earlier chat, because nothing was saved for the whole app.

## Solution

When the user asks to remember or store something, the lead calls a tool named `long_term_memory` and passes one short fact. That fact is a **memory**: it is kept for the whole app, not for one conversation. On the lead's first model call of a later turn, the app adds the saved memories to that request, newest first, up to twenty. The lead decides which facts matter. Workers never see the list. There is no search and no keyword gate. The chat shows a pill while a memory is saving, and the memory list itself never appears as a message in the thread.

## User Stories

1. As a user, I want the lead to save a memory when I ask it to remember or store something, so that a fact I care about is kept.
2. As a user, I want the lead to pass one short fact in its own words, so that the memory is a single fact rather than my whole prompt.
3. As a user, I want the saved text to be the fact the lead submitted, with surrounding whitespace removed, so that what it decided to keep is what is stored.
4. As a user, I want a second request to remember the same fact to add another memory, so that saving always appends.
5. As a user, I want no way to edit, replace, or forget a memory, so that this demo only adds facts.
6. As a user, I want to see "Saving a memory..." while the save runs, so that I can tell the lead is storing something.
7. As a user, I want that pill to pulse until the save finishes, then show complete while the answer continues, so that a memory save looks like the other tools.
8. As a user, I want the save to wait between 1 and 10 seconds before it finishes, so that it feels like the other mocked tools.
9. As a user, I want the lead to be told the fact was saved, so that it can confirm what it kept.
10. As a user, I want the thread to keep the lead's tool call, the tool result, and the answer, so that reopening the chat still shows that a memory was saved.
11. As a user, I want a reopened chat to label that call "Saving a memory...", so that the pill reads the same after refresh as it did live.
12. As a user, I want a blank or whitespace-only fact to save nothing and come back as an error, so that an empty call does not create a memory.
13. As a user, I want a missing fact or a fact that is not text to save nothing and come back as an error, so that a bad call does not create a memory.
14. As a user, I want a bad fact to still show the pill and wait, so that the failed call is visible like any other tool call.
15. As a user, I want a memory to be available in every conversation, so that a fact saved in one chat is there in the next.
16. As a user, I want a later turn in the same conversation to include the memories too, so that I do not have to switch chats for the lead to see them.
17. As a user, I want the memories added only on the lead's request to the model, so that the thread I read stays my prompts, the lead's replies, and tool calls.
18. As a user, I want an empty store to leave the lead's request as the conversation alone, so that a chat with no memories looks as it does today.
19. As a user, I want every saved memory included, up to twenty, so that the lead can use a fact even when my prompt shares no words with it.
20. As a user, I want the newest memory listed first, so that the latest fact leads the list.
21. As a user, I want a twenty-first, older memory left out of the request, so that the list stays capped.
22. As a user, I want that older memory to remain saved, so that the cap only limits what the lead sees.
23. As a user, I want the list added once at the start of the lead's turn, so that the call after a tool returns does not get a second copy.
24. As a user, I want a memory saved during this turn to show up in the tool result now and in the list on the next turn, so that the list is the memories that already existed when the turn began.
25. As a user, I want two saves on two turns to list the later fact first on the following turn, so that order follows when they were saved.
26. As a user, I want two saves in one reply to both be kept, so that one reply can store more than one fact.
27. As a user, I want the list to tell the lead that a worker cannot see memories and that a needed fact must be written into the task, so that a spawn can still use what I asked to keep.
28. As a user, I want a worker's model call to contain its task and not the memory list, so that a task still stands on its own.
29. As a user, I want workers unable to call `long_term_memory`, so that only the lead saves memories.
30. As a user, I want a worker that calls `long_term_memory` to come back as an error for that task, so that the lead can say what happened.
31. As a user, I want cancel during the save wait to leave the conversation at my prompt and store no memory, so that a stopped save does not keep a fact.
32. As a user, I want a provider rejection before the tool runs to store no memory and drop the turn, so that a rejected lead call behaves as it does today.
33. As a user, I want a memory whose save already finished to remain when a later provider rejection drops that turn's messages, so that a saved fact is not a conversation message and is not removed.
34. As a user, I want a memory save beside other ordinary tool calls in one reply to run with them at the same time, so that saving does not queue behind weather or search.
35. As a user, I want a reply that also spawns workers to keep running one tool call after another, so that a memory save does not overlap a spawn.
36. As a user, I want line breaks inside a fact to stay in the stored fact and to appear as spaces in the list, so that one memory stays one bullet.

## Implementation Decisions

- The lead's model call offers weather, database search, the calculator, spawn, and `long_term_memory`. A worker's model call offers only the three lookup tools. The memory tool's description tells the lead to call it when the user asks to remember or store something, and to pass one short fact.
- The tool takes one argument, `fact`, a string. The stored text is that string with surrounding whitespace removed. A missing fact, a non-string, or a string that is empty after trimming returns `{"error": "Memory needs a fact."}` and writes nothing. A successful save returns `{"saved": "<stored fact>"}`.
- The call emits `tool_start` with tool `long_term_memory` and display text `Saving a memory...`, waits a random 1–10 seconds, then emits `tool_end`. The wait happens for an error result too. The fact is written only after that wait, so cancel during the wait stores nothing.
- Memories are rows in the app database, separate from conversations and messages, with no link that would remove them when messages are dropped. Each row is the stored fact and the time it was saved. The same fact may appear more than once.
- Before the lead's first model call of a turn, if any memories exist, the in-memory request gains one system message at the front. It is not written to the conversation. Later model calls in that same turn keep that same message and do not add another. The message lists at most twenty memories, newest first:

```
Memories, newest first:
- {fact}

Workers cannot see these memories. If a task needs a fact, write that fact into the task.
```

  Each bullet is the stored fact with line breaks turned into spaces. An empty store adds no system message.
- A memory saved earlier in the same turn is not inserted into that system message. The lead sees it from the tool result. The next turn's list includes it.
- A worker that calls `long_term_memory` is an unknown tool for that worker and returns that worker's error. Its model messages stay the worker instruction plus the task.
- Reopening a conversation labels a stored `long_term_memory` call "Saving a memory...", using the same label map as the other tools. The live pill already takes its text from the `tool_start` event.
- Cancel still deletes messages after the user's prompt. A provider rejection on the lead's own stream still drops that turn's messages. Neither removes memories already written. A rejection before the tool finishes writes none.
- When one lead reply contains several ordinary tool calls and no spawn, those calls still run together, including a memory save. A reply that contains a spawn still runs one call after another.

## Testing Decisions

- A good test exercises the chat API only: post a prompt, read the server-sent events, read the stored messages, and read what the stand-in model was sent and which tools it was offered. It does not call internal helpers, and it does not render the page.
- Assert `tool_start` display text `Saving a memory...`, the saved tool-call arguments, and the tool-result JSON `{"saved": "<fact>"}` or `{"error": "Memory needs a fact."}`. Assert the stored conversation has no system message and no memory row of its own.
- Assert the lead's first model call of a later turn, including a turn in another conversation, begins with the memory system message when memories exist, lists at most twenty facts newest first, and is unchanged when the store is empty. Assert the following model call in that turn contains that system message once.
- Assert a worker's model messages are the instruction plus the task, that the worker is offered only the three lookup tools, and that a worker call to `long_term_memory` is that worker's error.
- Assert cancel during the save wait leaves only the user's prompt and that a following turn has no memory list. Assert a provider rejection after a finished save drops the turn's messages and that another conversation's next turn still receives the memory.
- Prior art is the chat tests that stream a reply, show tool progress, persist tool results for a later turn, spawn workers, cancel a generation, and drop a rejected turn.

## Out of Scope

- A browser or component test for the pill. The server-sent events and the stored tool call are the contract.
- Forgetting, editing, or replacing a memory.
- Keyword overlap, embeddings, or any other gate that would hide a memory from the lead.
- A screen or endpoint that lists memories.
- Workers reading or saving memories.
- A conversation-delete action. Memories are simply not stored as conversation messages.
- Changing the mock payloads or the 1–10 second wait on weather, database search, or the calculator.
- An ADR. The cap, the full list, and the lead-only save are easy to reverse.

## Further Notes

The list is the whole store, capped at twenty, because a prompt like "what's the weather where I live?" shares no useful words with "The user lives in Berlin." The lead is what matches them. The running backend must be restarted before this is visible, because the server process does not reload code on its own.
