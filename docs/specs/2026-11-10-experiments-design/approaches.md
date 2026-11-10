# Approaches

## Where an experiment is measured

| | How | Trade-off | |
|---|---|---|---|
| **A. One workspace, arms switched on the VM** | `spe-eval` applies the baseline arm, runs, applies the mitigated arm, runs; both on the workspace's VM from its clone | one VM, one build, the same canaries: the two arms differ only in the mitigation. A run takes twice one arm. The hand-off sits on the VM (03 says why that is acceptable here) | **chosen** (the agent's call in the design conversation of 2026-11-10; the user went on from it without objecting) |
| B. Two workspaces | a baseline experiment and a mitigated one, compared across | two VMs, and two builds whose canaries differ unless the seed is fixed, and the seed is secret; breaks one-instance-at-a-time quotas | rejected |
| C. Run from the portal VM | a portal service runs `run.sh` against the workspace's controller hand-off; a Coder link triggers it | the answer key never reaches the VM, as for the official ladder; but the portal's checkout is upstream `main`, so a participant's uncommitted mitigation and tests are not in the run | rejected for experiments; it is the official ladder's route, which stays |

## How results are shown

| | Trade-off | |
|---|---|---|
| **`promptfoo view` on the VM behind a Coder app** | promptfoo's own UI: results table, outputs, tool calls, side-by-side evals; a normal `coder_app`, owner-only; its run endpoints must be blocked | **chosen** |
| A results page of our own in the report service | full control, the ladder matrix possible; a second UI to build and keep | not now; the matrix stays a command (04) |
| `promptfoo view`'s own Run button as the trigger | no `spe-eval` to build; but it runs a bare suite: no checks, no controls gate, no lock, no arms | rejected (04, *Read-only*) |

## Where it lives

| | Trade-off | |
|---|---|---|
| **A new template, `spe-experiments`** | `spe` and its users are untouched; the experiment flow can change freely while it settles; two templates to keep while both live, sharing playbooks and `run-ansible.sh` | **chosen** (the user, 2026-11-10: "propose a new coder template instead of editing the existing one, then the old one could be deleted or kept") |
| Extend `spe` | one template; every workspace gets the flow at once, and every change to it reaches every participant | rejected |

## How options grow

| | Trade-off | |
|---|---|---|
| **Options read from files** (`fileset()` over `experiments/` and `mitigations/`, which the sync copies into the pushed template directory, as `spe`'s presets come from `testbeds/`) | a contribution adds files, never Terraform | **chosen** |
| One `coder_parameter` per mitigation | explicit, but every contribution edits `main.tf` | rejected |
| A `level` parameter L0–L3 | simple for the ladder; no place for a participant's mitigation, and a level bundles controls a participant cannot pick apart | rejected: levels become experiments |

## Existing tools searched

Needs, in the user's terms: a participant proposes a mitigation, measures it against the agent on a real SPE build,
sees the results, and contributes it so others can rebuild and remeasure it.

- **promptfoo** (in use): its viewer is taken whole; its eval creator is not used as a trigger (above).
- **Coder presets and parameters** (in use): taken; the form is how a build is chosen.
- **AgentDojo** (prompt-injection benchmark with pluggable attacks and defenses) and **Inspect** (UK AISI's eval
  framework, with its own log viewer): both would replace promptfoo and model the environment as tools in Python;
  here the target is a deployed stack with real APIs, canaries and controls at the infrastructure layer, and the
  suites, scoring and isolation already exist on promptfoo. Taking either whole would leave the stack, the
  switches, the reset and the canaries to write again around it. Not used. Not trialled; recorded from what each
  is known to do, as of this spec.
- **The viewer's read-only guard**: promptfoo 0.125.1 has no read-only mode for `promptfoo view` (its sharing and
  telemetry switches do not cover the eval creator or replay), so a guard is needed; it is an existing reverse
  proxy configured with a method and path allow-list (04), not a proxy of our own.
- **`spe-eval`'s lock and background run**: `flock` for the lock and a user systemd unit (`systemd-run --user`) for
  `--detach`, both on the VM already; what `spe-eval` itself adds is the order of arms and applies, which no tool
  knows. No job runner (a queue, a CI runner on the VM) is used: one run at a time per VM needs none.

The search was made in one session (Claude Code), from known tools, not a web search across harnesses; a reviewer
who knows a closer fit for any piece should say so on the spec's PR.
