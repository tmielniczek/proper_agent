# 05: Drop a turn when the model rejects it

**What to build:** If the provider rejects the API key or rate-limits the request, the thread shows an error and that turn is not saved. No user prompt and no partial assistant text from the failed attempt remain. The sidebar is unchanged by the failure.

**Blocked by:** 02: Stream an assistant reply

**Status:** ready-for-agent

- [x] When the provider rejects the API key, the thread shows an error and the failed turn is not saved
- [x] When the provider rate-limits the request, the thread shows an error and the failed turn is not saved
- [x] After refresh, the conversation does not contain the prompt or any assistant text from that failed turn
- [x] The sidebar order and titles are unchanged by the failed turn

## Comments

Implemented. A rejected API key or a rate limit emits an SSE error, drops that turn's prompt and any partial assistant text, and leaves the sidebar order and titles as they were.
