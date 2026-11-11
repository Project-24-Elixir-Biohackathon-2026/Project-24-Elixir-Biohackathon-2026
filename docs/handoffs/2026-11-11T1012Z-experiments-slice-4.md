# 2026-11-11: experiments slice 4

**Track:** experiments. **Spec:** `docs/specs/2026-11-10-experiments-design/` (README: decisions 1–23; slices in
`inputs-for-plan.md`). No plan stage: each slice is one PR, `impl/experiments-<n>-<slug>`, titled `… (n/7)`, its
task list in the PR body, worked with `superpowers:subagent-driven-development`.
**Previous:** slice 3, **`spe-eval`** (fork PR #88): `platform/instance/spe-eval` and `spe_eval.py` (`arm`, `run
[--detach]`, `status`, `wait`, `runs`; arms, creation-time check, suite, lock), the VM-local hand-off in
`~/spe-eval/handoff/`, per-arm snapshots and the progress line in `isolation.py`, the gate learning the arm,
`run.sh`'s `--suite`/`--reports-dir`/`--description`, the `spe_eval` role (Node 24.21.0, uv, lingering), the
archive's `evals/`. Checked by the ladder on de.NBI (L1–L3, `--repeat 1`, every arm ok; tables in #88's body).

## Next

Slice 4, **the viewer and apps** (decisions 14–16): `evals-view`, the read-only proxy, the Evaluations app, and
the early output (slices 3 and 4 together give it: spec README). Branch `impl/experiments-4-viewer`. Scope:
`inputs-for-plan.md` row 4, spec section `04-viewer.md`. Its *For the plan to settle* item: the writes `promptfoo
view` 0.125.1's reading UI needs (04, *Read-only*), from its routes, with a test. Needs de.NBI (standing OK: one
instance at a time, `qwen3.8-27b`).

## Carried from slice 3

- **Where results are**: `~/spe-eval/reports/<experiment>/<run id>/<arm>/` (`run.json`, `controls.json`,
  `agent.json`, `hardening.json`, `gate-notes.json`) and the promptfoo database in `~/spe-eval/promptfoo/`
  (`PROMPTFOO_CONFIG_DIR`); each eval's description is `<experiment> <run id> <arm> [<ids>] <model> controls|agent`.
  `spe-eval run` already prints "(spe-eval results, or the Evaluations app)": the app is this slice's.
- **Building an arm without the portal**: `docs/knowledge/experiment-arm-build-without-portal.md`; one build
  serves every `ladder-l<N>` (#88's ruling), applied per arm by `spe-eval`. Start a long run with
  `env -u XDG_RUNTIME_DIR -u DBUS_SESSION_BUS_ADDRESS spe-eval run <name> --repeat 1 --detach` and poll
  `spe-eval status` every few minutes from a background loop (a long `ssh … spe-eval wait` once never returned).
- **On agent-service-1** prune the build cache before a build (`docs/knowledge/denbi-disk-full.md`); the instance
  is shared: restore it afterwards from the main checkout's `instances/denbi.yml` (`destroy.yml`, `create.yml`,
  `docs/knowledge/denbi-anthropic-haiku.md`).
- **Compose alias loss** after a network change is handled in `spe-apply up`
  (`docs/knowledge/compose-network-alias-lost.md`); an instance left broken by an older clone is repaired by
  `git pull` then `spe-apply all`.
