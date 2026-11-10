# 2026-11-10: experiments slice 3

**Track:** experiments. **Spec:** `docs/specs/2026-11-10-experiments-design/` (README: decisions 1–23; slices in
`inputs-for-plan.md`). No plan stage: each slice is one PR, `impl/experiments-<n>-<slug>`, titled `… (n/7)`, its
task list in the PR body, worked with `superpowers:subagent-driven-development`.
**Previous:** slice 2, *the new template* (fork PR #86): `experiments/ladder-l0…l3.yml` checked by `validate.py`;
`spe_experiments`/`spe_experiment`/`spe_mitigations` in Ansible with `create.yml`'s mitigation checks and
`hardening.json`'s `mitigations`/`experiment`; the `spe-experiments` Coder template
(`platform/coder/experiments-template/`, `assemble.sh`, an OpenTofu test); the sync pushing it and
`experiment/<name>` branches as `spe-x-<name>`.

## Next

Slice 3, **`spe-eval`** (decisions 7–11, 13, 22, 23; 18's `--detach`/`status`/`wait`/exit codes), branch
`impl/experiments-3-spe-eval`, checked by the ladder as regression (decision 5) on de.NBI with a `--repeat 1` run
(standing OK: one instance at a time, `qwen3.8-27b`). Scope: `inputs-for-plan.md` row 3. Its *For the plan to
settle* items for this slice: the generated suite config, `spe-apply all` vs a tag set, the progress line source.

## Carried from slice 2 (rulings on #86)

- **Injections map in Terraform**: the template sets each listed fixture's `spe_inject_*` switch from
  `fixtures.json` (unlisted fixtures' switches are not set). `spe-eval` reads the same file for the arms; keep one
  mapping per side or share it.
- **`hardening.json`'s `injections` stays true/false/"mixed"**; with a fourth fixture ladder builds become
  "mixed": revisit when `run.sh`/`spe-eval` read the arms (this slice).
- **Preset descriptions are capped at 128 bytes** by the coder provider: the generated
  `— <threat> via <paths> · <mitigation>` line is kept whole, the experiment's text cut with "…".
- Deferred minors are in `BACKLOG.md` (spe-x name collision, long measures line, stale workspace version,
  `assemble.sh` on an empty dir).

## Watch for

- The de.NBI build of an experiment arm without the portal: render the template's `build_vars` for a preset with
  tofu, drop the keys the instance file sets (name, seed, host, model, data roots), and run `create.yml` **from the
  worktree** with `-e @<main>/platform/ansible/instances/denbi.yml -e @<rendered> -e
  spe_output_root=<main>/platform/ansible/output -e spe_repo_ref=<branch>`; from the main checkout it runs main's
  roles. `docs/knowledge/experiment-arm-build-without-portal.md`.
- `gh pr create`/`ready`/`merge` and `methodology worktree --prune` fail on this token (the upstream org refuses a
  long-lived fine-grained PAT): `docs/knowledge/gh-pr-create-token.md`; prefix
  `GH_REPO=thodkatz/elixir-biohackathon-2026-test` for `methodology` commands that call `gh`.
- OpenTofu is at `~/.local/bin/tofu` on this VM; the template test runs when it is on PATH or `SPE_TOFU` is set.
