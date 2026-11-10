# 2026-11-10: experiments slice 2, mid-unit (context budget)

**Unit:** `impl/experiments-2-template`, fork PR #86 (draft, title `Experiments: the new template (2/7)`). Its
body holds the slice's task list (Tasks 1–5) and the rulings so far; read it first, it is the plan. Scope and
carried rulings: `docs/handoffs/2026-11-10T1309Z-experiments-slice-2.md`.

**Worked with `superpowers:subagent-driven-development`.** Its workspace in this worktree (git-ignored):
`.superpowers/sdd/slice-2-plan/` — `plan.md` (the same task list, with the local tofu path), `progress.md` (the
ledger: pre-flight, rulings, task states), `task-<n>-brief.md`/`-report.md`, and `implementer-contract.md`,
`reviewer-contract.md`, `re-review-contract.md` (the skill's prompt templates, to point subagents at). If the
workspace is gone, the PR body and `git log` are enough.

## State

- Task 1 (ladder experiments as files, `validate.py` experiment checks): done, `91a53af` + fix `c5b5ca1`, review clean.
- Task 2 (Ansible: `spe_experiments`/`spe_experiment`/`spe_mitigations`, `create.yml` mitigation checks,
  `hardening.json` `mitigations`/`experiment`): implemented `e18e053` (base `c5b5ca1`), report
  `task-2-report.md`; **its task review is next** (review package `c5b5ca1..e18e053`).
- Tasks 3 (the `spe-experiments` template, `assemble.sh`, the Terraform test), 4 (the sync), 5 (docs): not started.
- Then: the whole-branch final review, the de.NBI build of `ladder-l2`, the local review round, merge.

## Notes for the next session

- **Terraform tests need OpenTofu**, absent here: `docs/knowledge/opentofu-coder-template-test.md` (download,
  the env-var trick for parameters, what is unknown at plan). The previous session's binary was in its scratchpad;
  download again into yours and set `SPE_TOFU`.
- **The de.NBI build** (standing OK, one instance): the existing VM `denbi-agui-01` (`instances/denbi.yml` in the
  main checkout, `spe_provision: existing`) can be rebuilt in place. No portal route (the portal follows upstream),
  so render the template's `build_vars` output for the `ladder-l2` preset with tofu into a vars file and run
  `create.yml -e @instances/denbi.yml -e @<that file> -e spe_repo_ref=impl/experiments-2-template` from the main
  checkout (`</dev/null`); the build makes no model call (`spe_agui_smoke: false`). Check `hardening.json` level 1,
  `mitigations: [L1]`, `experiment: ladder-l2`.
- Running a task's review in parallel with the next task's implementer worked (disjoint files; tell each to stage
  by name).
