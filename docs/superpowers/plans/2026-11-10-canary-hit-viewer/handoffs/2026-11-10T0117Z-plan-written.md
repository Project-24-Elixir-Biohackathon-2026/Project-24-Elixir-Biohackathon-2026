# 2026-11-10: plan written (all 5 slices); review, merge and cleanup left

**Unit:** the plan, branch `plan/canary-hit-viewer`, draft PR #75 (label `plan`). Mid-unit handoff at the context
budget; the plan text is complete.

**Done this session (on the branch):**
- `d729a23`: `slice-3-participant-page.md` (Tasks 9–11), `slice-4-admin-page.md` (Tasks 12–13),
  `slice-5-upstream.md` (Task 14); README rulings 7–9 (stream bounds, server-rendered hit HTML, admin caps).
- **Ruling 2 rewritten** (self-review finding): upstream has `platform/report/` but no
  `platform/promptfoo-evals/handoff.py` or `metrics.py` (`git ls-tree upstream/main`, 2026-11-10), so the watcher
  may not import `handoff`. `load_canaries`, `read_hosts`, `_scalar` and the error move into a new
  `platform/report/canary_record.py` (`RecordError`; `handoff.py` imports it as `ConfigError`). Slice 1 Task 1
  and slice 2 Task 6 rewritten to match; slice 5 ports the package without the ladder's files and updates the
  ladder-port line in `BACKLOG.md`.
- Spec gap covered: "grouped by session and run on demand" is slice 3 Task 11's "Group by run" toggle.
- Also found: the report unit runs `python3 -I`, so sibling imports need a `sys.path` line (slice 3 preamble).
- Uncommitted when this was written, committed with it: `AGENTS.md` *Current work* (next: slice 1) and the
  `docs/README.md` index row for the plan.

**Next, in this unit:**
1. PR #75 body (what the plan holds, ruling 2's change, checks: `methodology sync --check`; no code, so no test
   suite) via `gh api -X PATCH` (`docs/knowledge/gh-pr-create-token.md`); mark it ready.
2. Local review round (correctness + methodology focuses, `development-workflow.md`, *Local review*) as one PR
   comment; address findings.
3. Merge by REST (squash, `--signoff`-equivalent: the squash commit message carries `Signed-off-by`), cleanup
   (`methodology worktree --prune` or `git worktree remove`), move the `biohackathon` pin.
4. The post-merge handoff on `main`, then `methodology next --unit impl/canary-hit-viewer-1-match-archive <handoff>`.
5. Reply to peer session `elixir-biohackathon-2026-test-b6` that Open WebUI is in (clarification 1, ruling 1), if
   reachable (`ListAgents`); still unanswered.

Note: `methodology worktree --prune` failed to read the forge this session (a fine-grained token over 366 days
refused by the upstream org's GraphQL); it still pruned by gone remote branches.
