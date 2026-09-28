# 02: Keep memories away from workers, cancel, and rejected turns

**What to build:** A worker never sees the memory list and cannot save a memory. Cancel during a save stores nothing. A provider rejection before the save stores nothing and drops the turn. A memory whose save already finished stays saved when a later rejection drops that turn's messages.

**Blocked by:** 01: Save a memory and show it on the lead's next turn

**Status:** ready-for-agent

- [ ] A worker's model call is the worker instruction plus its task, with no memory list
- [ ] A worker is offered only weather, database search, and the calculator
- [ ] A worker that calls `long_term_memory` comes back as an error for that task, and the other workers in the spawn still finish
- [ ] A reply that saves a memory and also spawns workers runs one tool call after another
- [ ] Cancel during the save wait leaves the conversation at the user's prompt and stores no memory, so a following turn has no memory list
- [ ] A provider rejection before the tool runs stores no memory and drops the turn
- [ ] A memory whose save already finished remains when a later provider rejection drops that turn's messages, and another conversation's next turn still receives it
