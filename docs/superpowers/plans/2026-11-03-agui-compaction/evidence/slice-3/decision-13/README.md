# Slice 3, task 4: decision 13 on de.NBI's qwen (2026-11-03)

Instance `denbi-agui-01` (`agent-service-1`), model `qwen3.8-27b`, window `W` = 262144 (LiteLLM's
`max_input_tokens`, task 1). Output cap raised to `C` = 699056 bytes for this check only; `N` = 87382. One
session, `98d90408-5c1c-4a26-b549-95deb4898a05`. Archive: `2026-11-03T151253Z_denbi-agui-01` (controller).

| Step | Setup | Result |
|---|---|---|
| 2 | compaction disabled | "Run `seq 1 87382` … tell me only the last line": the tool call ran, then the request was **refused before inference**: 400, `litellm.ContextWindowExceededError` "Context Window exceeded for given call … Max Input Tokens=262144, Got=316927". The run is `failed`, `compactions: []` ([`01-overflow-disabled.png`](01-overflow-disabled.png)) |
| 3 | compaction enabled, `context_window_tokens: null` (agent from `30cdc66`) | Same session, "What was the last line?": one compaction, trigger `overflow`, 3 messages cut, the next request 3312 input tokens; the run `completed` and answered `87382` ([`02-recovered.png`](02-recovered.png), [`03-recovered-open.png`](03-recovered-open.png)) |

[`run-log.json`](run-log.json): the two runs' `status`, `usage`, `compactions` and the error's start, from the
archive's `agent-runs.jsonl`. Checked for the instance's canary values and the LLM key first: none.

## Findings

- **The refusal is LiteLLM's, not vLLM's.** de.NBI's gateway counts the tokens itself (`_pre_call_checks`) and
  refuses, so the request never reaches vLLM, and its wording ("Context Window exceeded") was not in the
  overflow list: step 3 would have failed as step 2 did. Fixed in `30cdc66` (the list gains `context window
  exceeded`, both tests use the real body) before step 3 ran, so step 3 ran once, with the fix.
- **The tool result was cut, by the agent's own cap.** `seq 1 87382` printed 779703 bytes with `\r\n` line
  ends, more than the plan's `8 N`: 699014 shown, `[truncated: …]` at the end. The cap took (`agent.yaml`
  `max_output_bytes: 699056`); the request still overflowed by 21 %, which is all the check needs.
- **The estimate under-counts qwen's digits.** The agent estimated 237599 tokens for what LiteLLM counted as
  316927 (`CHARS_PER_TOKEN` = 3; qwen splits numbers into single digits). With task 1's window set, a
  proactive trigger at 80 % of `W` would still have fired here (209715), but the margin is thinner than for
  prose; the reactive path covers the rest.
- **qwen's summary is again the answer** ("The last line printed by `seq 1 87382` was: **87382**"), the finding
  already in `BACKLOG.md` from task 3.
