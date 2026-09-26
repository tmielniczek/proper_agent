# 01: Start a conversation from the first prompt

**What to build:** On an empty chat screen, submitting a prompt creates a conversation titled with the first 30 characters of that prompt, shows the prompt in the thread, and lists the conversation at the top of the sidebar. Refreshing and reopening the thread shows the same prompt. No model reply yet.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [x] Submitting `"What is the current temperature in Berlin and calculate 2+2?"` on an empty chat creates a conversation titled `"What is the current temperatur"`
- [x] The new conversation appears at the top of the sidebar
- [x] The thread shows the submitted prompt
- [x] Refreshing the page and opening the conversation from the sidebar shows the same prompt
- [x] Conversations are listed with the most recently active one first
- [x] The thread contains only the user's prompt

## Comments

Implemented. The title is the first 30 characters of the prompt. The spec’s quoted example (`What is the current temperatu`) was one character short.
