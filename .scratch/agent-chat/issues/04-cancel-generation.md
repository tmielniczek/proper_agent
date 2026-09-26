# 04: Cancel generation and keep only the prompt

**What to build:** While assistant text is streaming or a tool pill is still running, Cancel stops generation, aborts the model request and the tool wait, and clears any partial assistant text from the screen. The saved history for that turn ends with the user's prompt.

**Blocked by:** 03: Show mocked tool progress, then continue the answer

**Status:** ready-for-agent

- [ ] While assistant text is streaming, Cancel stops the stream and clears the partial assistant text from the thread
- [ ] While a tool pill is still running, Cancel stops the wait and clears the partial assistant text and the in-progress pill
- [ ] After cancel, refreshing shows the user's prompt as the last message, with no partial assistant message and no unfinished tool result
- [ ] The model request does not continue after cancel
