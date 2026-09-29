# 02: Emit a chat span for the lead and for compaction

**What to build:** A finished lead reply adds a span named `chat {model}` under the turn, carrying the chat attributes, the caller, and the provider's input and output token counts. The span ends when the model stream ends. A second lead model call after tools is another chat span directly under the turn. A compaction summary is a chat span under the same turn with caller `summary`, starting before the lead's chat span. When the provider reports a total and omits the input/output split, the chat span stays `ok` with those two attributes unset, and the screen still bills the total.

**Blocked by:** 01: Emit one turn span for every handled prompt

**Status:** ready-for-agent

- [ ] A finished lead reply adds a span named `chat {model}` whose parent is the turn span
- [ ] That span sets `gen_ai.operation.name` to `chat`, `gen_ai.provider.name` to `openai`, and `gen_ai.request.model` to the configured model name, including when the stand-in language model handles the call
- [ ] The lead's chat span sets `app.caller` to `lead` and `app.status` to `ok`, with OpenTelemetry status OK and no `error.type`
- [ ] `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens` are the counts the provider reported for that call
- [ ] The chat span ends when the model stream ends
- [ ] A second lead model call, after tools, is another `chat` span directly under the turn, a sibling of the first
- [ ] A compaction summary is a `chat` span under the turn with `app.caller` `summary`, and it starts before the lead's chat span
- [ ] A finished model call that reports a total and omits the input/output split stays `ok` with those two attributes unset
- [ ] The screen still bills the total tokens when the split is missing, and the local tokenizer stays the context-window count
- [ ] The stand-in reports input and output counts when a test sets them, and otherwise leaves the split unset; its total stays `1` unless a test sets a total
