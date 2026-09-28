# 03: Mask the lead's closing answer

**What to build:** The lead's closing answer is held until the same mask has been applied, then streamed and stored in that masked form, with a screen note under the answer when something was replaced. A sentence the lead streams together with a tool call appears immediately and is stored unchanged. A memory and a worker's task are sent as written.

**Blocked by:** 01 Mask the prompt and show the screen note

**Status:** ready-for-agent

- [ ] The lead's closing answer, the reply that contains no tool call, is held until it has been masked, and only then streamed
- [ ] A card number, social security number, or labeled secret in that closing answer is replaced the same way as in a prompt, and the stored answer matches what was shown
- [ ] A mask in the closing answer adds the same screen note under that answer, carried on that message in `screen_notes`
- [ ] Deltas of the closing answer are the masked text, and none of those deltas arrive before the answer is complete
- [ ] A sentence the lead streams together with a tool call appears immediately and is stored unchanged, even when it contains a card number
- [ ] That tool-call sentence gets no mask note
- [ ] A memory sent to the lead is unchanged, even when the fact contains a card number
- [ ] A worker's task is sent unchanged, even when the lead copied a card number into it
