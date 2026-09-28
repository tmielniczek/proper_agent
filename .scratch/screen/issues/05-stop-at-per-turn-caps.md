# 05: Stop a turn that has already hit a per-turn cap

**What to build:** Before a model call starts, from the lead or a worker, the turn stops when it already has 10 model calls, already has at least 8,000 tokens, or the previous model call in this turn reported no token count. The call that crosses a token cap finishes. The reply is one Stopped sentence, finished tool results and worker results stay, and there is no cost note. A worker that would pass the call count returns that same sentence as its task error and does not call the model. The other workers in that spawn continue, and the lead gets no further model call.

**Blocked by:** 04 Show the cost of a finished turn

**Status:** ready-for-agent

- [x] The 10th model call of a turn starts and the 11th does not
- [x] That stop keeps tool results and worker results already stored, and replies only `Stopped: this turn reached 10 model calls.`, with no cost note
- [x] A model call that crosses 8,000 tokens in this turn finishes, and the next model call does not start, replying only `Stopped: this turn reached 8,000 tokens.`
- [x] One call that itself costs more than 8,000 tokens finishes, shows a cost note, and leaves the next turn free of the per-turn cap
- [x] A model call that reports no token count counts as one call, adds nothing to the token totals, and stops the next model call with only `Stopped: this turn's token use could not be counted.`
- [x] A reported count of zero counts as a real total
- [x] When the call count and another of these caps both apply, the call-count message wins, then the per-turn token message, then the missing-count message
- [x] The per-turn call count and per-turn token total exist only for that turn
- [x] Workers that still fit under the remaining call count finish, and a worker that would pass the count returns `{"task": "<task>", "error": "<the Stopped sentence>"}` and does not call the model
- [x] Parallel workers take a call slot under one lock, so two workers cannot both pass the last slot
- [x] The other workers in that spawn keep going, and the lead gets no further model call afterward. The turn stores the Stopped sentence as the next assistant message and skips the cost note
- [x] A refusal is one `delta` of the Stopped sentence, then `done`
