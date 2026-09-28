# 02: Keep a tool burst whole on the tail

**What to build:** On a compacted lead call, a tool burst stays entirely in the tail, even when that makes the tail longer than 6 messages. The summary call still offers no tools, and any tool result that sits in the middle is folded into the brief as text. A later lead call in the same turn compacts the list that now includes the new tool results, which stay stored in full.

**Blocked by:** 01 Compact a lead call that crosses the line

**Status:** ready-for-agent

- [x] A tool burst is the assistant message that requests the tools plus every tool message that answers those requests
- [x] When the cut would fall inside a burst, the tail grows past 6 messages so the burst stays whole
- [x] Messages already in the head stay out of the tail even when a burst is extended, so the first user message is still sent once
- [x] The summary call offers no tools. Middle tool results are included as text, so the provider receives no bare tool role
- [x] A spawn's stored tool result, when it sits in the middle, is folded into the brief rather than sent verbatim on the lead call
- [x] A later lead call in the same turn, after new tool results, compacts against the list that now includes those results
- [x] Those new tool results are stored in full, so the transcript keeps them even when the next lead call was compacted
