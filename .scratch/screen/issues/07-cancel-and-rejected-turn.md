# 07: Keep a cancelled turn's mask and drop a rejected turn

**What to build:** Cancel during the lead's answer keeps the masked prompt and its mask note, drops the uncommitted answer, and leaves tokens already added in place. A provider rejection still drops the whole turn, including the masked prompt, and leaves no reply.

**Blocked by:** 01 Mask the prompt and show the screen note, 04 Show the cost of a finished turn

**Status:** ready-for-agent

- [ ] Cancel during the lead's answer keeps the masked prompt and its mask note, and drops the uncommitted answer
- [ ] Cancel still deletes messages after the user's prompt. The user's message, including its screen notes, stays
- [ ] Tokens already added for a finished model call stay added after cancel
- [ ] A provider rejection drops the turn the way it does today, including the masked prompt, and leaves no reply and no prompt
