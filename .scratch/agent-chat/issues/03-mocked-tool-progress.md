# 03: Show mocked tool progress, then continue the answer

**What to build:** When the agent calls weather, database search, or the calculator, the thread shows an inline status pill with a pulse for the whole wait. The wait lasts a random 1–10 seconds, then the pill completes and the answer keeps streaming. Weather returns a sunny 21° forecast with 45% humidity for the requested location. Search returns one mock record that includes the query. The calculator returns the value of a safe basic expression, or 42 when it cannot evaluate it. Tool calls and results stay in the conversation so a later turn can use them.

**Blocked by:** 02: Stream an assistant reply

**Status:** ready-for-agent

- [ ] A `get_weather` call shows an inline pill reading `Checking weather...` with a pulse until the tool finishes
- [ ] A `search_database` call shows a pill reading `Searching database...`
- [ ] A `calculator` call shows a pill reading `Calculating...`
- [ ] Each tool waits between 1 and 10 seconds before the agent continues
- [ ] When the tool finishes, the pill shows complete and the assistant's answer continues streaming
- [ ] Weather returns a sunny 21° forecast with 45% humidity for the requested location
- [ ] Search returns one mock record that includes the query
- [ ] The calculator returns the value of a safe basic expression, or 42 when it cannot evaluate it
- [ ] After refresh, the conversation still contains the tool call, the tool result, and the final answer
- [ ] A later turn can use the tool results already stored in the conversation
