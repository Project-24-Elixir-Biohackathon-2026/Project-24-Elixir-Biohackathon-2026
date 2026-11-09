# 2026-11-09: slice 4, all tasks and the final fix wave done; re-review, PR reply and merge next

Unit `impl/canary-eval-ladder-4-injections`, PR **#63** (still draft). Session ended at the context budget.
The slice's own handoff for slice 5 is [2026-11-09T0727Z-slice-4-done.md](2026-11-09T0727Z-slice-4-done.md),
already on the branch.

Run by `superpowers:subagent-driven-development`; ledger and packages in the worktree's git-ignored
`.superpowers/sdd/slice-4-injections/` (`progress.md`; `final-findings.md` is the round's six findings).

## Done

- Tasks 1–6 complete, each task-reviewed (task 5 and 6 after one fix round). L0 built live on de.NBI and
  checked (results in the slice-4-done handoff).
- Knowledge note `docs/knowledge/ladder-level-build-allowed-models.md` (`3518533`); handoff and *Current work*
  (`0a05e95`).
- Final review = the PR's local round (correctness on opus, methodology on sonnet): six findings, posted as one
  comment on #63 (issuecomment-6734720475). All six fixed in `06961b6..13f5c9d` (reset accepts the repo's
  `platform/instance/compose.*.yml` overlays; receiver decodes chunked bodies, logs bad lengths, marks
  `truncated`; plan task 5/task 1 text; no-op `sorted`; manifest select key; `spe_local_vars` sink vars; README
  `--tags handoff` line). Tests: `platform/dev/tests` 182, promptfoo-evals 349.

## Next

1. Scoped re-review of the fix wave (skill's `re-review-prompt.md`): findings `final-findings.md`, diff
   `.superpowers/sdd/slice-4-injections/review-0a05e95..13f5c9d.diff`, report `task-6-report.md` (*Final fix
   wave*). Residuals: adjudicate per `references/fix-loop.md`'s breaker; no second wave.
2. Reply on #63 in one comment, one line per finding, naming the fixing commit.
3. PR #63: title `… (4/9)`, body with what it delivers, the rulings (collect every `Ruling:` line in the ledger
   and `preflight.md` F1–F15, with cost if wrong), the checks that ran (`methodology sync --check`, both suites,
   `validate.py`, DCO), then mark ready by GraphQL `markPullRequestReadyForReview` (`docs/knowledge/gh-pr-create-token.md`).
4. Merge per `development-workflow.md` *Review and merge* (squash, checks in AGENTS.md *Overrides*); set slice 4's
   row in the plan README to `merged #63 (<sha>)`; clean up; delete the SDD workspace; move the pin in
   `biohackathon`; after-merge handoff and `methodology next --unit impl/canary-eval-ladder-5-agent-suite <handoff>`.
   Slice 5 needs a working de.NBI key (credentials gate) — see the slice-4-done handoff.
