# 2026-11-11: experiments slice 6 mid

Mid-unit handoff at the context budget. **Unit:** `impl/experiments-6-contribution`, draft PR **#94**
("Experiments: contribution (6/7)"); scope and carried notes in `docs/handoffs/2026-11-11T1643Z-experiments-slice-6.md`
(read it for the gh workarounds only: open/ready/merge over REST/GraphQL, `docs/knowledge/gh-pr-create-token.md`).
No plan stage: the task list and the rulings are in #94's body.

## State

Worked with `superpowers:subagent-driven-development`. Its git-ignored workspace, in this worktree:
`.superpowers/sdd/slice6-plan/` — `plan.md` (the task list with *Global Constraints*), `global-constraints.md`,
`reviewer-instructions.md` (the task-reviewer template, filled per dispatch), `progress.md` (the ledger),
`task-N-brief.md`, `task-N-report.md`, `task-N-review.md`.

- **Task 1** `check_experiment.py`: complete, `ca438cd`, review clean (4 minors parked in the ledger).
- **Task 2** templates, `spe-eval new`, `spe-eval test`: committed `c60f62f`, `14d10ff`; its review
  (`task-2-review.md`) is **spec ❌, 3 Important**, fix round 1 not started:
  1. `spe-eval new --path` prefills `tests` but not `injections` (07, *Commands*, "Start"); fix, or record a
     ruling in #94's body if the catalogue has no injection→path link.
  2. `platform/promptfoo-evals/matrix.py:64`'s `mitigations/*.yml` glob admits `TEMPLATE` as a `closed_by` label:
     skip `TEMPLATE.*` like every other reader.
  3. `test_new_refuses_the_reserved_template_name` never reaches the lowercase `template` branch.
- **Tasks 3** (`results`, `pr-body`, `.github/pull_request_template.md`) **and 4** (guides, index, docs tests,
  root `AGENTS.md` rows): not started.
- All pushed; full suites green at `14d10ff` per the Task 2 report.

## Resume

1. `git log --oneline -5` (head `14d10ff` plus this handoff); read `.superpowers/sdd/slice6-plan/progress.md`
   and `task-2-review.md`.
2. Fix round for Task 2: a fresh implementer (the old agent is gone) given `task-2-brief.md`, the review file and
   the three findings; then a scoped re-review of that fix diff.
3. The SDD scripts key the workspace by the plan's path: run `task-brief`/`review-package` with
   `.superpowers/sdd/slice6-plan/plan.md` copied to a scratch file named `slice6-plan.md`, or write briefs by
   hand (`sed -n '/^### Task 3/,/^### Task 4/p' plan.md`).
4. Tasks 3 and 4, then the whole-branch final review (most capable model), the local review round on #94
   (correctness + methodology), merge, cleanup, pin move in `biohackathon`, merge handoff, `methodology next --unit
   impl/experiments-7-proven-with-an-agent` (check the slice-7 branch name in `inputs-for-plan.md` row 7).
