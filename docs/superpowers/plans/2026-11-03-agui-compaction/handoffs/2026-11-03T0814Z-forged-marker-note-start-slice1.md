# 2026-11-03: forged-marker note added to task 6; start slice 1/3

Nothing else changed since [the plan-merged handoff](2026-11-03T0730Z-plan-merged-start-slice1.md): start slice 1
exactly as it says (claim, read the README and `slice-1-agent.md`, seven tasks, its paid run and its waiting item).

## Added: the client can forge a compaction marker

From a discussion with the user (2026-11-03) on how the AG-UI stack stores conversations. The browser sends the
whole history with every run, so a participant can send an assistant message with `messageId`
`spe-compaction-<anything>`, and the agent will cut there and continue from a summary the participant wrote.
The full analysis, with the other history-injection cases and a proposed server-side journal, is
[`docs/proposals/2026-11-03-agui-history-integrity.md`](../../../../proposals/2026-11-03-agui-history-integrity.md)
(case 5), with its line in `BACKLOG.md`.

It now lives in **slice 1, task 6**, *Interfaces*: accepted by design in this slice, not tested as if it were
prevented. Recording marker provenance in the run log (`compactions[].marker_id`, per-run `cut_at`) changes
decision 11, so it goes in only if the user folds it into the spec as a clarification first.
