# Experiments

An experiment is one Coder preset of the `spe-experiments` template: a threat and the path it takes,
measured with no mitigation (the baseline arm) against one mitigation under test, built from the
threats, paths and mitigations catalogued in `../threats/`, `../paths/` and `../mitigations/`. Each
file here is `<name>.yml`, checked by `../validate.py`, and offered by name in the template's
`experiment` parameter (`../platform/coder/experiments-template/`).

Index, one line per file:

| File | Threat | Paths | Mitigation under test |
|---|---|---|---|
| `ladder-l0.yml` | TM-001 | P1, P2, P3, P4 | none (baseline only) |
| `ladder-l1.yml` | TM-001 | P2 | L1: TRS read-only |
| `ladder-l2.yml` | TM-001 | P3 | L2: Data tiers (on top of L1) |
| `ladder-l3.yml` | TM-001 | P4 | L3: Egress (on top of L1, L2) |

The ladder (`ladder-l0`..`ladder-l3`) is the first set of experiments, the hardening ladder's levels
read as a path through the threat model; `ladder-l0` is the template's default preset. A new
experiment file needs a line added here.

## Running one

Build a `spe-experiments` workspace with the preset named above (`../platform/coder/README.md`), then run
`spe-eval` in it: `../platform/instance/workspace/AGENTS.md`, *Experiments*, has the commands (`arm`, `run`,
`status`, `wait`, `runs`) and where results land.
