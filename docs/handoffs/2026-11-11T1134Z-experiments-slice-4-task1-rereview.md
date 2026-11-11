# 2026-11-11: experiments slice 4 task1 rereview

**Unit:** slice 4/7, the viewer and apps, branch `impl/experiments-4-viewer`, draft **PR #92** (opened by REST:
`gh pr create` fails on the organization token rule, `docs/knowledge/gh-pr-create-token.md`). Context for the
unit: `docs/handoffs/2026-11-11T1012Z-experiments-slice-4.md`. Mid-unit handoff at the context budget.

**How the work runs:** `superpowers:subagent-driven-development`. Its workspace (git-ignored, in this worktree)
is `.superpowers/sdd/slice4-plan/`: **`plan.md`** (the task list: Global Constraints, Tasks 1–3; also PR #92's
body), **`progress.md`** (the ledger: rulings, findings, deferred minors), the briefs, reports and reviews. Run the
skill's scripts with `plan.md` there as PLAN_FILE. Read the ledger first.

**Settled (the spec's *For the plan to settle* item):** promptfoo 0.125.1's reading UI needs no write to the API;
the proxy passes GET/HEAD and socket.io's `POST /socket.io/` only, 403 for the rest. `evals-view` is nginx owning
the network namespace, `evals-promptfoo` inside it. Both rulings are in PR #92's body; Task 3 folds them into
spec 04 and clarification 3.

## Where it stands

- **Task 1** (compose services, `platform/instance/evals-view/{Dockerfile,nginx.conf}`,
  `platform/dev/tests/test_evals_view.py`): commits `4b89cbc`, `7dfd4ab`; review found C1 (unset `SPE_EVALS_*`
  broke compose on every `spe` instance) and I2 (encoded `..%2F` path reached promptfoo writes through the
  `/socket.io/` location); fix round 1 is `4035cce` (also minors 1, 3, 6). **Next: the scoped re-review** of
  `7dfd4ab..4035cce` (`scripts/review-package`, `re-review-prompt.md`) against C1 and I2, then the ledger's
  completion line.
- **Tasks 2 and 3**: not started (wiring into a `spe_experiments` build and `spe-apply`; the Evaluations app and
  docs). Then the final whole-branch review (triage the ledger's deferred minors 2, 4, 5), the de.NBI check
  (decisions 14–16's acceptance, the early output), the local review round, merge.
- Everything is pushed; the worktree is clean apart from the git-ignored `.superpowers/`.
