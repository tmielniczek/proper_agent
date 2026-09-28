# Screen

**Status:** ready-for-agent

## Problem Statement

Anything the user types is sent to the model as written, and the lead's closing answer is streamed as the model produces it. A social security number, a card number, or a labeled secret in that text is stored and shown. A prompt that tells the lead to ignore its instructions is sent through. A turn can keep calling the model, including through workers, with no cap on calls or tokens.

## Solution

A **screen** checks the user's prompt before the lead starts, and the lead's final text before it is saved and shown. A social security number, a card number, or a labeled secret is replaced with a **mask** and that masked text is what is stored and sent on. A fixed list of phrases refuses the turn before any model call. Before every model call, from the lead or a worker, the screen checks three app-wide caps and stops the turn when one is already hit. The thread shows a **screen note** when the screen masks something or when a turn finishes inside the caps. The note never contains the secret.

## User Stories

1. As a user, I want a dashed social security number in my prompt, such as `123-45-6789`, replaced with `[ssn]`, so that the number is not stored or sent to the lead.
2. As a user, I want nine digits with no dashes left as I wrote them, so that an ordinary number is not treated as a social security number.
3. As a user, I want a card number of 13 to 19 digits, spaces or dashes allowed, replaced with `[card number]` when it passes the Luhn check, so that a real card number is not stored or sent.
4. As a user, I want the same shape of number left as written when it fails the Luhn check, so that a lookalike is not masked.
5. As a user, I want a run of digits shorter than 13 or longer than 19 left as written, so that only card-length numbers are considered.
6. As a user, I want `password:` or `api_key:`, in any case, to keep the label and replace the rest of that line with `[secret]`, so that a labeled secret is masked even when the value contains spaces.
7. As a user, I want text before the label on that line still scanned for a social security number or a card number, so that a number ahead of the label is not kept.
8. As a user, I want the value after the label left as one secret, so that a card number inside that value is not also rewritten as a card.
9. As a user, I want several masks in one prompt to become one screen note, kinds in this order — social security number, card number, secret — with a plural when there is more than one, so that I can see what was removed without seeing the values.
10. As a user, I want that note to read `Screen: masked 1 social security number, 2 card numbers, 1 secret`, so that the wording is stable.
11. As a user, I want a prompt with nothing to mask to show no "allowed" line and no screen note on my message, so that an ordinary turn stays quiet.
12. As a user, I want my bubble to show the masked prompt before the lead replies, so that the value I typed does not stay on screen.
13. As a user, I want a new conversation's title to be the first 30 characters of the masked prompt, so that the sidebar does not keep the secret.
14. As a user, I want a later turn to send the lead the stored masked prompt, so that the original value is not recovered from history.
15. As a user, I want a prompt refused when it contains any of these phrases, in any case: "ignore previous instructions", "ignore all previous instructions", "ignore your instructions", "ignore the instructions", "disregard your instructions", "disregard the instructions", "reveal your system prompt", "show your system prompt", "print your system prompt", "what is your system prompt", so that those requests never reach the model.
16. As a user, I want a phrase inside a longer sentence to refuse the turn, so that padding around the phrase does not slip it through.
17. As a user, I want a paraphrase that is not on that list to go through, so that the screen does not guess.
18. As a user, I want a phrase that sits only after `password:` or `api_key:` to still refuse the turn, so that hiding the phrase in the secret value does not bypass the list.
19. As a user, I want that refusal to store the masked prompt, to skip the mask note, and to reply only `Stopped: that request asks to ignore instructions or reveal the system prompt.`, so that the secret is not kept and the thread shows one reason.
20. As a user, I want that phrase-list refusal to make no model call, so that a blocked prompt spends nothing.
21. As a user, I want the phrase list to win when today's token budget is already spent, so that I hear the policy reason rather than the budget reason.
22. As a user, I want a prompt that is not on the phrase list, sent when today's budget is already spent, to store the masked prompt, skip the mask note, call no model, and reply only `Stopped: today's token budget is used up.`, so that the day stops cleanly.
23. As a user, I want the lead's closing answer held until the screen has masked it, and only then streamed, so that a secret in the answer never appears as a live token.
24. As a user, I want a card number, social security number, or labeled secret in that closing answer replaced the same way as in a prompt, so that the stored answer matches what I was shown.
25. As a user, I want a mask in the closing answer to add the same screen note under that answer, so that I can see the answer was changed.
26. As a user, I want a sentence the lead streams together with a tool call to appear immediately and to be stored unchanged, even when it contains a card number, so that the screen does not wait on tool progress.
27. As a user, I want that tool-call sentence to get no mask note, so that the note is only for text the screen actually changed.
28. As a user, I want a memory sent to the lead unchanged, even when the fact contains a card number, so that memory stays outside the screen.
29. As a user, I want a worker's task sent unchanged, even when the lead copied a card number into it, so that the screen does not rewrite tasks.
30. As a user, I want a finished turn that stayed inside the caps to show `Screen: 3 model calls, 1,200 tokens. Today 4,000 of 50,000.`, so that I can see the cost.
31. As a user, I want one call to read `1 model call` and one token to read `1 token`, so that the note agrees with the count.
32. As a user, I want that cost note to count every model call the lead and the workers started, and to add this turn's tokens into today's total, so that the numbers match what was spent.
33. As a user, I want the cost note on the closing answer after reload, and the prompt's mask note on my message after reload, so that a refresh still shows them.
34. As a user, I want both notes when the prompt and the answer were masked and the turn finished, prompt note under my message and answer note then cost note under the answer, so that each line stays with the text it describes.
35. As a user, I want the 10th model call of a turn to start and the 11th not to start, so that the call cap is 10.
36. As a user, I want that stop to keep tool results and worker results already stored, and to reply only `Stopped: this turn reached 10 model calls.`, with no cost note, so that finished work remains and the reason is a single message.
37. As a user, I want a model call that crosses 8,000 tokens in this turn to finish, and the next model call not to start, replying only `Stopped: this turn reached 8,000 tokens.`, so that the in-flight call is not cut off.
38. As a user, I want one call that itself costs more than 8,000 tokens to finish, show a cost note, and leave the next turn free of the per-turn cap, so that a per-turn cap resets on the next prompt.
39. As a user, I want a call that crosses 50,000 tokens today to finish, and the next turn to be refused before any model call with the daily message, so that the new day-cap stops the following prompt.
40. As a user, I want the cost note to be allowed to show a today-total above 50,000, so that the call which crossed the budget is still reported.
41. As a user, I want a model call that reports no token count to count as one call, add nothing to the token totals, and stop the next model call with only `Stopped: this turn's token use could not be counted.`, so that the turn does not continue without a count.
42. As a user, I want a reported count of zero to count as a real total, so that zero is not treated as a missing count.
43. As a user, I want the call-count message to win when the call count and another cap both apply, then the per-turn token message, then the daily message, then the missing-count message, so that one turn names one reason.
44. As a user, I want workers that still fit under the remaining call count to finish, and a worker that would pass the count to return an error for its task and not call the model, so that one spawn does not blow the cap.
45. As a user, I want that worker error to be the same Stopped sentence the turn will show me, so that the lead's tool result names the same reason.
46. As a user, I want the other workers in that spawn to keep going, and the lead to get no further model call afterward, so that the turn ends on the Stopped message rather than another answer.
47. As a user, I want today's token total to be shared by every conversation, so that a second chat cannot spend a fresh budget.
48. As a user, I want today's total to be kept in the app database, so that a later request still sees what this process already spent.
49. As a user, I want the daily total to reset at local midnight, so that the next local day starts at zero.
50. As a user, I want a mocked tool call, on its own, to add neither a model call nor tokens, so that only the model is capped.
51. As a user, I want cancel during the lead's answer to keep my masked prompt and its mask note, and to drop the uncommitted answer, so that cancel still leaves the prompt.
52. As a user, I want tokens already added for a finished model call to stay added after cancel, so that a cancelled turn does not refund spend.
53. As a user, I want a provider rejection to drop the turn the way it does today, so that a rejected call still leaves no reply and no prompt.
54. As a user, I want a screen note drawn as a status line rather than as my bubble or the lead's bubble, so that I can tell it from the conversation.
55. As a user, I want a refusal delivered as one piece of assistant text and then the turn marked done, so that the Stopped sentence does not dribble out of a model.

## Implementation Decisions

- The screen runs in three places. On the way in, it masks the prompt and stores the masked text, then applies the phrase list to the original prompt. On the way out, it masks only the lead's closing answer, the reply that contains no tool call, and streams that masked text. Before every model call, lead or worker, it checks the caps. Worker tasks, memory, and any assistant text saved with a tool call are not masked.
- Masking a line that contains `password:` or `api_key:` replaces from the value through the end of that line and leaves the label. Social security numbers and card numbers are found in the remaining text: a social security number is three digits, a dash, two digits, a dash, four digits; a card number is a 13-to-19-digit run, spaces or dashes allowed between digits, that passes the Luhn check. Placeholders are `[ssn]`, `[card number]`, and `[secret]`.
- The phrase list is a case-insensitive substring match on the original prompt, using the ten phrases in story 15. A match stores the masked prompt, writes no screen note, stores one assistant message with the phrase-list sentence, and does not call the model. The same shape is used for a budget refusal before the first call. When both apply, the phrase-list sentence is the one stored.
- A new conversation's title remains the first 30 characters of the stored prompt, which is already masked.
- The stream emits `prompt` with the stored prompt text before the lead starts, including on a refusal, so the client can replace the optimistic bubble. It emits `screen` with the note text when a note is produced. A refusal is one `delta` of the Stopped sentence, then `done`. Deltas of a closing answer are emitted only after that answer has been masked. Deltas that accompany a tool call are still emitted as they arrive.
- Each stored message may carry `screen_notes`, a list of strings, in the conversation payload. The user's message carries the prompt mask note when the turn was not refused. The closing assistant message carries the answer mask note, when the answer was masked, and then the cost note. A refusal message carries no screen notes. Notes are not a separate message role. After `done`, the thread is the stored messages, so a live note is not shown a second time.
- The client renders each screen note as a status line on that message, in the same family as a tool pill, not as a user or assistant bubble. Tool messages stay hidden.
- Caps, checked before a model call starts, in this order: the turn already has 10 model calls; the turn's tokens are already at least 8,000; today's tokens are already at least 50,000; the previous model call in this turn reported no token count. The matching sentences are the ones in stories 36, 37, 22, and 41. The first match wins. The call that crosses a token cap is allowed to finish. The call that would be the 11th does not start. A missing count adds no tokens and still counts as one call. A reported zero is a real count.
- Today's total is one number for the local calendar date, stored in the app database, shared by every conversation, and left in place when a conversation is deleted. The next local day starts a new total. The per-turn call count and per-turn token total exist only for that turn.
- The provider request asks for token usage. The number added is that call's total tokens. Parallel workers take a call slot under one lock, so two workers cannot both pass the last slot. A worker that does not get a slot returns `{"task": "<task>", "error": "<the Stopped sentence>"}` and does not call the model. The other workers in the spawn continue. The lead does not get another model call after that; the turn stores the Stopped sentence as the next assistant message and skips the cost note.
- Cancel still deletes messages after the user's prompt. The user's message, including its screen notes, stays. Token totals already written stay written. A provider rejection still drops the turn, including the masked prompt.
- Record an ADR for this shape: the mask and the phrase list sit on the prompt and the lead's final text, the cost check sits before every model call, and memory, worker tasks, and tool-call narration stay as written. The alternative was wrapping every model call in the mask.

## Testing Decisions

- A good test exercises the chat API only: post a prompt, read the server-sent events, read the stored messages, and read what the stand-in model was sent. It does not call the screen's helpers, and it does not render the page.
- Assert the stored user content, the title, the `prompt` event, `screen` events, deltas, and `screen_notes` on the stored messages. Assert a phrase-list or budget refusal stores the masked prompt, stores the Stopped assistant message, emits no `screen` event, and leaves the stand-in with no new call.
- Assert the closing answer's deltas are the masked text and that none of those deltas arrive before the answer is complete. Assert text saved on a tool-call message is unchanged and was streamed as it arrived.
- Assert a later lead call receives the masked history. Assert a memory preface and a worker task still contain a secret the screen was not allowed to touch.
- The stand-in model reports a token total for each scripted reply. Unless a test sets one, it reports 1, so existing turns that call the model more than once still proceed. A test can set a total, including a total that crosses 8,000 or 50,000, or can omit the total. Assert the cost note, the daily total on a later turn and in another conversation, and which Stopped sentence was stored.
- Assert the 11th call does not happen, that a worker left without a slot returns the error object and the others still return their text, and that the lead is not called again after that spawn.
- A test may move the clock that chooses the local day, then post another prompt and assert the daily total starts over. Prior art for replacing a clock is the tests that replace the tool wait.
- Assert cancel leaves the masked prompt and its screen note, and assert a provider rejection drops the turn.
- Prior art is the chat tests that stream a reply, show tool progress, persist tool results, spawn workers, save a memory, cancel a generation, and drop a rejected turn.

## Out of Scope

- A browser test for the status line. The events and the stored `screen_notes` are the contract.
- Masking memory, worker tasks, or text the lead streams with a tool call.
- Detecting paraphrases, unlabeled passwords, nine bare digits, or numbers that fail the Luhn check.
- A command allowlist, or a model call whose job is to judge the prompt.
- Counting mocked tool calls toward the caps.
- Refunding tokens when a turn is cancelled.
- A per-conversation budget, or a way to edit the phrase list or the caps from the chat.
- Changing what a provider rejection drops.

## Further Notes

Every ordinary successful turn now emits `prompt` and a cost `screen` event, and the closing assistant message carries that cost note. Tests that assert an exact event list have to expect them. The running backend must be restarted before this is visible, because the server process does not reload code on its own.
