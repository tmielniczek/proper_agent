# 03: Show mocked tool progress, then continue the answer

**What to build:** When the agent calls weather, database search, or the calculator, the thread shows an inline status pill with a pulse for the whole wait. The wait lasts a random 1–10 seconds, then the pill completes and the answer keeps streaming. Weather returns a sunny 21° forecast with 45% humidity for the requested location. Search returns one mock record that includes the query. The calculator returns the value of a safe basic expression, or 42 when it cannot evaluate it. Tool calls and results stay in the conversation so a later turn can use them.

**Blocked by:** 02: Stream an assistant reply

**Status:** ready-for-agent

- [x] A `get_weather` call shows an inline pill reading `Checking weather...` with a pulse until the tool finishes
- [x] A `search_database` call shows a pill reading `Searching database...`
- [x] A `calculator` call shows a pill reading `Calculating...`
- [x] Each tool waits between 1 and 10 seconds before the agent continues
- [x] When the tool finishes, the pill shows complete and the assistant's answer continues streaming
- [x] Weather returns a sunny 21° forecast with 45% humidity for the requested location
- [x] Search returns one mock record that includes the query
- [x] The calculator returns the value of a safe basic expression, or 42 when it cannot evaluate it
- [x] After refresh, the conversation still contains the tool call, the tool result, and the final answer
- [x] A later turn can use the tool results already stored in the conversation

## Comments

Implemented. Tool calls stream `tool_start` / `tool_end`, wait 1–10 seconds, then the answer continues. The call, the mock result, and the final answer stay in the conversation for later turns.
