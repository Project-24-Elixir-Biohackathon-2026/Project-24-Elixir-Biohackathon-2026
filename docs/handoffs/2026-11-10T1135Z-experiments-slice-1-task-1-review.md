# 2026-11-10: experiments slice 1 task 1 review


**Track:** experiments, slice 1/7 (the catalogue as files), branch `impl/experiments-1-catalogue`, draft PR #85
(opened by REST: `gh pr create` fails on the org token, `docs/knowledge/gh-pr-create-token.md`).
**Previous:** `docs/handoffs/2026-11-10T1117Z-experiments-slice-1.md` (the slice's scope and acceptance).
Handed off at the context budget, mid-unit.

## Where it stands

- **The task list (the slice's plan)** is in PR #85's body, and as a file with the SDD ledger in this worktree's
  git-ignored `.superpowers/sdd/slice-1-plan/` (`plan.md`, `progress.md`, `constraints.md`, `task-N-brief.md`).
  Four tasks: 1 paths and mitigations as files plus `validate.py`; 2 `matrix.CATALOGUE` from files and
  `tests/experiments/`; 3 injection catalogue read (`surfaces.json`, `metrics.DETECTORS`,
  `injections_schema.check_fixtures` and `switches`); 4 Ansible plants every fixture whose switch is on.
- **Task 1 implemented**, commits `f15e79e`, `b2bec29` (pushed). Tests reported green (validate OK; platform/dev
  234 passed; promptfoo-evals 393 passed; `matrix.py render` equals the committed Markdown). Its concerns, in
  `.superpowers/sdd/slice-1-plan/task-1-report.md`: L1–L3 `requires`/`conflicts` empty (no tying assert found),
  L4/L5 `closes: []`.
- **Rulings** (ledger, and to go in the PR body): `injections` in the experiment block is
  `injections_schema.switches(ids)` in slice 1 (experiment files come in slice 2); `hardening.json`'s `injections`
  stays true/false/"mixed" over all fixtures.

## Next

Resume `superpowers:subagent-driven-development` on `.superpowers/sdd/slice-1-plan/plan.md` (the ledger says
where): Task 1's task review (base `267aecd`, head `b2bec29`; judge its two concerns), then Tasks 2–4, the final
whole-branch review, PR #85 ready with its body (task list, rulings, checks run), the local review round
(*Reviewers*), merge, cleanup, pin in `biohackathon`, chain to slice 2.
If `.superpowers/` is gone, rebuild the task list from PR #85's body.
