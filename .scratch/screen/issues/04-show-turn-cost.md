# 04: Show the cost of a finished turn

**What to build:** A turn that finishes inside the caps shows one cost screen note on the closing answer. The note counts every model call the lead and the workers started, adds this turn's tokens to today's total, and is still there after reload. When the prompt and the answer were both masked, the prompt note stays under the user's message and the answer note, then the cost note, stay under the answer.

**Blocked by:** 01 Mask the prompt and show the screen note, 03 Mask the lead's closing answer

**Status:** ready-for-agent

- [ ] A finished turn that stayed inside the caps shows `Screen: 3 model calls, 1,200 tokens. Today 4,000 of 50,000.`
- [ ] One call reads `1 model call` and one token reads `1 token`
- [ ] The cost note counts every model call the lead and the workers started, and adds this turn's tokens into today's total
- [ ] The number added for a call is that call's total tokens. Unless a test sets one, the stand-in reports 1, so a turn that calls the model more than once still proceeds. A test can set a total
- [ ] The cost note is on the closing answer after reload, and the prompt's mask note is on the user's message after reload
- [ ] When the prompt and the answer were masked and the turn finished, the prompt note is under the user's message and the answer note, then the cost note, are under the answer
- [ ] The closing assistant message carries those notes in `screen_notes` in that order. The stream emits a `screen` event with the cost note text. After `done`, the thread is the stored messages, so a live note is not shown a second time
- [ ] A mocked tool call, on its own, adds neither a model call nor tokens
- [ ] Every ordinary successful turn emits `prompt` and a cost `screen` event, and the closing assistant message carries that cost note
