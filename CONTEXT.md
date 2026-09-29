# Agent chat

A single-user chat where a lead answers each turn and may hand independent tasks to workers.

## Language

**Turn**:
The work from one user prompt until a final text, a stop, a refusal, a rejection, or a cancel.
_Avoid_: Request, session

**Lead**:
The agent that owns the user's turn and may start workers to carry out tasks.
_Avoid_: Main agent, parent agent, orchestrator

**Worker**:
An agent a lead starts with one task. It does not see the conversation, and it cannot start a worker.
_Avoid_: Sub-agent, child agent, nested agent

**Task**:
The assignment a lead writes for a single worker, complete without the rest of the conversation.
_Avoid_: Prompt, query

**Spawn**:
A batch of at most five workers a lead starts on independent tasks.
_Avoid_: Fan-out, delegation, sub-agent run

**Refused task**:
A task named in a spawn that does not start a worker, because that spawn already has five.
_Avoid_: Dropped task, skipped task, overflow

**Memory**:
A fact the lead saved because the user asked to keep it, kept for the whole app rather than for one conversation.
_Avoid_: Note, context, long-term memory

**Screen**:
The check on the user's prompt and the lead's final text, and the cost check before a model call.
_Avoid_: Middleware, interceptor, guardrail

**Screen note**:
A status line in the thread that records a mask or the cost of a finished turn, without the secret.
_Avoid_: Log, middleware log

**Model call**:
A request to the language model. The lead, a worker, or compaction may make one.
_Avoid_: LLM request, completion

**Tool run**:
One execution of a tool a model call requested.
_Avoid_: Invocation, function call

**Mask**:
A social security number, card number, or labeled secret replaced in a prompt or in the lead's final text before that text is stored or shown.
_Avoid_: Redaction, sanitization

## Compaction

**Context window**:
The token capacity of one lead model call.
_Avoid_: Memory, daily budget, turn cap

**Compaction**:
The head, one summary, and a tail standing in for the lead's messages on a model call. Stored messages stay the transcript.
_Avoid_: Truncation, pruning

**Head**:
The memory preface, when one is sent, together with the conversation's first user message.

**Tail**:
The latest messages of the conversation kept in full on a compacted model call.

**Tool burst**:
An assistant message that requests tools, together with the tool messages that answer those requests.
_Avoid_: Tool pair, tool round

**Summary**:
The user message that stands in for the messages between the head and the tail.

**Rolling summary**:
The summary kept for a conversation, covering the middle already folded in.
_Avoid_: Stored summary, transcript summary
