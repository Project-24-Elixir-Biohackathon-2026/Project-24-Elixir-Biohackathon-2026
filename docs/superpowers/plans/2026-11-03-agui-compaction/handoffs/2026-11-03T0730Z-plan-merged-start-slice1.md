# 2026-11-03: AG-UI compaction plan merged; start slice 1/3

Plan PR #16 merged (squash), after one local review round: 17 findings, all addressed
(https://github.com/thodkatz/elixir-biohackathon-2026-test/pull/16#issuecomment-6598428160).

## Next: slice 1/3, `impl/agui-compaction-1-agent`

Read the plan's `README.md` (Global Constraints, Shared interfaces, *PR slices*), then only
[`slice-1-agent.md`](../slice-1-agent.md). Claim first: `.methodology/shared/claude/worktree.sh
impl/agui-compaction-1-agent`, push, draft PR `Agent compacts the conversation (1/3)` against the fork.

- **Seven tasks, two mid-slice handoff points** (README, *PR slices*): after task 4 and after task 6, each after
  a commit with the whole agent suite green. Hand off at the latest one reached when the budget fires.
- **Test sizes**: the fixture's 16 tool definitions estimate ≈ 3,000 tokens, so the compaction tests use
  `BIG` = 15,000 characters and `window(6000)`. If a test compacts on the first request, print both estimates
  and move the window between them (slice 1, verified facts).
- **Clarifications 1–4 are folded in slice 1** (tasks 1, 4, 6, 6), in number order; 5 is slice 3's.
- **Paid**: task 7's Haiku summary sample is approved (README, *Global Constraints*); nothing else in slice 1
  calls a model.
- Task 7, step 4 adds the `BACKLOG.md` item for the upstream port.

## Waiting on the user

Clarification 5 (decision 13's check against Haiku's own window) rewrites an approved acceptance check; PR #16's
body asks the user to look. Slice 3 reads the answer before its paid run; slices 1 and 2 do not wait for it.
