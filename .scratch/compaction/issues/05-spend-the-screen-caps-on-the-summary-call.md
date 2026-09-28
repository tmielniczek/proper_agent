# 05: Spend the screen caps on the summary call

**What to build:** A summary call spends one of the 10 model calls and today's token budget, and it does not spend the turn's 8,000-token cap. Caps that already apply stop the turn with the existing screen sentence before any summary call. The finished turn's cost note counts the brief as a call and as part of today's total, and leaves it out of the turn's token figure. The brief is sent unmasked. The lead's closing answer is still masked.

**Blocked by:** 01 Compact a lead call that crosses the line

**Status:** ready-for-agent

- [x] Before any summary call, the turn's screen caps are checked in the existing order: call cap, then per-turn tokens, then today's budget, then a missing count. The first match stops with that existing sentence and makes no summary call and no lead call
- [x] The summary call takes one of the 10 model calls. A summary that would pass 10 calls does not start, and the turn stops with `Stopped: this turn reached 10 model calls.`
- [x] The summary call's tokens are added to today's budget, which every conversation shares. Those tokens are left out of the turn's 8,000-token cap
- [x] The lead call proceeds after a summary when the turn's own tokens are still under 8,000 and the other caps allow it
- [x] A summary blocked by today's budget does not start, and the turn stops with `Stopped: today's token budget is used up.`
- [x] A summary that crosses today's budget finishes, its tokens are added to today, and the lead call does not start, with the daily sentence
- [x] A summary that reports no token count counts as one call, adds nothing to today's total, and stops the lead call with `Stopped: this turn's token use could not be counted.` A reported zero counts as a real total
- [x] A finished turn's cost note includes the summary in the call count and in today's total, and leaves it out of the turn's token figure. No screen note says the turn was compacted
- [x] The summary text is sent unmasked, even when it contains a card number. The lead's closing answer is still masked
