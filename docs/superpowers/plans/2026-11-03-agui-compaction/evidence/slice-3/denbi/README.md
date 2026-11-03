# Slice 3, task 3: a de.NBI session on qwen compacts (2026-11-03)

Instance `denbi-agui-01` (`agent-service-1`), model `qwen3.8-27b`, agent and chat UI from
`impl/agui-compaction-3-denbi-docs` at `9797544`. The scripted session is `sessions.py --scenario compaction-live`:
`seq 1 3000`, then "tell me only the last line", once per turn. For this check only, the window
(`spe_agent_context_window_tokens`) was set small in the private instance file, then put back to task 1's value
afterwards. Archive: `2026-11-03T145234Z_denbi-agui-01` (index row 01: `Compactions` 3; row 02: 1).

| Folder | Window | Result |
|---|---|---|
| [`window-20000/`](window-20000/) | 20000 (as the plan said) | **Failed.** One turn compacted 3 times, then `RUN_ERROR` "The conversation is still too long after compacting it. Start a new chat." |
| [`window-40000/`](window-40000/) | 40000 | **Passes.** Turns 1 and 2 ran without compacting; turn 3 compacted once (`threshold`, estimated 43261 tokens, 15 messages cut, the next request 3756 input tokens) and the model then still answered `3000` |

Each folder: the divider and the opened summary (`01-`, `02-` screenshots), the archived chat (`chat.md`, its
`## Compacted` sections) and the run log's compaction records (`compactions.json`). All checked for the
instance's canary values and the LLM key first: none.

## Why 20000 failed

- **One turn alone passed the trigger** (16000). The chat tool truncates the 14 KB output of `seq 1 3000`, so qwen
  re-reads it (`get_process_status`, `read_file`): eight tool calls in that one turn, each several thousand tokens.
- **After each compaction qwen fetched the output again**, because the summary does not carry it, and the window
  filled again: three compactions in one run, then the cap (decision 6) ended the run. The cap
  did its job: no endless loop.
- **qwen's second summary is the answer, not a summary**: "The last line `seq 1 3000` printed is: **3000**". The
  summary prompt does not hold on qwen for every request. To `BACKLOG.md`.

At 40000 one turn fits under the trigger, so the compaction comes between turns, as the scenario intends.
