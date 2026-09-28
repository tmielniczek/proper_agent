# Spawn workers

**Status:** ready-for-agent

## Problem Statement

The chat can call weather, database search, and the calculator, but only as the one agent that owns the turn, and only one call after another. Asking for several independent pieces of work — five cities, five invoice lookups — makes the user wait through each one in line. There is no way for that agent to hand independent tasks to other agents, and no way to see those pieces running together.

## Solution

The agent that owns the turn, the **lead**, can start a **spawn**: a batch of at most five **workers** on independent **tasks**. Workers run at the same time, use the same three tools, and cannot start workers of their own. The lead keeps those three tools for a single lookup. Tasks past the fifth are **refused tasks**. The thread shows the spawn while it runs, shows each refused task as not started, and shows each worker's tool pills only during the live turn. Several ordinary tool calls in one lead reply also run together, so a reply that asks for five searches does not wait on them one by one.

## User Stories

1. As a user, I want the lead to call weather, database search, or the calculator itself for a single lookup, so that a simple question does not start a worker.
2. As a user, I want the lead to spawn when my request splits into independent tasks, so that separate pieces of work can proceed together.
3. As a user, I want each worker to receive one self-contained task and not the rest of the conversation, so that it answers only what the lead assigned.
4. As a user, I want workers in one spawn to run at the same time, so that I am not waiting on them in line.
5. As a user, I want a spawn to start at most five workers, so that one reply cannot fan out without a limit.
6. As a user, I want the first five tasks, in the order the lead submitted them, to be the ones that start, so that the cut-off is predictable.
7. As a user, I want every task after the fifth to be a refused task that does not start a worker, so that the extra work is visible and not silently dropped.
8. As a user, I want eight submitted tasks to start five workers and refuse three, so that the cap applies per spawn rather than stopping the whole batch.
9. As a user, I want the lead to be able to spawn again after a batch returns, so that a larger job can continue in a later batch.
10. As a user, I want a second spawn in the same reply to start only after the first batch has finished, so that two batches never put more than five workers in flight.
11. As a user, I want dependent steps to be the lead's next action after it reads a result, so that "find the city, then get the weather" stays with the lead.
12. As a user, I want a worker to use weather, database search, and the calculator, so that it can do the same lookups the lead can.
13. As a user, I want a worker to be unable to start another worker, so that spawning cannot recurse.
14. As a user, I want a worker that tries to spawn to come back as an error for that task, so that the lead can say what happened.
15. As a user, I want a worker to keep going until it writes a final answer or I cancel, so that it is not cut off by an extra step limit.
16. As a user, I want a worker that stops with an empty answer to return that empty text, so that the lead can deal with it as an answer rather than a crash.
17. As a user, I want the lead to receive only each worker's final text, or an error, plus the task it was given, so that the worker's own tool loop does not bury the next turn.
18. As a user, I want workers to use the same model as the lead, so that a spawn does not depend on a second configuration.
19. As a user, I want an empty spawn to return an error and start nothing, so that a call with no tasks does not pretend to run.
20. As a user, I want a blank or whitespace-only task to fill one of the five slots with an error and start no worker, so that the other tasks in that spawn still run.
21. As a user, I want a blank slot to leave the spawn pill count as the number of workers that actually started, so that "Asking 2 workers..." means two workers.
22. As a user, I want a task that is not text to fill its slot with an error, so that a bad entry does not start a worker.
23. As a user, I want one worker's rate limit, rejected key, or tool failure to be that worker's error while the others finish, so that one failure does not throw away the rest.
24. As a user, I want my prompt to stay in the conversation when a worker fails, so that a worker error is not a rejected turn.
25. As a user, I want a provider rejection on the lead's own model call to drop the turn, including my prompt, so that a rejected lead call behaves as it does today.
26. As a user, I want to see "Asking N workers..." for the whole time those workers run, including while their tool pills are up, so that I can tell the spawn is still in progress between tool calls.
27. As a user, I want N to be the number of workers that started, not the number of tasks submitted, so that a refused task is not counted as running.
28. As a user, I want one started worker to read "Asking 1 worker...", so that the label matches the count.
29. As a user, I want each refused task to show "Not started" with a short snippet of the task as soon as the spawn starts, so that I can see what was left out before the workers finish.
30. As a user, I want refused pills to sit with the spawn pill, in submission order, already marked not started, so that they do not jump around as tools finish.
31. As a user, I want a refused pill to stay when I reopen the conversation, so that the fact a task never started is still visible later.
32. As a user, I want every refused task to get a pill, however many there are, so that a long list is not quietly trimmed.
33. As a user, I want a blank refused task to show "Not started" with no snippet, so that an empty extra task is still marked.
34. As a user, I want each worker's tool to show the usual label plus a short snippet of that worker's task, such as "Checking weather... · weather in Berlin", so that two of the same tool are distinguishable.
35. As a user, I want a long task snippet to be trimmed to a short single line, so that a pill does not fill the thread.
36. As a user, I want two worker tools of the same name to finish independently, so that the first weather check does not complete the other one's pill.
37. As a user, I want worker tool pills only while the turn is live, so that reopening the chat does not replay the worker's tool loop.
38. As a user, I want the worker's own text to stay off the thread, so that the lead is the one who answers me.
39. As a user, I want a blank slot to have no pill, so that a malformed task is not presented as a refused task.
40. As a user, I want a failed worker to have no extra pill of its own, so that the lead's answer is what explains the failure.
41. As a user, I want the lead's own single tool call to keep today's label, such as "Checking weather...", so that a direct lookup looks the same as before.
42. As a user, I want several ordinary tool calls in one lead reply to run at the same time, so that five database searches show their pills together instead of in a queue.
43. As a user, I want those parallel lead tool pills to complete on their own when each call finishes, so that a fast call does not mark a slow one done.
44. As a user, I want a spawn in a reply that also contains other tool calls to keep running one call after another, so that a spawn is not overlapped with a second batch.
45. As a user, I want cancel during a spawn to abort the lead and every worker, so that in-flight tool waits stop.
46. As a user, I want a cancelled turn to leave the conversation at my prompt, so that partial worker work is not stored.
47. As a user, I want the live pills to clear when I cancel, so that a stopped turn does not keep spinning.
48. As a user, I want the stored turn to contain the lead's spawn call, one tool result, and the lead's answer, so that the worker loops are not part of the history.
49. As a user, I want the tool result to list each started slot in order with its task and either final text or an error, then the refused tasks by their task text, so that the lead knows which piece is which.
50. As a user, I want the next turn to send that spawn result back to the lead and not the worker's tool loop, so that the lead remembers the outcome without the noise.
51. As a user, I want each mocked tool a worker calls to still wait between 1 and 10 seconds, so that worker tools feel like the lead's tools.
52. As a user, I want reopening the conversation to redraw "Asking N workers..." from the stored spawn, counting only tasks in the first five that are non-blank text, so that the pill matches what started.
53. As a user, I want an empty spawn to leave no spawn pill and no refused pill, so that a call that started nothing does not look like a run.
54. As a user, I want a worker's unknown tool to be that worker's error, so that a bad tool name does not fail the whole turn.

## Implementation Decisions

- The lead's model call offers weather, database search, the calculator, and one spawn tool. The spawn tool's description tells the lead to use it when the request splits into independent tasks, and to call a tool directly for a single lookup. The tool takes one ordered list of task strings and has no mode flag.
- A worker's model call offers only the three tools. Its in-memory context is a short instruction to answer the task and use those tools, plus the task. That context is never written to the conversation.
- A spawn with a missing or non-list task payload returns the error "Spawn needs a list of tasks." An empty list returns "Spawn needs at least one task." Neither emits a spawn pill or a refused pill.
- The first five entries are slots. A non-blank string starts a worker. A blank or whitespace-only string, or a non-string, does not start a worker and comes back as that slot's error ("Task is blank." or "Task must be text."). Entries after the fifth are refused, using the original string, or an empty string when the entry is not text.
- Workers in one spawn are started together. Each worker loops until the model returns a message with no tool calls. Tool text from the worker is not streamed to the user. A provider rejection or a thrown tool becomes that worker's error. An empty final message is returned as text.
- The tool result of a spawn that actually planned slots is one object: `workers` is the slot outcomes in order, each `{task, text}` or `{task, error}`, and `refused` is the refused task strings in order. An empty or invalid spawn is `{error}` only.
- The conversation stores the lead's spawn tool call and that one tool result. Worker messages are discarded when the spawn finishes.
- Live progress is server-sent events. A spawn emits `tool_start` with tool `spawn_workers` and display text "Asking N workers..." (singular "worker" when N is 1), then one `refused_task` event per refused task with display text "Not started" or "Not started · {snippet}", then worker tool events, then `tool_end` for the spawn when every slot has finished. A worker tool event includes a unique `call_id` and display text "{usual label} · {snippet}". The snippet is the task collapsed to one line and trimmed to 80 characters, with an ellipsis when it is cut.
- Reloaded pills come from the stored spawn call, not from worker events. The spawn pill counts non-blank text tasks among the first five. Each later task is a refused pill. An empty task list draws no pills.
- When one lead reply contains more than one tool call and none of them is a spawn, those calls run together. Each emits `tool_start` and `tool_end` with that call's id, so two pills for the same tool complete separately. Results are stored in the original call order. A reply that contains a spawn keeps today's one-after-another execution, and a lone tool call keeps today's event shape without a call id.
- Cancel cancels the lead's in-flight work, including workers and tool sleeps, and deletes messages after the user's prompt. A provider rejection raised on the lead's own stream still drops the whole turn. A provider rejection inside a worker does not.

## Testing Decisions

- A good test exercises the chat API only: post a prompt, read the SSE stream, and read the stored messages. It does not call internal helpers, and it does not render the page.
- Assert the stream events and the saved roles, tool-call arguments, and tool-result JSON. Assert that a worker's model messages are the instruction plus the task, that the worker is offered only the three tools, and that a later lead turn contains the spawn result and no worker loop.
- Assert overlap by observing that two tool waits are in progress at once, for workers in one spawn and for several ordinary tool calls in one lead reply. Assert that two spawns in one reply do not overlap, and that cancel during a worker tool leaves only the user's prompt.
- Prior art is the existing chat tests that stream a reply, show tool progress, persist tool results for a later turn, and cancel a generation.

## Out of Scope

- A browser or component test for the pills. The SSE events and the stored spawn call are the contract.
- A pipeline inside a spawn. Workers do not see each other, and there is no sequential mode flag.
- A separate model, a step cap, or a time limit for workers.
- A cap on how many refused pills a spawn may show.
- Persisting a worker's tool calls for later inspection.
- Changing the mock payloads or the 1–10 second wait on the three tools.
- An ADR for the decision that the lead, not a worker pipeline, sequences dependent work.

## Further Notes

The lead's native parallel tool calls and a spawn are different. A spawn is how the lead hands out tasks and gets back final text. Several weather or search calls in one reply are still the lead's own tools; they run together so the thread shows them at the same time. The running backend must be restarted before this is visible, because the server process does not reload code on its own.
