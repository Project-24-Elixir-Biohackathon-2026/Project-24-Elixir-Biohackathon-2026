# 2026-11-10: experiments slice 3 (`spe-eval`, PR #88), task 7 under way: L1 run blocked on the VM's local.yml

Mid-unit handoff (context budget). Same unit, same worktree:
`.claude/worktrees/impl-experiments-3-spe-eval`, branch `impl/experiments-3-spe-eval`, draft PR **#88**.
Previous handoff: `docs/handoffs/2026-11-10T2124Z-experiments-slice-3-before-t7.md` (its *Rulings to carry into
the PR body* still apply). SDD ledger: `.superpowers/sdd/experiments-3-plan/progress.md`.

## Done this session

- **Scoped re-review of `e57f53f..80948ca`** (Opus subagent, `.superpowers/sdd/experiments-3-plan/rereview-e57f53f..80948ca.md`):
  every whole-branch finding fixed; new findings all fixed: N1 Important (gate note covered closed
  `api-reach`/`isolation-plant`) `ddf81fc`; N2 dirty-stack workspace remedy + README pruning text
  `4aa2e21`; N3 `Lock.acquire` retries past `holder()`'s probe `f3e8c92`; archive tar-exit-1 test made
  deterministic `7b07b46`; SIGKILL'd `windows.jsonl` gap to BACKLOG `0e44913`. Suites run: promptfoo-evals 459,
  dev `-k "spe_eval or spe_apply"` 133 (the full dev suite not re-run since `80948ca`: run it before the PR).
- **Task 7 bug 1, fixed** `47629d0`: `npm ci` on the VM failed (npm 10 of Node 22 refuses the npm 11 lock,
  "Missing: gcp-metadata@7.0.1"): `spe_eval_node_version` 24.21.0; note `docs/knowledge/npm-ci-lock-npm-version.md`.
- **L1 build** of denbi-agui-01 (`ladder-l1`, qwen3.8-27b) passed (`create.yml` ok=203) at `47629d0`. Toolchain
  (Node 24.21.0, uv), `npm ci`, `uv sync` all worked on the VM.
- **`--detach` from a bus-less shell works**: `env -u XDG_RUNTIME_DIR -u DBUS_SESSION_BUS_ADDRESS spe-eval run
  ladder-l1 --repeat 1 --detach` printed the run id, exit 0, systemd user unit ran (fix `a0982db` confirmed).

## Blocker found (task 7 bug 2, not fixed)

Run `20261110T213910Z`: both arms `failed` within 30 s. The VM-local `spe-apply all` (runs `create.yml` on the
VM from `~/sperange/platform/ansible/instances/local.yml`) refused at the preflight: `data_root /data-share …
not owned by denbi-agui-01` and `only 4 GB free …, need 15`. `local.yml` (written by `roles/repo`, from
`spe_local_vars + spe_local_vars_extra`) lacks `denbi.yml`'s `spe_data_root: /srv/spe-data`,
`spe_min_free_gb: 5` (and `spe_manage_docker: false`): those are not in `spe_local_vars`, and the experiment's
rendered `spe_local_vars_extra` replaces any list an instance file gives. On the portal the defaults are right,
so it is a controller-built-instance gap, but decide: (a) add `spe_data_root`, `spe_min_free_gb`,
`spe_manage_docker` to `spe_local_vars` in `group_vars/all.yml` (likely right: a local re-apply must see the
build's data root), or (b) pass them via `spe_local_vars_extra` in the arm vars for task 7 only. Check
`journalctl --user -u 'spe-eval-*'` on the VM for the full log. Also noticed: spe-eval reported "returning to the
build's own arm failed (spe-apply all exit 2)".

## How the L1 build was made (redo for L1..L3)

Scratchpad files are gone with this session; recreate: render with `platform/dev/tests/test_experiments_template.py`'s
helpers (`copy_template`, `tofu init`, `plan(d, preset_parameters("ladder-l<N>"))`, `build_vars`), drop
`spe_instance`/`spe_seed`, add `spe_agent_model_provider: openai_compatible`, `spe_agent_model: qwen3.8-27b`,
`spe_agent_allowed_models: []`; then from the worktree's `platform/ansible`:
`DENBI_LLM_API_KEY=$(coder ssh thodkatz/test 'docker exec spe-frontend-open-webui-1 printenv OPENAI_API_KEY' | tr -d '\r\n')`
and `ansible-playbook playbooks/create.yml -e @<main>/platform/ansible/instances/denbi.yml -e @<arm>.yml -e
'{"spe_agent_allowed_models": []}' -e spe_output_root=<main>/platform/ansible/output -e
spe_repo_ref=impl/experiments-3-spe-eval </dev/null` (the key `52bb9f98` comes from the user's existing workspace
`thodkatz/test`, Started; no new workspace made). Scripts need `bash x.sh`: no `/bin/bash` on this guest.
Committed comparison: `docs/results/canary-ladder-qwen3.8-27b.md`.

## Next

1. Fix bug 2 (with a test of `local.yml`'s keys), push, rebuild L1, `spe-eval run ladder-l1 --repeat 1`, then
   L2, L3 (rebuild each); compare controls and agent counts to the committed matrix; evidence in the PR body.
   Destroy the instance afterwards (`docs/knowledge/denbi-*`; it is the shared denbi-agui-01: restore it as the
   previous handoffs say, or ask if unsure).
2. Then the previous handoff's step 3 (full dev suite, local review round, PR body, merge, pin, chain to 4/7).

`methodology worktree --prune` could not read the forge (fine-grained token lifetime > 366 days refused by the
upstream org); only the start routine's prune was affected.
