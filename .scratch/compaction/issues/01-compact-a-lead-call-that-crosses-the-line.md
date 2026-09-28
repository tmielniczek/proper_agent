# 01: Compact a lead call that crosses the line

**What to build:** A lead call whose messages are at or under 80% of the context window receives the full transcript and makes no extra model call. A lead call over that line receives a compaction: the head, one summary, and a tail of the last 6 stored messages that are not already in the head. The stored transcript still has every message, and the brief is only for the lead.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] The context window is 50,000 tokens unless a test passes a smaller window. The compaction line is 80% of that window, rounded down to a whole token. For the default window that line is 40,000
- [ ] A lead call at or under the line, including a list of exactly the line, is sent in full, with no extra tool-free call
- [ ] A lead call over the line is the head, one user message that starts with `Summary of omitted messages:`, and the tail. The brief is the summary call's text with surrounding whitespace removed
- [ ] The head is the memory preface, when memories exist, and the conversation's first stored user message, masks included. No preface is sent when there are no memories
- [ ] That first user message is sent only in the head when it is also among the latest messages
- [ ] The tail is the last 6 stored messages that are not already in the head. Each user message, assistant message, and tool message counts as one. The memory preface takes none of those slots
- [ ] A summary call is made only when a middle exists and the full list is over the line. That call reads the whole middle
- [ ] The stored transcript keeps every user message, assistant message, and tool message. The summary is absent from the thread
- [ ] Screen notes stay on the thread and out of the head, the tail, and the summary input
- [ ] A worker still receives its instruction and its task, and its own tool loop is left uncompacted
- [ ] A phrase-list refusal makes no summary call and no lead call
- [ ] Tool schemas are left out of every token count. The same count is used for the full list, and the memory preface is included when it will be sent
