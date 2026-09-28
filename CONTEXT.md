# Agent chat

A single-user chat where a lead answers each turn and may hand independent tasks to workers.

## Language

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
