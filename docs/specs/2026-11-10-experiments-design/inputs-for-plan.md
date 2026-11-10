# Inputs for the plan

## Slices, in order

| # | Slice | Decisions | Needs an instance |
|---|---|---|---|
| 1 | **The catalogue as files**: `paths/` (P1–P4, template), `mitigations/` (L1–L3, L4–L5 planned), `validate.py` over all three, `matrix.CATALOGUE` read from files, `tests/experiments/`, `injections` in the experiment block, `drs_register` and `trs_install` planting every catalogue entry whose switch is on, `injections_schema.py` reading ids, surfaces and actions from the catalogue and `metrics.py`'s detectors | 2, 3, 4, 23 | no |
| 2 | **The new template**: `spe-experiments` with `experiment` and `mitigations`, the sync assembling and pushing it (and `experiment/<name>` branches), the merge into `ansible_vars`, `spe_experiments` gating, `requires`/`conflicts` in `create.yml`, `hardening.json` `mitigations`, the ladder experiments | 1, 5, 6 | one de.NBI build (the `ladder-l2` preset: level 1) |
| 3 | **`spe-eval`**, checked by the ladder as regression (decision 5): VM-local hand-off, local `isolation`, per-arm snapshots, the two arms (and the one-arm case), `run.sh`'s suite, reports and description arguments, the gate learning the arm, injection switches and `injections.json` per arm, lock and its token, archive, the guide's first *Experiments* steps | 7–11, 13, 22, 23 | de.NBI, a `--repeat 1` run |
| 4 | **The viewer and apps**: `evals-view`, the read-only proxy, the Evaluations app; the early output | 14–16 | de.NBI |
| 5 | **Eval runs apart in canary hits**: provider mark, run-log `source`, the watcher and pages | 12 | de.NBI |
| 6 | **Contribution**: `check_experiment.py` (`--json`, the injection checks), `spe-eval new`, `results`, `pr-body`, PR template, `CONTRIBUTING.md`, the workspace guide's *Experiments* section, `experiments/README.md` | 17–19 | no |
| 7 | **Proven with an agent**: a coding agent in a de.NBI workspace builds a TRS-guard experiment against its own new injection from one sentence (decision 20); what it stumbled on is fixed or written into the guide | 20 | de.NBI |

Slices 3 and 4 together give the early output (README). `spe-eval`'s `--detach`, `status`, `wait` and exit codes
(decision 18) are built in slice 3 with the run itself.

## Dependencies

- **The ladder upstream.** `run.sh`, `isolation.py`, `matrix.py`, `handoff.py`, `metrics.py`,
  `controls_asserts.py`, the probes and the `spe_harden_*` switches are on the fork only, not yet upstream; the
  canary hit viewer likewise (`platform/report/canary_record.py`, where `vm_argv` lives, and the template's Canary
  hits app). The portal follows upstream, so nothing here
  reaches participants until those are ported. Slices can be built and checked on the fork and a de.NBI instance
  first; their upstream port follows the ladder's.
- **Branch templates from upstream only.** Step 5 of the contribution path needs push access to upstream; making
  branch templates from forks or PR refs is out of scope (`out-of-scope.md`).

## For the plan to settle

- The writes `promptfoo view` 0.125.1's reading UI needs (04, *Read-only*), from its routes, with a test.
- How the generated experiment suite config is built (a file `spe-eval` writes, or `agent.yaml` filtered by
  promptfoo's `--filter-pattern`/metadata filter) and that the utility group runs in it.
- Whether `spe-apply all` is the narrowest apply that switches every ladder mitigation (L3's compose overlay is
  written by the frontend roles) or a tag set suffices.
- The progress line source (the `afterEach` hook appending to a file `spe-eval` tails).
- Slice 2, from slice 1's rulings (#85): whether an experiment's `injections` ids map to `spe_inject_*` values in
  the template (Terraform) or stay in Python (`injections_schema.switches`); and `hardening.json`'s `injections`,
  today true/false/"mixed" over every fixture, so a fourth fixture makes ladder builds "mixed": revisit it when
  `mitigations` is added there.
