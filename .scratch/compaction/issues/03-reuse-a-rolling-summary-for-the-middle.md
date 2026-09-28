# 03: Reuse a rolling summary for the middle

**What to build:** A conversation keeps a rolling summary in memory for the middle already folded in. The first summary reads the whole middle. A later one reads the previous brief plus only the messages that have since entered the middle. An unchanged middle reuses the brief and makes no summary call. Cancel drops that brief only when it deletes a message the brief covers.

**Blocked by:** 01 Compact a lead call that crosses the line, 02 Keep a tool burst whole on the tail

**Status:** ready-for-agent

- [ ] The first summary for a conversation reads the whole middle
- [ ] A later summary reads the previous brief plus only the messages that are in the middle and not yet folded
- [ ] When the middle has not gained a message, no summary call is made, and the next compacted lead call still receives that brief
- [ ] A message already folded stays folded. When the tail also includes that message, the lead sees both the brief and the raw message
- [ ] A new process has no rolling summary, so the next compaction reads the middle from the transcript again
- [ ] Another conversation keeps its own rolling summary, so one chat does not brief the other
- [ ] Cancel discards the rolling summary when it deletes a message that summary covers, so the next brief does not describe removed tool results
- [ ] Cancel keeps the rolling summary when every message it covers is still stored
- [ ] A new memory changes the preface on the next lead call without a new summary call when the middle is unchanged
