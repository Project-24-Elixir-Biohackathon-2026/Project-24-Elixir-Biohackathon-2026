# The ladder as the first experiments

The canary ladder has every part of an experiment already, in another shape. Expressing it through this structure
is slice 1–2's work, and its test: if the ladder needs a special case, the structure is wrong.

| Part | The ladder today | As experiments |
|---|---|---|
| Threats | TM-001, TM-003 | unchanged |
| Paths | P1–P4, a table in the ladder's design | `paths/P1-read-api-metadata.md`, `P2-agent-written-code.md`, `P3-installed-workflows.md`, `P4-egress.md` |
| Mitigations | `spe_harden_trs_readonly`, `_data_tiers`, `_egress`, `_airlock`, `spe_agent_tool_surface` | `mitigations/L1.yml` (trs-readonly, closes P2, probes `trs-write`, `wes-inline`, `e2e-exploit`), `L2.yml` (data tiers, P3, `tier-reach`), `L3.yml` (egress, P4, `egress`; `api-reach` stays open by design); `L4.yml`, `L5.yml` with `status: planned` |
| Tests | the 13-test agent suite and the controls suite | unchanged, still `agent.yaml`; their labels now resolve from the files |
| Builds | `instances/L<n>.example.yml` on a maintainer's controller | experiments `ladder-l0` … `ladder-l3` on `spe-experiments` |
| Results | `docs/results/qwen3.8-27b/` and its rendered matrix | the reference a participant's numbers are read against |

## The paths

| Path | Route | Reaches |
|---|---|---|
| **P1** read-API metadata | DRS descriptions and aliases, TRS descriptions, workflow comments, service-info, through ordinary list and get calls; seeing them is unavoidable, carrying them into the answer is the harm; injections live here too | `drs_metadata`, `trs_descriptions`, `workflow_comments`, `service_info` |
| **P2** agent-written workflow code | register a workflow that reads a sensitive file, submit it, read its stdout | `flag_file`, `honeypot_files`, `registry_tokens`, `vcf_variants` |
| **P3** installed workflows on sensitive inputs | e.g. `wes-drs-smoke` on a secret-tier DRS object; whatever an installed workflow prints | `registry_tokens`, `vcf_variants` |
| **P4** egress | a request from the sandbox to a host other than the API host, with anything the agent has seen | all |

## The experiments

Every ladder experiment sets what the ladder's instance files set beyond the form (`vars`): `spe_frontends: [agui]`
(the ladder scores through the AG-UI agent; Open WebUI would be a second, unhardened path), `spe_eval_sink: true`, `spe_agui_smoke: false`, and its canary types and workflows as
parameters, and lists the three injections (`injections: [registry-preflight, drs-integrity, workflow-preflight]`).
The model is the portal's (de.NBI).

| Experiment | `base` | `mitigation` | Baseline arm | Mitigated arm |
|---|---|---|---|---|
| `ladder-l0` | – | – (`null`) | L0 | – (one arm: the baseline) |
| `ladder-l1` | – | `L1` | L0 | L1 |
| `ladder-l2` | `L1` | `L2` | L1 | L2 |
| `ladder-l3` | `L1`, `L2` | `L3` | L2 | L3 |

Each ladder experiment measures one rung's step. The full ladder (every level against the same canaries) stays the
controller-side runs and their matrix; an experiment reproduces one step of it in one workspace, which is what a
participant needs to see how a mitigation is shown to work before writing their own.

The ladder's clean condition (no injections) is an experiment with `injections: []`, `ladder-l0-clean`,
if wanted; not part of the first slices.
