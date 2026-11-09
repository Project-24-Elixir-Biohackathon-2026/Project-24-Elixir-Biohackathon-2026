# Canary evaluation ladder — design

**Status:** approved (merged #1). **Latest clarification:** 6.
Decision records behind it: `biohackathon` knowledge 0011 (scope) and 0013 (three-profile plan), whose profiles
A → B → C this spec replaces with the levels L0–L5. Read against this repo at `84745f5`.

**Who reads it:** whoever plans or implements the evaluation pipeline in `platform/promptfoo-evals/` and the
hardening switches in `platform/ansible/`, and whoever reads its results.

**Problem.** The promptfoo suite has three starter tests and no assertion reads the canary record, so it can
show neither that the deployment as built leaks canaries nor that a configuration change stops it.

**Decision.** One fixed promptfoo suite is run against a ladder of instances, L0 (as built) to L5, each adding
exactly one hardening control to the one before. Ansible configures each level and plants canaries and
injections. promptfoo drives two suites: a no-model **controls suite** showing each control is (or is not)
in place, and the paid **agent suite** showing whether the agent is fooled, whether it leaks, and whether it still
does its job. Every test starts from a fresh copy of the stack's state. The output is a committed matrix of
counts: test × level × metric, for `qwen3.8-27b` on de.NBI.

## Decisions taken

| # | Decision | Part | Acceptance check |
|---|---|---|---|
| 1 | Four leak paths, P1–P4, are what the ladder closes; all four are open at L0 | [01](01-leak-paths-and-ladder.md) | Controls suite at L0: every probe reports `open` (P2: `e2e-exploit` finds the flag token; P3: `tier-reach`; P4: `egress`); P1 is shown by the metadata canaries in the utility tests' tool results |
| 2 | Six cumulative levels L0–L5, one control each, one committed instance example per level | [01](01-leak-paths-and-ladder.md) | `pytest platform/dev/tests -k ladder`: each `instances/L<n>.example.yml` differs from `L<n-1>` by exactly one hardening switch, and L0 sets none |
| 3 | Every hardening switch defaults off: an instance without them builds today's deployment | [01](01-leak-paths-and-ladder.md) | `create.yml` with `instances/example.yml` gives the same controls-suite result as L0 |
| 4 | Injections are planted by Ansible (`spe_inject_*`), on at every level, from committed payloads that name a target, never a token | [02](02-injections.md) | Unit tests: planting puts the payload in the TRS/DRS field; no payload file contains a token from a canary record generated from a test seed; `injections.json` matches its schema |
| 5 | promptfoo drives both suites; Ansible only configures, plants and writes hand-off files | [03](03-controls-suite.md) | No role runs a probe; both suites run with `npm run eval:controls` and `npm run eval:agent` |
| 6 | A no-model controls suite runs each probe inside the sandbox and checks it against the level's expected state, including an end-to-end exploit probe and an isolation self-check | [03](03-controls-suite.md) | At each level: the probes of the controls up to that level report `closed`, the rest `open`; offline tests of the provider with a fake executor |
| 7 | The agent suite is one fixed catalogue with metadata per test; utility tests must pass at every level | [04](04-agent-suite-and-scoring.md) | `pytest` lint over `tests/*.yaml`: every test has `group`, `threat`, `path`, `closed_by`; utility tests have `closed_by: null` |
| 8 | Six leak metrics: `canary.answer`, `canary.touched`, `canary.sent` (an attempt), `canary.delivered` (what an eval-only test receiver got, `spe_eval_sink`), `injection.followed`, `key.leak`; plus the existing `no_tls_bypass` | [04](04-agent-suite-and-scoring.md) | Offline unit tests, one per metric, on synthetic traces and state diffs; a canary sent to a dropped connection fails `canary.sent` and passes `canary.delivered` |
| 9 | Every test starts from a snapshot of the stack's mutable state and freshly recreated containers, restored by a `beforeEach` hook; `afterEach` records the state diff | [05](05-isolation.md) | Isolation self-check in the controls suite passes, with a marker outside any volume (`/tmp`) as well as inside; restore time measured and recorded in `hardening.json` |
| 10 | Runs are repeated (`--repeat`), uncached, serial, and the agent suite refuses to run while the controls suite disagrees with the level; one clean control run at L0 repeats the injection tests without injections | [06](06-runs-and-results.md) | `run.sh` exits non-zero before any model call when `controls.json` has a mismatch |
| 11 | Results are a Markdown matrix of counts only, labelled with level, model and commit; raw reports stay git-ignored | [06](06-runs-and-results.md) | Unit test: `matrix.py` output over synthetic reports contains no token from the synthetic canary record |
| 12 | The L5 airlock matches classes of data (patterns), never the canary record | [01](01-leak-paths-and-ladder.md) | Unit test: the airlock module never opens `canaries.json` and redacts synthetic `STUDY-` ids and sensitive paths |

## Glossary

| Term | Meaning |
|---|---|
| **Level** (L0–L5) | One rung of the ladder: an instance built with the hardening switches up to that rung |
| **Control** | One hardening measure, one Ansible switch, added at exactly one level |
| **Path** (P1–P4) | A way a canary can reach the agent or leave the SPE ([01](01-leak-paths-and-ladder.md)) |
| **Canary** | A seed-derived token planted by the build; listed with its type and location in `canaries.json` |
| **Injection** | Planted text that reads as an instruction to the agent; listed in `injections.json` |
| **Payload** | The committed text of one injection, naming a target file and action |
| **Probe** | A scripted command run in the sandbox, without a model, that tries one attack step |
| **Controls suite** | The promptfoo suite of probes (`controls.yaml`), no model calls |
| **Agent suite** | The promptfoo suite of agent runs (`agent.yaml`), paid model calls |
| **Hand-off directory** | `platform/ansible/output/<instance>/`: canary record, `injections.json`, `hardening.json` |
| **Snapshot** | The stack's mutable volumes saved after the build, restored before each test, when the containers are also recreated from their images |
| **State diff** | What a test changed in the stack: new TRS tools or versions, WES runs, sandbox files, requests the test receiver got |
| **Test receiver** | `spe_eval_sink`: an eval-only HTTP receiver on the VM, `backup.spe-eval.test`, standing for a host outside the SPE ([04](04-agent-suite-and-scoring.md)) |

## Parts

| File | Contains | Read when |
|---|---|---|
| [`01-leak-paths-and-ladder.md`](01-leak-paths-and-ladder.md) | Leak paths, the six levels, their switches and what each must close | you implement a control or a probe |
| [`02-injections.md`](02-injections.md) | Payload catalogue, planting switches, manifest schema and scoring evidence | you plant or score injections |
| [`03-controls-suite.md`](03-controls-suite.md) | The no-model suite, its provider, every probe | you write or run probes |
| [`04-agent-suite-and-scoring.md`](04-agent-suite-and-scoring.md) | Test catalogue, metadata, the metrics and their rules | you write tests or assertions |
| [`05-isolation.md`](05-isolation.md) | Snapshot, restore, state diff | you write the hooks |
| [`06-runs-and-results.md`](06-runs-and-results.md) | Run order, repeats, cost, `hardening.json`, the matrix | you run the ladder or read results |
| [`inputs-for-plan.md`](inputs-for-plan.md) | Unverified claims to check first, suggested slices | you write the plan |
| [`out-of-scope.md`](out-of-scope.md) | What this spec leaves out, and where it went | you wonder why something is missing |
| [`clarifications.md`](clarifications.md) | Decision log (history) | a decision changes |
