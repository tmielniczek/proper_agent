# 03: Emit a tool-run span for each lead tool, including memory

**What to build:** Each tool run the lead starts emits `execute_tool {tool}` under the chat span that requested it. `get_weather`, `search_database`, `calculator`, and a memory save are each distinguishable. The chat span ends before the tool run starts, and two tool runs started together overlap. A calculator expression the tool cannot evaluate still counts as a finished run. Tool arguments, the tool result, and the memory fact stay off the spans.

**Blocked by:** 02: Emit a chat span for the lead and for compaction

**Status:** ready-for-agent

- [ ] `get_weather` emits `execute_tool get_weather` under the chat span that requested it, with `gen_ai.operation.name` `execute_tool`, `gen_ai.tool.name` `get_weather`, and `app.status` `ok`
- [ ] The chat span ends before the start of a tool run it requested
- [ ] `search_database` and `calculator` emit the same kind of tool span, named with that tool
- [ ] A calculator expression the tool cannot evaluate stays `app.status` `ok`
- [ ] A memory save emits `execute_tool long_term_memory` under the lead's chat span, and the fact text is absent
- [ ] The location, the search query, the calculator expression, and the tool result are absent from those spans
- [ ] Two tool runs the lead starts together both hang off that same chat span and overlap in time
