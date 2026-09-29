# Turn spans

**Status:** ready-for-agent

## Problem Statement

A turn calls the language model, runs tools, and may start workers, and none of that timing or token use is visible outside the thread. The screen note shows the turn's model-call count and total tokens after a finished turn. It does not show input tokens, output tokens, which tool ran, whether that work succeeded, or how long the model call took. A phrase-list or budget refusal never appears as measured traffic. A demo of this app cannot show the shape of telemetry a real deployment would emit.

## Solution

Each turn emits one trace to the console. The root span is the turn. Each model call is a child span, and each tool run is a child of the model call that requested it. Worker model calls and their tool runs hang off the spawn's tool run. A refusal before any model call still emits the turn span. Spans carry the caller, the model, input tokens, output tokens, the tool name, a status, and a refused-task count. Latency is the span's duration. Prompt text, tool arguments, tool results, memory, and task text stay off the spans. The screen keeps gating spend and writing the screen note.

## User Stories

1. As an operator, I want each handled prompt to emit one turn span named `turn`, so that the turn is the root of the trace.
2. As an operator, I want every span to carry the service name `agent-chat`, so that the demo matches a named service.
3. As an operator, I want a phrase-list refusal to emit that turn span with `app.status` `refused` and no model-call span, so that a gated prompt still shows up as traffic.
4. As an operator, I want a daily-budget refusal before any model call to emit the same kind of turn span, `refused`, with no model-call span, so that a budget gate is visible.
5. As an operator, I want a prompt that matches the phrase list while the daily budget is already spent to stay a single `refused` turn with no model-call span, so that the phrase list's precedence is what the trace shows.
6. As an operator, I want a `refused` turn span to have OpenTelemetry status OK and no `error.type`, so that a gate is not counted as a service error.
7. As an operator, I want the refusal sentence and the prompt text absent from the turn span, so that the trace does not store what the screen kept out of the thread.
8. As an operator, I want a finished lead reply to add a span named `chat {model}` under the turn, so that the model call is a child of the turn.
9. As an operator, I want that chat span to set `gen_ai.operation.name` to `chat`, `gen_ai.provider.name` to `openai`, and `gen_ai.request.model` to the configured model name, so that a collector can read it as a chat call.
10. As an operator, I want the lead's chat span to set `app.caller` to `lead` and `app.status` to `ok`, so that I can tell who made the call.
11. As an operator, I want `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens` on that span to be the counts the provider reported for the call, so that input and output are separate.
12. As an operator, I want the chat span to end when the model stream ends, and a tool run it requested to start after that, so that the model latency excludes the tool.
13. As an operator, I want the chat span's OpenTelemetry status to be OK when `app.status` is `ok`, with no `error.type`, so that a successful call is not an error.
14. As an operator, I want a second lead model call, after tools, to be another `chat` span directly under the turn, so that the calls are siblings.
15. As an operator, I want a compaction summary to be a `chat` span under the turn with `app.caller` `summary`, starting before the lead's chat span, so that the summary call is part of the same turn.
16. As an operator, I want a summary call the provider rejects to use `app.status` `provider_rejection` on that chat span and `stopped` on the turn, so that the turn matches the too-large stop the user sees.
17. As an operator, I want a finished model call that reports a total and omits the input/output split to stay `ok` with those two attributes unset, so that a missing split is not a failed call.
18. As an operator, I want the screen to keep billing the total tokens when the split is missing, so that the cost check is unchanged.
19. As an operator, I want `get_weather` to emit `execute_tool get_weather` under the chat span that requested it, with `gen_ai.operation.name` `execute_tool`, `gen_ai.tool.name` `get_weather`, and `app.status` `ok`, so that the tool run is visible.
20. As an operator, I want the location, the search query, and the calculator expression absent from those spans, so that tool arguments stay out of the trace.
21. As an operator, I want `search_database` and `calculator` to emit the same kind of tool span, named with that tool, so that each mocked tool is distinguishable.
22. As an operator, I want a calculator expression the tool cannot evaluate to stay `app.status` `ok`, so that a result it still returns counts as a finished run.
23. As an operator, I want a memory save to emit `execute_tool long_term_memory` under the lead's chat span, with the fact text absent, so that memory is a tool run and not a copy of the fact.
24. As an operator, I want the tool result absent from the tool span, so that the trace records the run and not the payload.
25. As an operator, I want two tool runs the lead starts together to both hang off that same chat span and to overlap in time, so that parallel tool runs look parallel.
26. As an operator, I want a spawn's tool span, `execute_tool spawn_workers`, to hang off the lead chat span that requested it, so that the batch has one parent.
27. As an operator, I want each worker's chat span to hang off that spawn span with `app.caller` `worker`, so that worker calls sit inside the spawn.
28. As an operator, I want a worker's tool run to hang off that worker's chat span, so that the worker's tools stay inside the worker.
29. As an operator, I want a task past the fifth to add no worker span, and the spawn span's `app.refused_tasks` to equal how many tasks were refused, so that a refused task is a count.
30. As an operator, I want a spawn with no refused task to set `app.refused_tasks` to `0`, so that the count is always present on a spawn span.
31. As an operator, I want the task text absent from the spawn span and from the worker's chat span, so that a task is not copied into the trace.
32. As an operator, I want a spawn that returns its batch to stay `app.status` `ok` when a worker inside it failed, so that the batch's span matches the finished spawn.
33. As an operator, I want a worker model call the provider rejects to be `provider_rejection` on that chat span while the spawn stays `ok` and the lead can still finish the turn `ok`, so that a worker failure stays on the worker.
34. As an operator, I want a blank task in an otherwise valid spawn to start no worker span and leave the spawn `ok`, so that a slot that does not start is not a refused task and not a failed plan.
35. As an operator, I want a spawn whose tasks are missing, empty, or not a list to emit an `error` tool span, `error.type` `error`, and no worker span, so that a bad plan is the spawn's own failure.
36. As an operator, I want a worker that asks to start workers, or names a tool it is not allowed to run, to add no tool span for that request, and to leave its chat span `ok`, so that a blocked tool never starts a run.
37. As an operator, I want an unknown tool on the lead to emit an `error` tool span whose `error.type` is `ValueError`, and the turn span `error`, so that a tool that raises is an error on the run and on the turn.
38. As an operator, I want a lead model call the provider rejects with 401 to set the chat span's `app.status` to `provider_rejection`, its OpenTelemetry status to ERROR, and `error.type` to `401`, so that the provider code is the error type.
39. As an operator, I want the same shape with `error.type` `429` when the provider rate-limits the call, so that the two rejections stay distinct.
40. As an operator, I want that lead rejection to set the turn span to `error` and still drop the turn from the thread, so that telemetry follows the existing rejection.
41. As an operator, I want any other unexpected exception to set `app.status` `error`, OpenTelemetry status ERROR, and `error.type` to the exception class name, on the span that failed and on the turn, so that the class is the error type.
42. As an operator, I want a cancel during a model stream to set that chat span and the turn to `cancelled`, with OpenTelemetry status OK and no `error.type`, so that a cancel is not an error.
43. As an operator, I want a chat span that had already finished, when a later cancel arrives, to keep `ok`, so that a finished call stays finished.
44. As an operator, I want a cancel during a tool run to set that tool span and the turn to `cancelled`, and to leave the chat span that requested the tool `ok`, so that the cancel lands on the run still in flight.
45. As an operator, I want a screen stop or a context-window stop before the next model call to add no chat span for the call that does not start, and to set the turn to `stopped`, so that a call that never starts has no span.
46. As an operator, I want a model call that finishes and is then followed by a screen stop to stay `ok` on that chat span, with the turn `stopped`, so that the stop belongs to the turn.
47. As an operator, I want `stopped` and `cancelled` spans to have OpenTelemetry status OK and no `error.type`, so that a dashboard's error rate counts provider failures and unexpected exceptions.
48. As a user, I want the screen note and the mask to stay as they are, so that the thread still shows the mask and the cost.
49. As an operator, I want the secret and the screen-note text absent from every span on a masked turn, so that the trace does not undo the mask.
50. As an operator, I want the running app to print these spans on the console, so that the demo needs no collector.

## Implementation Decisions

- One tracer for the app. The running app exports spans to the console. App creation accepts an in-memory exporter used by tests, in the same place it accepts the stand-in language model. Service name is `agent-chat`. Span kind is internal.
- The turn span wraps handling of the prompt, including the phrase-list check and the daily-budget check. It ends when that handling ends. `app.status` on the turn is `ok`, `stopped`, `cancelled`, `error`, or `refused`.
- A model-call span wraps one stream. It starts before the stream and ends when the stream finishes, raises, or is cancelled. It is named `chat {model}`. Attributes: `gen_ai.operation.name` `chat`, `gen_ai.provider.name` `openai`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `app.caller` (`lead`, `worker`, or `summary`), `app.status` (`ok`, `provider_rejection`, `cancelled`, `error`). The configured model name is used for the stand-in as well as for the real client, and it is stable in tests.
- A tool-run span wraps one execution. It is named `execute_tool {tool}`. Attributes: `gen_ai.operation.name` `execute_tool`, `gen_ai.tool.name`, `app.status` (`ok`, `error`, `cancelled`). A spawn span also sets `app.refused_tasks` to the number of refused tasks, including zero. Parent of a lead or summary tool run is the chat span that requested it. Parent of a worker chat span, and of that worker's tool runs, is the spawn span.
- A call the screen or the context window refuses to start does not get a chat span. A refused task does not get a worker span. A blank slot in a valid plan does not get a worker span. A worker request that is blocked before a tool runs does not get a tool span.
- A spawn tool run is `error`, with `error.type` `error`, when the plan is missing, empty, or not a list. It is `ok` when the batch returns, including when a worker's own span failed. A tool that returns a result after catching a bad calculator expression is `ok`. A tool run that raises uses `app.status` `error` and `error.type` equal to the exception class name.
- OpenTelemetry status is ERROR, and `error.type` is set, only for `app.status` `error` and `provider_rejection`. `error.type` is `401` or `429` for a provider rejection, the exception class name for a raised failure, and `error` for a spawn plan that returns an error. `ok`, `stopped`, `cancelled`, and `refused` leave the OpenTelemetry status OK and set no `error.type`. A span already ended keeps its status when a later sibling is cancelled.
- The usage reported by a model call gains optional input and output counts, taken from the provider usage chunk. The screen still adds the total. When the split is absent, the two usage attributes are left unset and the chat span stays `ok`. The local tokenizer stays the context-window count.
- A provider rejection carries `401` or `429` so the span can set `error.type`. The client still receives the same rejection text, and the lead's rejection still drops the turn. A summary rejection still stops the turn as too large. A worker rejection still returns on that worker and lets the rest of the spawn finish.
- Spans do not carry prompt text, tool arguments, tool results, memory text, task text, refusal text, or screen-note text. They do not carry a tool-call id, a tool description, or a separate metric.
- The screen's mask, phrase list, caps, screen note, cancel, and drop-on-rejection stay as they are. This follows ADR 0001: the screen sits on the prompt and the lead's final text, and the cost check sits before every model call.
- Record an ADR for this shape: one console trace per turn, model calls and tool runs nested as above, operational attributes only, and OpenTelemetry ERROR only for `error` and `provider_rejection`. The alternatives were spans only around model calls, copying the prompt into the span, treating a stop as an error, and exporting OTLP.

## Testing Decisions

- A good test posts a prompt through the chat API, reads the server-sent events and the stored messages when it needs to prove the screen still behaved, and reads the finished spans from the in-memory exporter. It does not parse console output, and it does not call a tracer helper on its own.
- The exporter is installed through app creation, beside the stand-in model. Assert span name, parent, attributes, OpenTelemetry status, and `error.type`. Assert a chat span's end comes before the start of a tool span it requested. Assert two tool runs started together overlap.
- The stand-in reports input and output counts when a test sets them, and otherwise leaves the split unset. Its total stays `1` unless a test sets a total, so existing turns keep moving. A test marks a provider rejection as `401` or `429`.
- Assert a phrase-list refusal, a budget refusal, a cap that blocks the next call, a context-window stop, a lead rejection, a summary rejection, a worker rejection, a cancel during a stream, and a cancel during a tool. Assert the thread still drops on a lead rejection, still keeps the mask and the screen note, and still stores the cost note on a finished in-cap turn.
- Assert a secret in the prompt, a tool argument, a memory fact, and a worker task are absent from the exported attributes.
- Prior art is the chat tests that stream a reply, show tool progress, spawn workers, save a memory, compact a lead call, stop at the caps, cancel a generation, and drop a rejected turn. Prior art for replacing the tool wait is those same tool tests.

## Out of Scope

- An OTLP exporter, a collector, or a metric pipeline.
- A page that renders spans.
- Asserting the console exporter's text.
- Copying prompts, tool arguments, tool results, memory, task text, or screen notes onto spans.
- Filling input and output tokens from the local tokenizer.
- Tool-call ids, tool descriptions, or opt-in argument and result attributes.
- Changing the mask, the phrase list, the caps, the screen note, what cancel deletes, or what a provider rejection drops.

## Further Notes

Existing chat tests keep using the stand-in total of `1` and an unset token split. The running app prints spans only after the process is restarted, because the server does not reload code on its own.
