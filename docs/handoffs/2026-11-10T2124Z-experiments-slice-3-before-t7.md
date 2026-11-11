# 2026-11-10: experiments slice 3 (`spe-eval`, PR #88), tasks 1–6 done, before task 7

Mid-unit handoff (context budget). Same unit, same worktree:
`.claude/worktrees/impl-experiments-3-spe-eval`, branch `impl/experiments-3-spe-eval`, draft PR **#88**. Pushed up
to `80948ca`. Previous handoff: `docs/handoffs/2026-11-10T1613Z-experiments-slice-3-mid.md`.

The SDD workspace (git-ignored) is `.superpowers/sdd/experiments-3-plan/`: read its ledger `progress.md` first
(rulings, deferred minors); `final-review.md` holds the whole-branch review and its fix round.

## Done

- Tasks 1–4 (earlier sessions). Task 5 (VM side: `spe_eval` role with Node 22.22.0 + uv + lingering,
  VM-local hand-off `vm_handoff.yml` under tag `handoff`, per-arm `vm_hardening.yml` under tag `frontend`,
  `/usr/local/bin/spe-eval`, archive into `evals/`, decision-8 test): `24d2dcf`, `d55c22b`, fix `2bf84bc`.
  Task 6 (workspace guide *Experiments*, READMEs, BACKLOG decision 21): `e57f53f`.
- Whole-branch review (Opus): 4 Important + race + minors, all fixed in `1d269f5..80948ca`; suites green
  (promptfoo-evals 457, dev/tests 441, validate OK).

## Rulings to carry into the PR body

- `injections.json` on the VM is written once at build, not per arm (R4 said both): every arm uses the
  experiment's own switches; `check_creation_time` now also compares injection switches, so a mismatched
  build refuses (exit 2).
- `run.sh` accepts `injections: "mixed"` only on its non-default (experiment) path; the ladder route refuses it.
- The gate passes an *undeclared* closed probe with a note (out-of-scope.md), only for an arm with mitigations.

## Next

1. Scoped re-review of `e57f53f..80948ca` against `final-review.md` (one reviewer subagent, or controller).
2. Task 7 (plan.md, *Task 7*): one de.NBI instance (standing OK), built as a `ladder-l<N>` arm without the
   portal (`docs/knowledge/experiment-arm-build-without-portal.md`); `spe-eval run ladder-l<N> --repeat 1` for
   N = 1…3; evidence in the PR body; destroy the instance. Also check `spe-eval run --detach` from a Coder-like
   shell without `XDG_RUNTIME_DIR`/`DBUS_SESSION_BUS_ADDRESS` (fix `a0982db`); SSH alone hides that case.
   First real check of the Node/uv downloads, `npm ci`, `uv sync` and `run.sh`'s `npx promptfoo` path.
3. Local review round (correctness + methodology), PR body (tasks, rulings R1–R6 and the three above, checks
   run), ready, merge; update AGENTS.md *Current work* (still points at the slice-3 handoff), move the pin in
   `biohackathon`, chain to slice 4/7 ("The viewer and apps").

## Watch for

- Dispatch prompts must name the worktree's absolute path and the branch check
  (`docs/knowledge/subagent-commits-in-main-checkout.md`).
- `platform/dev/tests` takes ~6 min; a concurrent `git commit` in the same tree can fail `test_hardening_json`
  (it reads `git rev-parse HEAD`): run the suite with nothing else committing.
