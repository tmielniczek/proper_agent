# 07: Keep the mask and the screen note off the trace

**What to build:** A masked turn still shows the mask and the screen note in the thread, including the cost note on a finished in-cap turn. The secret and the screen-note text are absent from every span on that turn. Spans do not undo the mask.

**Blocked by:** 02: Emit a chat span for the lead and for compaction

**Status:** ready-for-agent

- [ ] The screen note and the mask stay as they are: the thread still shows the mask and the cost
- [ ] A finished in-cap turn still stores the cost note
- [ ] The secret and the screen-note text are absent from every span on a masked turn
- [ ] Spans do not carry prompt text, refusal text, or screen-note text
