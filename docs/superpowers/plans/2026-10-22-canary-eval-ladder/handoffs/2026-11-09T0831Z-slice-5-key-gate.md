# 2026-11-09: slice 5 tasks 1–2 done; task 3 waits on the jump host, task 4 on a de.NBI key

Slice 5 (`impl/canary-eval-ladder-5-agent-suite`, draft PR #64, opened by REST: `gh pr create` fails on the
org parent, `docs/knowledge/gh-pr-create-token.md`). Run with `superpowers:subagent-driven-development`; its
ledger is git-ignored (`.superpowers/sdd/slice-5-agent-suite/progress.md` in this worktree) and holds the
pre-flight table and every ruling below in full.

## Done

- **Task 1** (`bf8adfe`): `agui_provider` returns `metadata.state_diff` with `state_diff: true`, reading the
  baseline through `isolation.read_baseline()`; a missing baseline or failed diff is an `error`. Review clean.
- **Task 2** (`6f0093d..2e1f25b`): the slice-1 carry-overs in `metrics.py` (unset API key → configuration error;
  `injection_followed` counts an action only after its exposure), utility asserts, `agent.yaml`, the 13-test
  catalogue, the starter config and `eval` script removed, docs updated. Review: two Important findings fixed in
  one round (state-diff evidence now takes its matching trace call's index; the README's *Add a test* example).
  Tests: promptfoo-evals 371 passed, `platform/dev/tests` 182 passed (with `--with jinja2`).

## Rulings (pre-flight and review; the ledger has why and cost)

- F1: `no_tls_bypass` carries no `metric:` (only the six decision-8 metrics do).
- F2: the slice-1 `metrics.py` carry-overs done first, as their own commit.
- F3/F4: the provider reuses `isolation.read_baseline()`; tests use the real baseline shape.
- F5–F7: README anchored on the real table; `AGENTS.md`/`getting-started.md` updated; `--with jinja2`.
- F11: 20 of 36 DRS object names hold a `registry-study-id` canary, so utility rows listing DRS objects will fail
  `canary.answer` at every level. Kept scored (the plan: "metadata canaries met here are P1"); to go into
  `BACKLOG.md` and the slice's done handoff as a question for the user.
- Review I1: clarification 3 (exposed first) binds over the brief's "state-diff evidence counts as the last call".
- Task 4's `build()` as corrected: `-e @$PRIVATE/instances/denbi.yml -e @instances/L0.example.yml
  -e '{"spe_agent_allowed_models": []}'`, branch pushed first, key only in the environment, no direct snapshot.

## Blocked

- **Task 3** (dry run against the scripted agent): `eval:controls`' `beforeAll` failed with
  `isolation.RestoreError: … the VM is unreachable (exit 255)`. At 08:2xZ the jump host
  (`denbi-jumphost-01.bihealth.org`, 194.94.4.4) stopped accepting TCP on port 22 from this guest; at 07:5xZ
  `ssh agent-service-1` worked. Probe with TCP only (`timeout 10 bash -c 'echo > /dev/tcp/194.94.4.4/22'`), never
  repeated logins. Once open, re-dispatch task 3 unchanged (brief: `scripts/task-brief <plan> 3`).
- **Task 4** needs a working de.NBI key: Coder is not logged in on this guest, and the VM's `agent.env` holds the
  slice-4 placeholder (401). Gate on PR #64.

## Next

Task 3 when the jump host answers; task 4 when the gate is answered; then the final whole-branch review, the
local review round and the merge.
