# 06: Share today's token budget

**What to build:** Today's token total is one number for the local calendar date, stored in the app database and shared by every conversation. A call that crosses 50,000 tokens today is allowed to finish, and the next prompt is refused before any model call. The phrase list wins when both would refuse the turn. The total resets at local midnight and stays when a conversation is deleted.

**Blocked by:** 02 Refuse a prompt on the phrase list, 05 Stop a turn that has already hit a per-turn cap

**Status:** ready-for-agent

- [ ] Today's token total is shared by every conversation, so a second chat cannot spend a fresh budget
- [ ] Today's total is kept in the app database, so a later request still sees what this process already spent, and it is left in place when a conversation is deleted
- [ ] The daily total resets at local midnight. A test may move the clock that chooses the local day, then post another prompt and see the daily total start over
- [ ] A call that crosses 50,000 tokens today finishes, and the next turn is refused before any model call with `Stopped: today's token budget is used up.`
- [ ] The cost note may show a today-total above 50,000
- [ ] A prompt that is not on the phrase list, sent when today's budget is already spent, stores the masked prompt, skips the mask note, calls no model, emits no `screen` event, and replies only `Stopped: today's token budget is used up.`
- [ ] The phrase list wins when today's token budget is already spent, so the reply is the phrase-list sentence
- [ ] When the call count, the per-turn token cap, the daily cap, and a missing count all apply, the call-count message wins, then the per-turn token message, then the daily message, then the missing-count message
- [ ] That budget refusal is one `delta` of the Stopped sentence, then `done`, and the stream still emits `prompt` with the stored prompt
