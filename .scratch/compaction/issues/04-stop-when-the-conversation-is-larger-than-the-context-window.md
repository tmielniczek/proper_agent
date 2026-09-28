# 04: Stop when the conversation is larger than the context window

**What to build:** When a lead call cannot be sent inside the context window, the turn stops before that call with only `Stopped: this conversation is larger than the context window.` The transcript, including the new prompt, stays, and there is no cost note. A failed brief leaves the previous rolling summary as it was. A successful brief is kept even when the compacted list then stops the turn.

**Blocked by:** 03 Reuse a rolling summary for the middle

**Status:** ready-for-agent

- [ ] A full list over the line with nothing between the head and the tail stops before any model call
- [ ] A head and tail that together are over the line stop before any summary call, so protected messages are not summarized away to make room
- [ ] Every compaction stop replies only `Stopped: this conversation is larger than the context window.`, keeps the transcript including the new prompt, and carries no cost note
- [ ] A summary input over the context window stops with that sentence and makes no lead call. A summary input of exactly the context window is allowed
- [ ] A rejected summary call, an empty brief, or a whitespace-only brief stops with that sentence and leaves the transcript
- [ ] A failed or empty summary leaves the previous rolling summary and its folded messages unmoved
- [ ] A compacted list over the context window stops with that sentence and makes no lead call. A compacted list from just over the line through the context window is sent
- [ ] A successful brief is kept even when the compacted list is then over the window and the turn stops, so the next turn can reuse that brief
