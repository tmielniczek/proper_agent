# 04: Emit a spawn span with worker model calls and tool runs

**What to build:** A spawn emits `execute_tool spawn_workers` under the lead chat span that requested it. Each worker's chat span hangs off that spawn with caller `worker`, and a worker's tool run hangs off that worker's chat span. `app.refused_tasks` is how many tasks were refused, including zero. A task past the fifth and a blank task add no worker span. A plan that is missing, empty, or not a list is the spawn's own failure. A worker request that is blocked before a tool runs adds no tool span. Task text stays off the spawn span and the worker's chat span. A spawn that returns its batch stays `ok`.

**Blocked by:** 03: Emit a tool-run span for each lead tool, including memory

**Status:** ready-for-agent

- [ ] `execute_tool spawn_workers` hangs off the lead chat span that requested it
- [ ] Each worker's chat span hangs off that spawn span with `app.caller` `worker`, and a worker's tool run hangs off that worker's chat span
- [ ] A task past the fifth adds no worker span, and the spawn span's `app.refused_tasks` equals how many tasks were refused
- [ ] A spawn with no refused task sets `app.refused_tasks` to `0`
- [ ] The task text is absent from the spawn span and from the worker's chat span
- [ ] A spawn that returns its batch stays `app.status` `ok`
- [ ] A blank task in an otherwise valid spawn starts no worker span and leaves the spawn `ok`
- [ ] A spawn whose tasks are missing, empty, or not a list emits an `error` tool span, `error.type` `error`, and no worker span
- [ ] A worker that asks to start workers, or names a tool it is not allowed to run, adds no tool span for that request and leaves its chat span `ok`
