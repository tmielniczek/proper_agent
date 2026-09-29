# 05: Mark provider rejections and raised failures as errors

**What to build:** A lead model call the provider rejects, an unknown tool, or any other unexpected exception marks the span that failed and the turn as errors. The provider code, or the exception class name, is `error.type`. The lead's rejection still drops the turn from the thread. A summary call the provider rejects stops the turn as too large. A worker model call the provider rejects stays on that worker: the spawn stays `ok`, and the lead can still finish the turn `ok`.

**Blocked by:** 02: Emit a chat span for the lead and for compaction, 04: Emit a spawn span with worker model calls and tool runs

**Status:** ready-for-agent

- [ ] A lead model call the provider rejects with 401 sets the chat span's `app.status` to `provider_rejection`, its OpenTelemetry status to ERROR, and `error.type` to `401`
- [ ] The same shape uses `error.type` `429` when the provider rate-limits the call
- [ ] That lead rejection sets the turn span to `error` and still drops the turn from the thread
- [ ] The client still receives the same rejection text as before
- [ ] An unknown tool on the lead emits an `error` tool span whose `error.type` is `ValueError`, and the turn span is `error`
- [ ] Any other unexpected exception sets `app.status` `error`, OpenTelemetry status ERROR, and `error.type` to the exception class name, on the span that failed and on the turn
- [ ] A summary call the provider rejects uses `app.status` `provider_rejection` on that chat span and `stopped` on the turn
- [ ] A worker model call the provider rejects is `provider_rejection` on that chat span, the spawn stays `ok`, and the lead can still finish the turn `ok`
- [ ] A test can mark a provider rejection as `401` or `429`
- [ ] OpenTelemetry status is ERROR, and `error.type` is set, only for `app.status` `error` and `provider_rejection`
