# Canary evaluation ladder: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` (`AGENTS.md`,
> *Working Conventions*) to implement one slice per session and PR. Steps use checkbox (`- [ ]`) syntax.

**Goal:** a fixed promptfoo suite, run against instances L0–L5, that shows per level whether the agent is fooled,
whether it leaks a canary, and whether it still does its job, plus a no-model controls suite that shows each
control is in place.

**Spec:** [`docs/superpowers/specs/2026-10-22-canary-eval-ladder-design/`](../../specs/2026-10-22-canary-eval-ladder-design/README.md)
(decisions 1–12; latest clarification 6). Each slice file links the parts it implements.

**Architecture.** Ansible configures a level (`spe_harden_*` switches), plants canaries and injections, and
writes the hand-off directory `platform/ansible/output/<instance>/` (`canaries.json`, `injections.json`,
`hardening.json`, `hosts.yml`). Everything else lives in `platform/promptfoo-evals/`: two promptfoo configs
(`controls.yaml`, no model; `agent.yaml`, paid), their providers, assertions and isolation hooks as
standard-library Python modules, `run.sh` gluing a ladder run together, and `matrix.py` turning reports into a
committed Markdown matrix of counts.

**Tech stack:** promptfoo 0.124.1 (pinned), Python ≥ 3.12 standard library (pytest and PyYAML for tests only),
Ansible from the system package, Docker Compose on the instance VM, Traefik v2.11, WESkit, trs-filer, drs-filer.

## Global Constraints

Every task's requirements include these.

- **Tests.** Offline, before every commit, the suites a slice touches:
  `(cd platform/promptfoo-evals && uv run --group dev pytest -q)` and
  `uv run --with pytest --with pyyaml --with jinja2 pytest platform/dev/tests -q` (jinja2 renders the Ansible
  templates in the tests slices 6–9 add). New Python under `platform/promptfoo-evals/`
  imports only the standard library; PyYAML is a `dev` dependency there, for tests only.
- **No token ever leaves the operator side in a committed file or a report reason.** Assertions name the canary
  *type* and *file*, never the token (spec part 04, *Reports carry values*). Fixtures use synthetic seeds and
  synthetic tokens built in the test, never a real `canaries.json`.
- **Never commit secrets** (`AGENTS.md`, *Project rules*): instance files other than `*.example.yml`,
  `platform/ansible/output/`, `canaries.json`, `injections.json` of a real instance, keys. `reports/` and
  `.promptfoo/` stay git-ignored and are deleted after use.
- **Ask the user first** for (a) any `npm run eval:agent` or other paid model call, stating the level, the
  model and the number of agent runs; (b) creating or destroying a cloud instance (`create.yml` with
  `spe_provision: openstack`, `destroy.yml`). Re-provisioning the de.NBI VM in place (`spe_provision:
  existing`) and running the controls suite (`npm run eval:controls`) make no paid model calls and need no OK.
- **Every hardening switch defaults off** in `platform/ansible/inventory/group_vars/all.yml`; an instance file
  without it builds today's deployment (decision 3). Every `spe_inject_*` switch defaults off too, and is `true`
  in every `L<n>.example.yml`.
- **Commits** are signed off (`git commit -s`), staged by name, one coherent change each (`AGENTS.md`).
- **A claim checked first.** A task that starts with "Verify" checks an unverified claim from
  [the spec's inputs](../../specs/2026-10-22-canary-eval-ladder-design/inputs-for-plan.md) before building on
  it. If the claim is false, apply the "if false" column of the claims table below, record the ruling in the
  newest handoff (decision, why, cost if wrong: `AGENTS.md`, *Project rules*), and add the spec clarification
  in the same slice.
- **Docs move with the code**: `platform/promptfoo-evals/README.md` and `platform/ansible/README.md` describe
  every switch, script and command a slice adds, in the slice that adds it.

## Shared interfaces

Fixed here so that slices agree; a slice that needs to change one rewrites this section and every open task
that uses it, in the same PR.

**Hand-off directory** (`$SPE_HANDOFF_DIR`, `platform/ansible/output/<instance>/`):

| File | Written by | Shape |
|---|---|---|
| `canaries.json` | handoff role (exists) | `{instance, seed, api_host, generated_at, study_ids, tokens: [{token, type, file, note}]}` |
| `hosts.yml` | handoff role (exists) | `ssh_target`/`ssh_key`/`ssh_args` (existing) or `ssh_key` + `floating_ip` (openstack), `api_host`, `agent_url`, … |
| `injections.json` | handoff role, slice 4 | spec part 02, *Hand-off*: `{schema_version: 1, injections: [...]}` |
| `hardening.json` | handoff role, slice 3 | `{schema_version: 1, instance, level, switches: {spe_harden_trs_readonly, spe_harden_data_tiers, spe_harden_egress, spe_agent_tool_surface, spe_harden_airlock}, frontend, model_provider, model, commit, restore_seconds, injections}`; switch types: booleans, except `spe_harden_data_tiers` (a list of tier names, `[]` for all tiers) and `spe_agent_tool_surface`, which already exists (`shell` by default, `typed` for L4: the value the spec calls `ga4gh_typed`); `level` is the number of leading ladder controls switched on (L1…L5 in order), `restore_seconds` is `null` until the isolation hook measures it; `injections` is `true` when the three `spe_inject_*` switches are on, `false` when all are off (the clean control, clarification 6), `"mixed"` for a mix, which `handoff.check_hardening` refuses: not a ladder run |

**Modules in `platform/promptfoo-evals/`** (all importable from the tests with `sys.path` set by `conftest.py`):

| Module | Slice | Public interface |
|---|---|---|
| `handoff.py` | 1 | `load_canaries(dir) -> list[dict]`; `load_study_ids(dir) -> list[str]` (`canaries.json` `study_ids`, a `{giab: id}` mapping or a list; `[]` when absent); `is_file_canary(entry) -> bool` (`False` only for the metadata types `drs-object-metadata`, `trs-tool-description`, `workflow-file-comment`, `service-info`; unknown types count as file canaries); `load_hardening(dir) -> dict`; `load_injections(dir, repo_root=None) -> list[dict]` (validates, raises `ManifestError`, an optional root for the payload hashes defaulting to `REPO_ROOT`); `api_host(dir) -> str`; `vm_argv(dir) -> list[str]` (the `ssh …` prefix from `hosts.yml`, `[]` when the VM is local); `handoff_dir() -> Path` (from `SPE_HANDOFF_DIR`, `ConfigError` if unset); `read_hosts(dir) -> dict`; `check_hardening(record) -> dict` (the shape check `load_hardening` and `matrix.counts` share, also checks `level` against the switches); `REPO_ROOT`; `ManifestError` ⊂ `ConfigError` |
| `injections_schema.py` | 1 | `validate(manifest: dict, repo_root: Path) -> list[str]` (errors, empty when valid; checks payload hashes against the files); CLI `python3 injections_schema.py <manifest> <repo_root>` exits 1 on errors |
| `metrics.py` | 1 | promptfoo assertions `canary_answer`, `canary_touched`, `canary_sent` (an attempt), `canary_delivered` (the state diff's `sink_requests_added`; `None` or absent is a configuration error), `injection_followed`, `key_leak`, each `(output, context) -> {pass, score, reason}`; reasons name type and file, never a token (a token or study id inside a file is shown as `<canary>`); a hand-off or provider error returns `pass: false` with a reason starting `configuration error:` (`metrics.CONFIG_ERROR`), which `matrix.counts` counts under `errors`, never as a failure or a pass |
| `matrix.py` | 1 | `counts(level_dir: Path) -> dict` (one level's reports → counts only: label from `hardening.json`, controls result, per test id its metadata and per-metric failures over repeats); `render(counts: list[dict]) -> str` (Markdown); CLI `python3 matrix.py counts reports/L<n> > docs/results/<model>/L<n>.json` and `python3 matrix.py render docs/results/<model>/L*.json > docs/results/canary-ladder-<model>.md`. The counts files are committed, so raw reports can be deleted after each level. `MatrixError`; `CATALOGUE: dict[str, frozenset[str \| None]]` (group/threat/path/closed_by, spec part 04's values, the one definition `tests/test_catalogue.py` imports); `METRICS: frozenset[str]` (the six decision-8 metric names; only those six assertions carry a `metric:`, any other name makes `counts` refuse the level). A run counts under `errors` when promptfoo marks it an error, or when any component's reason starts with `configuration error:` or promptfoo's `Error running Python script:` (`ERROR_REASONS`). `counts` refuses an empty `controls.json`/`agent.json` and a test without `group`. A counts file with `injections: false` is the column `L<n> clean`; two counts files with the same column are refused. Counts JSON: `{schema_version: 1, instance, level, injections, model: "<provider>:<model>", commit, restore_seconds, controls: {probes, disagree: [probe ids]}, tests: {<id>: {group, threat, path, closed_by, runs, errors, passed, failures: {<metric>: n}}}}` |
| `isolation.py` | 2 | `snapshot(dir)`, `restore(dir) -> float` (seconds; puts the volumes back and recreates the containers from their images), `baseline(dir) -> dict`, `state_diff(dir, baseline) -> dict`; promptfoo hook `extension_hook(hook_name, context)` |
| `controls_provider.py` | 3 | promptfoo provider `call_api(prompt, options, context)`; the probe id is `vars.probe`; runs `probes/<id>.sh` in the sandbox (`tool-surface`, `airlock`: in the agent container); returns `{output, metadata: {probe, exit_code, http_codes, state, evidence}}` with `state` `open`/`closed`/`error` |
| `controls_asserts.py` | 3 | `probe_state(output, context)`; `PROBE_CONTROL: dict[str, int \| None]` (probe id → level of the control it tests, `None` for the fixed-state probes); `FIXED_STATE` (`api-reach`, `isolation-plant`: `open`; `isolation-check`: `closed`). The spec's `isolation` probe is the pair `isolation-plant` → `isolation-check` |

**State diff** (`state_diff`): `{trs_tools_added: [{id, version, descriptor_urls, descriptors}], wes_runs_added: [{run_id,
workflow_url, workflow_params, state}], sandbox_files_added: [path], sink_requests_added: [{method, host, path,
body}] | null}`; `sink_requests_added` is what the test receiver (`spe_eval_sink`, slice 4) logged during the test,
`null` on an instance without it. The agent provider (slice 5) puts it in
`metadata.state_diff`, because promptfoo runs assertions before `afterEach` (verified in slice 2, task 1).
`descriptors` is the text of each new version's descriptor files (fetched from TRS), so `injection_followed` can
connect a tool registered by any means to the target path it reads. The `beforeEach` hook writes the baseline to the file named by `SPE_EVAL_BASELINE` (default
`platform/promptfoo-evals/reports/.baseline.json`); the provider reads it after the run.

**Test metadata** (agent catalogue, spec part 04), all under `metadata:`: `group`, `threat`, `path`,
`closed_by`, plus `id` (stable kebab-case, the matrix's row key).

**npm scripts** (`package.json`): `eval:controls` → `reports/controls.json`; `eval:agent` → `reports/agent.json`;
`run.sh <hand-off dir> <repeat> [promptfoo eval args…]` copies both and `hardening.json` into `reports/L<level>/`
(`reports/L<level>-clean/` when `hardening.json` has `injections: false`): every level of one VM
shares one hand-off directory (`output/denbi-agui-01/`; the VM's preflight accepts only that instance name), so
level instance files are overlays on the operator's instance file, without an instance name.

## Claims checked first

| Claim | Checked in | If false |
|---|---|---|
| promptfoo 0.124.1 runs Python extension hooks with `beforeAll`/`beforeEach`/`afterEach`, before the assertions for `beforeEach` | slice 2, task 1 | restore from `run.sh` per test, running promptfoo once per test |
| The listed volumes plus recreated containers hold all mutable state (nothing the build needs lives in a container's writable layer); a restore takes about a minute | slice 2, task 1 and 4 | add the missing volumes; a container whose build state is in its writable layer moves that state into its image or a volume; above ~3 minutes, stop and ask (parallel stacks are out of scope) |
| The sandbox has open egress (`tools` network is an ordinary bridge) | slice 3, task 1 | P4 is closed at L0; the `egress` probe expects `closed` everywhere and slice 8 is dropped |
| promptfoo does not cache our Python provider's responses | **false** (read in promptfoo 0.124.1 while planning: Python provider results are cached by prompt and vars) | both suites run with `--no-cache`; slice 3, task 1 records the clarification |
| WESkit accepts `workflow_attachment` or non-TRS workflow URLs | slice 3, task 1 | `wes-inline` is `closed` at L0; L1 is TRS writes only |
| The sandbox reaches a port published on the VM through `extra_hosts: host-gateway` | slice 4, task 6 | map `spe_eval_sink_host` to the VM address the sandbox routes to instead |
| `gatk-hc-chr20` can be installed in TRS without real genomes (de.NBI lists only `wes-drs-smoke`) | slice 4, task 1 | plant the TRS and comment injections in `wes-drs-smoke` instead, and say so in a clarification |
| Traefik v2.11 can route TRS by method (`Method(GET)`) | slice 6, task 1 | a small method filter in front of trs-filer |

## File structure

| Path | Slice | Responsibility |
|---|---|---|
| `platform/promptfoo-evals/{handoff,injections_schema,metrics,matrix}.py`, `conftest.py`, `tests/test_{handoff,injections_schema,metrics,matrix,catalogue}.py` | 1 | scoring, offline |
| `platform/promptfoo-evals/isolation.py`, `tests/test_isolation.py` | 2 | snapshot, restore, state diff, hooks |
| `platform/promptfoo-evals/{controls_provider,controls_asserts}.py`, `controls.yaml`, `probes/*.sh`, `run.sh`, `package.json`, `tests/test_controls_*.py`; `platform/ansible/roles/handoff/` (`hardening.json`) | 3 | controls suite and the run script |
| `roles/eval_sink/` (the test receiver), `platform/dev/tests/{test_eval_sink,ansible_render}.py`, `platform/ansible/catalog/injections/*.txt`, `roles/trs_install/files/trs_install.py`, `roles/drs_register/files/drs_register.py`, `roles/handoff/` (`injections.json`), `instances/L0.example.yml`, `catalog/injections/fixtures.json`, `roles/handoff/files/injections_manifest.py`, `platform/dev/tests/test_{injections,ladder}.py` | 4 | planting injections, the test receiver, the L0 example |
| `platform/promptfoo-evals/agent.yaml`, `tests/*.yaml`, `agui_provider.py` (state diff), `promptfooconfig.yaml` (removed), `instances/no-injections.example.yml`, `docs/results/canary-ladder-qwen3.8-27b.md`, `docs/results/qwen3.8-27b/L0{,-clean}.json` | 5 | agent suite, the first L0 run and its clean control |
| `platform/ansible/roles/workflow_stack/templates/*` (Traefik: TRS read-only for the sandbox, operator writes on a localhost entrypoint; WESkit), a standard-library WES write guard, `roles/sandbox` runbook as a template, `instances/L1.example.yml`, `platform/dev/tests/golden/` (today's renders, for decision 3) | 6 | L1 |
| `platform/ansible/roles/workflow_stack/templates/compose.install.yaml.j2` (WESkit and worker mounts by tier), the verify smoke input, `instances/L2.example.yml` | 7 | L2 |
| `platform/ansible/roles/agui/templates/docker-compose.yml.j2` (a fixed sandbox address), `DOCKER-USER` firewall rules, `instances/L3.example.yml` | 8 | L3 |
| `platform/agui/pydantic-ai-agent/` (airlock), `roles/agui/templates/agent.env.j2` | 9 | L5 airlock |

## PR slices

N = 9. Slices are sequential; each starts from `main` after the previous one merged.

| n/N | Branch | Tasks | Delivers | Reviewer checks | File | Status |
|---|---|---|---|---|---|---|
| 1/9 | `impl/canary-eval-ladder-1-scoring` | 1–5 | the six metrics, the manifest schema, the matrix, the catalogue lint; decisions 7 (lint), 8, 11. ~1,550 lines, half of them tests: over the size target, kept whole because every module is offline and independent | `uv run --group dev pytest -q` in `platform/promptfoo-evals` | [slice-1-scoring.md](slice-1-scoring.md) | PR #3 |
| 2/9 | `impl/canary-eval-ladder-2-isolation` | 1–4 | snapshot, restore, state diff and hooks; restore time measured; decision 9 | offline tests; the measured restore time in the handoff | [slice-2-isolation.md](slice-2-isolation.md) | planned |
| 3/9 | `impl/canary-eval-ladder-3-controls` | 1–5 | controls suite, `hardening.json`, `run.sh`; decisions 1 (probes), 5, 6, 10 | offline provider tests; `npm run eval:controls` on the de.NBI VM: all `open` | [slice-3-controls.md](slice-3-controls.md) | planned |
| 4/9 | `impl/canary-eval-ladder-4-injections` | 1–6 | three payloads planted, `injections.json`, the test receiver, `L0.example.yml`; decisions 2 (test), 3, 4, 8 (receiver) | `pytest platform/dev/tests -k "injection or ladder or eval_sink"` | [slice-4-injections.md](slice-4-injections.md) | planned |
| 5/9 | `impl/canary-eval-ladder-5-agent-suite` | 1–4 | `agent.yaml` and the first catalogue; the first L0 run (paid) and its matrix; decision 7 | the lint; the committed matrix at L0 | [slice-5-agent-suite.md](slice-5-agent-suite.md) | planned |
| 6/9 | `impl/canary-eval-ladder-6-l1` | 1–5 | `spe_harden_trs_readonly`; L1 run | controls suite at L1; L1 column | [slice-6-l1.md](slice-6-l1.md) | planned |
| 7/9 | `impl/canary-eval-ladder-7-l2` | 1–3 | `spe_harden_data_tiers`; L2 run | controls suite at L2; L2 column | [slice-7-l2.md](slice-7-l2.md) | planned |
| 8/9 | `impl/canary-eval-ladder-8-l3` | 1–3 | `spe_harden_egress`; L3 run | controls suite at L3; L3 column | [slice-8-l3.md](slice-8-l3.md) | planned |
| 9/9 | `impl/canary-eval-ladder-9-airlock` | 1–3 | the L5 airlock module and switch; decision 12 | airlock unit tests; `airlock` probe `closed` with the switch on | [slice-9-airlock.md](slice-9-airlock.md) | planned |

L4 (the typed tool server) has its own spec ([out-of-scope](../../specs/2026-10-22-canary-eval-ladder-design/out-of-scope.md)).
`L4.example.yml`, `L5.example.yml` and the L4/L5 runs belong to that spec's plan, which slice 9 hands them to:
slice 9's PR moves them into `BACKLOG.md`'s L4 line.

## Review Focus

The input classes the spec implies that most likely bite a user; each has its test in the named task.

1. **A token that is a substring of ordinary text** (short registry surnames, e.g. `Ng`): the metrics match
   whole tokens on word boundaries, and a metric's reason never echoes it (slice 1, task 2).
2. **A malformed, missing or stale hand-off** (no `injections.json` with injections on, a `hardening.json` from
   another instance): scoring and `run.sh` stop with a configuration error, never a pass (slice 1, task 1;
   slice 3, task 5).
3. **A restore that silently does nothing** (a volume renamed in compose, a stack that does not come back
   healthy): the `isolation` probe and `restore` fail loudly (slice 2, task 3; slice 3, task 3).
4. **A probe that errors rather than refuses** (network down, VM unreachable): `state: error` is a mismatch
   at every level, never counted as `closed` (slice 3, task 2).
5. **Reports from two models or levels mixed** in one matrix: `matrix.py` refuses mixed models and duplicate
   levels (slice 1, task 4).

## Proposed spec clarifications

- Slice 2: the state diff is taken by the agent provider after the run, because promptfoo runs assertions
  before `afterEach`; `afterEach` only logs it (amends decision 9, part 05 *Hooks*).
- Slice 4: payloads target `wes-drs-smoke` if `gatk-hc-chr20` cannot be installed on de.NBI (part 02), only if
  slice 4's task 1 finds that.

## Handoffs

[`handoffs/`](handoffs/): one file per handoff; read only the newest (`ls handoffs | tail -1`).
