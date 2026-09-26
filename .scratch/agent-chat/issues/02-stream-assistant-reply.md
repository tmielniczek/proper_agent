# 02: Stream an assistant reply

**What to build:** Sending a prompt streams the configured model's reply into the thread token by token. When the reply finishes, the full assistant message is saved and the conversation sits at the top of the sidebar. A follow-up prompt in the same conversation is answered with the earlier messages still in context. Plain text only, with no tool status.

**Blocked by:** 01: Start a conversation from the first prompt

**Status:** ready-for-agent

- [x] Sending a prompt streams the assistant's reply into the thread as it is generated
- [x] When generation finishes, refreshing the conversation still shows the complete assistant message
- [x] The conversation moves to the top of the sidebar when the reply completes
- [x] A follow-up prompt in the same conversation is answered with the earlier messages still in context
- [x] The reply is plain text from the model configured in the environment, and no tool status is shown

## Comments

Implemented. Deltas are appended in the thread as they arrive, and the full assistant message is saved when generation finishes. The model name is `MODEL_NAME` or `LLM_MODEL`.
