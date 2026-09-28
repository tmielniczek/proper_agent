# Compaction

**Status:** ready-for-agent

## Problem Statement

The lead sends the whole stored transcript on every model call. A long conversation crowds the context window, and the lead's answers get worse as earlier turns bury the first request. Nothing in the app shortens that list. The stored thread is the conversation the user can still read, so shortening the call must not throw messages away.

## Solution

When the messages for a lead model call would exceed 80% of the context window, the lead is sent a **compaction** instead of the whole transcript: the **head**, one **summary**, and the **tail**. The context window is 50,000 tokens, so that line is 40,000 tokens. The head is the memory preface, when one is sent, and the conversation's first user message. The tail is the latest messages, kept whole so a **tool burst** is never split. The middle becomes one user message, a short brief. A **rolling summary** is kept in memory for that conversation and extended as more messages enter the middle. Stored messages stay the transcript. Workers are unchanged.

## User Stories

1. As a user, I want a lead call whose messages are at or under 40,000 tokens to receive the full transcript, so that a short conversation is not summarized.
2. As a user, I want a lead call whose messages are over 40,000 tokens to receive a compaction instead of the middle, so that the call stays inside the context window.
3. As a user, I want the context window to be 50,000 tokens, so that the 40,000-token line is 80% of that window.
4. As a user, I want the stored transcript to keep every user message, assistant message, and tool message, so that reopening the chat still shows the whole conversation.
5. As a user, I want the summary to be absent from the thread, so that the brief is only for the lead.
6. As a user, I want the head to be my first message in the conversation, so that the original request stays in the lead's call.
7. As a user, I want that first message to be the stored one, masks included, so that compaction does not recover a secret the screen already replaced.
8. As a user, I want the memory preface included in the head when memories exist, so that saved facts are still on the compacted call.
9. As a user, I want no preface in the head when there are no memories, so that an empty memory list adds nothing.
10. As a user, I want the first user message kept only in the head when it is also among the latest messages, so that the lead does not read it twice.
11. As a user, I want the tail to be the last 6 messages that are not already in the head, so that the recent exchange stays verbatim.
12. As a user, I want each user message, assistant message, and tool message to count as one toward those 6, so that a tool result takes a slot of its own.
13. As a user, I want the memory preface to take none of those 6 slots, so that memories do not push a recent message into the middle.
14. As a user, I want a tool burst kept entirely in the tail when the cut would fall inside it, so that a tool call is never sent without its results.
15. As a user, I want that burst to be the assistant message that requests the tools plus every tool message that answers those requests, so that several results from one assistant message stay together.
16. As a user, I want the tail to grow past 6 messages when that is what keeping the burst whole requires, so that the burst is not trimmed to fit the count.
17. As a user, I want messages already in the head to stay out of the tail even when a burst is extended, so that the first user message is still sent once.
18. As a user, I want the middle to become one user message between the head and the tail, so that the lead sees a single brief where the omitted messages were.
19. As a user, I want that user message to start with `Summary of omitted messages:` and then the brief, so that the lead treats it as background.
20. As a user, I want the brief to be the text the summary call returned, with surrounding whitespace removed, so that the lead reads the model's brief and not the instruction.
21. As a user, I want a summary call only when a middle exists and the full list is over 40,000 tokens, so that a list with nothing to fold makes no extra call.
22. As a user, I want a full list over 40,000 tokens with nothing between the head and the tail to stop before any model call, so that an oversized head and tail are not sent.
23. As a user, I want the head and the tail, together over 40,000 tokens, to stop before any summary call, so that protected messages are not summarized away to make room.
24. As a user, I want that stop, and every other compaction stop, to reply only `Stopped: this conversation is larger than the context window.`, so that the reason is one sentence.
25. As a user, I want a compaction stop to keep the transcript, including my new prompt, so that a too-large conversation does not erase the turn.
26. As a user, I want a compaction stop to carry no cost note, so that it matches the other stops.
27. As a user, I want the first summary for a conversation to read the whole middle, so that the brief starts from the omitted messages.
28. As a user, I want a later summary to read the previous brief plus only the messages that have since entered the middle, so that the call does not re-read the whole history.
29. As a user, I want no summary call when the middle has not gained a message, so that an unchanged middle reuses the brief.
30. As a user, I want that reused brief on the next compacted lead call, so that the lead still receives a summary.
31. As a user, I want a message already folded into the rolling summary to stay folded, so that a later tail does not force the middle to be written again.
32. As a user, I want the lead to see both the brief and the raw message when the tail also includes a message the brief already covers, so that a tool burst can stay whole.
33. As a user, I want a new process to have no rolling summary, so that the next compaction reads the middle from the transcript again.
34. As a user, I want another conversation to keep its own rolling summary, so that one chat does not brief the other.
35. As a user, I want cancel to discard the rolling summary when it deletes a message that summary covers, so that the next brief does not describe removed tool results.
36. As a user, I want cancel to keep the rolling summary when every message it covers is still stored, so that an unrelated cancel does not throw away a valid brief.
37. As a user, I want the summary call to offer no tools, so that the brief is text and not another tool loop.
38. As a user, I want the summary call to include middle tool results as text, so that the provider receives no bare tool role.
39. As a user, I want a summary input over 50,000 tokens to stop with the compaction sentence and make no lead call, so that the summary call itself stays inside the context window.
40. As a user, I want a summary input of exactly 50,000 tokens to be allowed, so that only a list past the window stops.
41. As a user, I want a rejected summary call to stop with the compaction sentence and leave the transcript, so that a provider rejection of the brief does not drop my prompt.
42. As a user, I want an empty or whitespace-only brief to stop with the compaction sentence, so that the lead is not sent a blank summary.
43. As a user, I want a failed or empty summary to leave the previous rolling summary unmoved, so that a failed fold does not claim messages it did not brief.
44. As a user, I want a compacted list over 50,000 tokens to stop with the compaction sentence and make no lead call, so that the lead is not sent a list past the window.
45. As a user, I want a compacted list from 40,001 through 50,000 tokens to be sent, so that a list inside the window is used even when it is over the 40,000-token line.
46. As a user, I want a successful brief kept even when the compacted list is then over the window and the turn stops, so that the next turn can reuse that brief.
47. As a user, I want the turn's existing screen cap checked before any summary call, so that a turn already at a cap does not pay for a brief.
48. As a user, I want that earlier stop to use the existing screen sentence, in the existing order — call cap, then per-turn tokens, then today's budget, then a missing count — so that compaction does not replace a screen reason.
49. As a user, I want the summary call to take one of the 10 model calls, so that a brief spends a call the lead and the workers share.
50. As a user, I want a summary that would pass 10 calls not to start, and the turn to stop with `Stopped: this turn reached 10 model calls.`, so that the call cap still wins.
51. As a user, I want the summary call's tokens added to today's budget, so that a brief spends the day.
52. As a user, I want those tokens left out of the turn's 8,000-token cap, so that reading the middle does not by itself end the turn.
53. As a user, I want the lead call to proceed after a summary when the turn's own tokens are still under 8,000 and the other caps allow it, so that the brief is followed by an answer.
54. As a user, I want a summary blocked by today's budget not to start, and the turn to stop with `Stopped: today's token budget is used up.`, so that the day stops before the brief.
55. As a user, I want a summary that crosses today's budget to finish, and the lead call not to start, with the daily sentence, so that the crossing call is kept and the next call is not.
56. As a user, I want a summary that reports no token count to count as one call, add nothing to today's total, and stop the lead call with `Stopped: this turn's token use could not be counted.`, so that a missing count still blocks the next call.
57. As a user, I want a summary that reports zero tokens to count as a real total, so that zero is not treated as missing.
58. As a user, I want a finished turn's cost note to include the summary in the call count and in today's total, and to leave it out of the turn's token figure, so that the note stays the screen's counters.
59. As a user, I want no screen note that says the turn was compacted, so that a successful brief stays quiet.
60. As a user, I want the summary text sent unmasked, even when it contains a card number, so that the screen does not rewrite the brief.
61. As a user, I want the lead's closing answer still masked, so that a secret in the answer is still covered.
62. As a user, I want a new memory to change the preface on the next lead call without a new summary call when the middle is unchanged, so that memories and the brief move separately.
63. As a user, I want screen notes left out of the head, the tail, and the summary input, so that notes stay on the thread and off the model call.
64. As a user, I want a worker to receive its instruction and its task, so that compaction does not hand the worker the conversation.
65. As a user, I want a worker's own tool loop left uncompacted, so that a worker still sees only its task.
66. As a user, I want a spawn's stored tool result, when it sits in the middle, to be folded into the brief rather than sent verbatim on the lead call, so that the middle is one summary.
67. As a user, I want a later lead call in the same turn, after new tool results, to compact against the list that now includes those results, so that each lead call judges the list it would send.
68. As a user, I want those new tool results stored in full, so that the transcript keeps them even when the next lead call was compacted.
69. As a user, I want a phrase-list refusal to make no summary call and no lead call, so that a refused prompt still spends nothing.
70. As a user, I want today's total, including summary tokens, shared by every conversation, so that a brief in one chat spends the budget the others see.
71. As a user, I want a full list of exactly 40,000 tokens sent in full, so that the line is crossed only when the count is over 40,000.
72. As a user, I want tool schemas left out of every token count, so that the offered tools do not by themselves push a call over the line.

## Implementation Decisions

- Compaction applies to lead model calls only. The lead loop keeps the full message list. Each lead call sends either that list or a compacted view. Workers, their tasks, and their tool loops are unchanged.
- The context window is 50,000 tokens unless a test passes a smaller window. The compaction line is 80% of the window, rounded down to a whole token (`window * 80 // 100`). For the default window that line is 40,000. A count equal to the line does not compact. A count over the line does.
- Token counts use the tokenizer for the configured model. The same count is used for the full list, the head plus the tail, the summary input, and the compacted list. The memory preface is included when it will be sent. Tool schemas are not included. Screen notes are not included.
- The full list is the preface, when there is one, plus every stored message in order. The head is that preface plus the conversation's first user message. The tail starts as the last 6 stored messages, then grows backward until every included tool burst is complete. A tool burst is one assistant message that carries tool calls, plus the tool messages whose ids belong to those calls. Messages that are in the head are then removed from the tail. The middle is every stored message in neither. The tail keeps stored order and stored roles.
- When the full list is over the line and the middle is empty, or the head plus the tail is over the line, the turn stops with `Stopped: this conversation is larger than the context window.` No model call is made. The transcript stays. There is no cost note.
- Otherwise a rolling summary is taken from process memory for that conversation. It records the brief and the ids of the messages already folded. If those ids are exactly the current middle, the brief is reused and no summary call is made. If there is no rolling summary, or a new process has none, the summary call reads the whole middle. If a rolling summary exists and the middle has grown, the summary call reads the previous brief plus only the messages that are in the middle and not yet folded. A message id already folded stays folded when a later tail also contains that message.
- The summary call is tool-free. It is one system instruction and one user message. The instruction asks for one short brief of decisions, tool results, and user asks that are still open, and tells the model to drop wording the lead no longer needs. When a previous brief is present, the instruction says to fold the new messages into that brief and return one brief. The user message contains the previous brief when there is one, then each included message in order: user and assistant text as that text, a tool call as its name and arguments, and a tool result as its text. It does not use the tool role.
- The summary input is allowed at exactly the context window and stops above it, with the compaction sentence, before the lead call. A provider rejection, an empty brief, or a whitespace-only brief stops the same way and does not drop the transcript. Any of those failures leaves the previous rolling summary and its folded ids as they were.
- A successful brief is stored as the rolling summary after surrounding whitespace is removed, and its folded ids become the middle it covered. The lead's summary message is the user message `Summary of omitted messages:\n` plus that brief. If the compacted list — head, that user message, and tail — is over the context window, the turn stops with the compaction sentence and the lead is not called. The new rolling summary is kept. A compacted list from just over the 80% line through the context window is sent.
- Before any summary call, the turn's screen caps are checked in the existing order: 10 model calls, 8,000 turn tokens, today's 50,000-token budget, then a missing count. The first match stops the turn with that existing sentence and makes no summary call and no lead call.
- The summary call then takes the daily budget and the 10-call cap. It does not take the 8,000-token turn cap. A block on the daily budget or the call cap stops with that existing sentence and does not call the lead. The call that crosses today's budget is allowed to finish; its tokens are added to today; the lead call is not started. The summary's token total is added to today's budget and to the turn's call count, and it is not added to the turn's token total. A missing total counts as one call, adds no tokens, and the lead call stops with the missing-count sentence. A reported zero is a real total.
- After a summary is reused or produced, the lead call takes the full screen check, including the turn token cap, then receives the compacted view and the lead tools. A finished turn's cost note is the existing note. A summary that ran is visible there as an extra call and as part of today's total, not as part of the turn's token figure. No compaction line is added.
- Cancel still deletes messages after the user's prompt. If any id the rolling summary has folded was deleted, that conversation's rolling summary is discarded. If every folded id is still stored, the rolling summary stays. A provider rejection of the lead call still drops the turn.
- The summary is not masked. The lead's closing answer is still masked. A phrase-list refusal still happens before any of this and makes no model call.
- This carves the summary call out of the per-turn token cap. [ADR 0001](../../docs/adr/0001-screen-sits-on-prompt-and-closing-answer.md) still holds for the cost check: the daily budget and the call cap run before that call. No new ADR. The rolling summary is process memory, not a stored message and not a schema change.

## Testing Decisions

- A good test exercises the chat API only: post a prompt, read the server-sent events, read the stored messages, and read what the stand-in model was sent, including whether tools were offered. It does not call a compaction helper, and it does not render the page.
- The app accepts a context window for a test. When none is given, the window is 50,000 tokens. Tests that cross the line pass a small window and build message text with the same tokenizer the app uses, so the counts are measured. Tool schemas are not part of those counts.
- Assert a list at or under the line is sent in full, with no extra tool-free call. Assert a list over the line sends the head, one user message that starts with `Summary of omitted messages:`, and the tail, and that the stored transcript still has the middle.
- Assert the tail holds a tool burst even when that makes it longer than 6, and that the first user message appears once. Assert the summary call offers no tools and carries middle text, including a tool result, as text.
- The stand-in can answer the tool-free call with a brief, with whitespace, with nothing, or by raising the provider rejection. Assert the lead call that follows receives that brief, and assert an empty, rejected, or oversized summary input stores the compaction sentence, keeps the prompt, and does not call the lead.
- Assert a second compacted call with the same middle makes no new tool-free call, and a middle that has gained a message sends the previous brief and the new text only. Assert cancel that deletes a folded message causes the next compaction to read the middle again. A new app process is the prior art for losing process memory: construct the app again and assert the next summary reads the whole middle.
- Assert the summary's reported total increases today's budget and the cost note's call count, and leaves the turn's token figure unchanged. Assert a turn already at a screen cap makes no tool-free call and stores that screen sentence. Assert a worker call is still the instruction plus the task.
- Prior art is the chat tests that stream a reply, persist tool results, spawn workers, save a memory, stop at the caps, share today's budget, cancel a generation, and drop a rejected turn.

## Out of Scope

- Compacting a worker's tool loop.
- Deleting, rewriting, or hiding stored messages.
- A screen note that compaction happened.
- Changing the 10-call cap, the 8,000-token turn cap, or the 50,000-token daily budget.
- Chunking a middle that does not fit in one summary call.
- A table of context windows by model name.
- Persisting the rolling summary across a process restart.
- Masking the summary.
- A browser test. The events, the stored messages, and the lists sent to the stand-in are the contract.
- Changing what a provider rejection of the lead call drops.

## Further Notes

A turn that compacts makes a tool-free model call before the lead call. Tests that assert an exact call count have to count that brief when the middle changed, and must not count it when the brief was reused. The stand-in reports 1 token unless a test sets a total, so a summary plus a lead call stays inside the caps. The running backend must be restarted before this is visible, because the server process does not reload code on its own.
