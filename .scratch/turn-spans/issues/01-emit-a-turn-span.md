# 01: Emit one turn span for every handled prompt

**What to build:** Each handled prompt emits one console trace whose root span is named `turn`, with service name `agent-chat`. A phrase-list refusal, a daily-budget refusal, and a phrase-list hit while the daily budget is already spent are each a single `refused` turn with no model-call span. A finished in-cap reply is an `ok` turn. The prompt and the refusal sentence stay off the span. Record an ADR for this trace shape: one console trace per turn, model calls and tool runs nested under it, operational attributes only, and OpenTelemetry ERROR only for `error` and `provider_rejection`.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Posting a prompt through the chat API finishes one span named `turn`, and the running app prints that span on the console
- [ ] Every span carries the service name `agent-chat`, and the span kind is internal
- [ ] A phrase-list refusal emits that turn span with `app.status` `refused`, OpenTelemetry status OK, no `error.type`, and no model-call span
- [ ] A daily-budget refusal before any model call emits the same kind of turn span
- [ ] A prompt that matches the phrase list while the daily budget is already spent stays a single `refused` turn with no model-call span
- [ ] The refusal sentence and the prompt text are absent from the turn span
- [ ] A finished in-cap reply emits the turn span with `app.status` `ok`
- [ ] A test reads finished spans from an in-memory exporter installed through app creation, beside the stand-in language model, and does not parse console output or call a tracer helper on its own
- [ ] An ADR records this shape, including the rejected alternatives: spans only around model calls, copying the prompt into the span, treating a stop as an error, and exporting OTLP
