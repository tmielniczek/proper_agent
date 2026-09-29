# 06: Mark a cancel and a stop without counting them as errors

**What to build:** A cancel during a model stream or a tool run marks the work still in flight, and the turn, as `cancelled`. A screen stop or a context-window stop marks the turn `stopped` and adds no chat span for a model call that never starts. A span that already finished keeps `ok`. `stopped` and `cancelled` are not service errors.

**Blocked by:** 03: Emit a tool-run span for each lead tool, including memory

**Status:** ready-for-agent

- [ ] A cancel during a model stream sets that chat span and the turn to `cancelled`, with OpenTelemetry status OK and no `error.type`
- [ ] A chat span that had already finished, when a later cancel arrives, keeps `ok`
- [ ] A cancel during a tool run sets that tool span and the turn to `cancelled`, and leaves the chat span that requested the tool `ok`
- [ ] A screen stop or a context-window stop before the next model call adds no chat span for the call that does not start, and sets the turn to `stopped`
- [ ] A model call that finishes and is then followed by a screen stop stays `ok` on that chat span, with the turn `stopped`
- [ ] `stopped` and `cancelled` spans have OpenTelemetry status OK and no `error.type`
- [ ] A span already ended keeps its status when a later sibling is cancelled
