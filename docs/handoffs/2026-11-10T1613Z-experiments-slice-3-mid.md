# 2026-11-10: experiments slice 3 mid (`spe-eval`, PR #88), after tasks 1–2

Mid-unit handoff (context budget). Same unit, same worktree:
`.claude/worktrees/impl-experiments-3-spe-eval`, branch `impl/experiments-3-spe-eval`, draft PR **#88**
(opened by REST: `gh pr create` fails here, `docs/knowledge/gh-pr-create-token.md`).

## Where the plan is

No plan stage: the slice's **task plan and rulings R1–R6 are in PR #88's body** (tasks 1–7). The full plan text
with *Global constraints* is also in the worktree's git-ignored SDD workspace
`.superpowers/sdd/experiments-3-plan/` (`plan.md`, `globals.md`, per-task briefs `task-N-brief.md` with the
globals prepended, reports, reviews, `reviewer-instructions.md`, and the ledger `progress.md`). Read the ledger
first; if that directory is gone, rebuild from the PR body and `git log`.

## Done

- **Task 1** (per-arm snapshots, progress line in `isolation.py`): `5122335`, `9e80ee6`; reviewed clean.
  Ruling: the progress `total` is the suite's test count (promptfoo 0.125.1 does not pass `--repeat` into
  `beforeAll`); `spe-eval status` (task 4) multiplies by the repeat it ran with. The dirty marker's field is now
  `key` (was `generated_at`).
- **Task 2** (gate learns the arm, `check_hardening` accepts `mixed`/`mitigations`/`experiment`, `run.sh
  --suite/--reports-dir/--description`): `df4b16c`, fix `cec1c26` (bool check on `injections`). **Its scoped
  re-review of `df4b16c..cec1c26` has not run**: do it first (finding: `injections` must refuse `1`, `0`,
  `"yes"`). Note: `run.sh`'s non-default path calls `npx promptfoo` directly; only tested with a fake `npx`, so
  task 7's de.NBI run is its real check.

## Next

Tasks 3–6 by subagent-driven development (briefs ready), then the whole-branch review, task 7 (de.NBI ladder
regression, standing OK for one instance), the local review round (correctness + methodology), PR ready, merge.
Pushed up to `cec1c26`.

## Watch for

- Dispatch prompts must name the worktree's absolute path and the branch check
  (`docs/knowledge/subagent-commits-in-main-checkout.md`); a reviewer once cited the main checkout's path, so
  check claims against the worktree.
