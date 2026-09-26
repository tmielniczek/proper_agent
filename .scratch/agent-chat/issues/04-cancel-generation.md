# 04: Cancel generation and keep only the prompt

**What to build:** While assistant text is streaming or a tool pill is still running, Cancel stops generation, aborts the model request and the tool wait, and clears any partial assistant text from the screen. The saved history for that turn ends with the user's prompt.

**Blocked by:** 03: Show mocked tool progress, then continue the answer

**Status:** ready-for-agent

- [x] While assistant text is streaming, Cancel stops the stream and clears the partial assistant text from the thread
- [x] While a tool pill is still running, Cancel stops the wait and clears the partial assistant text and the in-progress pill
- [x] After cancel, refreshing shows the user's prompt as the last message, with no partial assistant message and no unfinished tool result
- [x] The model request does not continue after cancel

## Comments

Implemented. Cancel aborts the model stream and any tool wait, clears partial assistant text and the in-progress pill, and leaves that turn saved as the user's prompt.
