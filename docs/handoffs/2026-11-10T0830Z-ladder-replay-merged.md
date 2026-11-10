# 2026-11-10: ladder replay merged

Unit `change/ladder-replay` is done: fork PR **#83** squash-merged as `2877865`. Its own handoff,
`docs/handoffs/2026-11-10T0824Z-ladder-replay-built.md`, has the background and the real-data checks.

**What the merge settled:**
- One local review round (correctness, methodology): 9 findings, all addressed on the PR (issuecomment-6762719514,
  reply -6762719869). `check` now compares errors with the committed counts; a non-JSON log line is refused by
  line number; the README runs the replay under `umask 077`. 393 tests pass.
- The user's ruling that canary values may be shown to the team (the seed stays secret) is recorded as
  `biohackathon` knowledge record 0019, committed with the pin move to `2877865`'s successor.

**To view the replayed ladder:** `platform/promptfoo-evals/README.md`, *Replaying the run log*; the rebuilt evals
are in the main checkout's `platform/ansible/output/denbi-agui-01/ladder-runs/` (git-ignored).

**Next:** nothing chained. The team viewer (a shared promptfoo viewer on the portal, ladder levels as Coder
presets, a `run.sh` trigger) is in `BACKLOG.md` *Next*, waiting on the user to write and approve its spec.
