# Isolation

The agent tests run against one live instance. Without isolation, one test changes what the next sees: files in
the sandbox's persistent `/home/user`, TRS tools the agent registered, WES runs and their logs. A later test
could then leak through an earlier test's leftovers, and repeats would not be independent samples.

## What others do, and what we do

Agent benchmarks build once and start a fresh copy per task: a new container from a built image, a restored VM
snapshot, a database reloaded from the same initial data, a fresh sandbox per sample (Inspect, verified in its
documentation; the others from general knowledge). A new instance per test is not an option here (a build takes
about 7 minutes, plus a VM: ~40 hours over a full ladder), nor is a VM snapshot (the IP, certificate and API host
change). The same pattern applies at the level of Docker volumes:

- **Snapshot** once, after `create.yml` and `verify.yml`: the stack's mutable volumes.
- **Restore** before every test: stop the workflow stack and the sandbox, put the saved volumes back, recreate the
  containers from their images, wait until healthy. Recreating, not restarting: a restarted container keeps its
  writable layer, so a file the agent left in the sandbox's `/tmp`, or a workflow in a worker's, would reach the
  next test.

Restoring, not cleaning up: a cleanup removes what we know of and leaves the rest (for example WESkit's
per-version workflow cache, which outlives a deleted TRS tool). A restore removes everything the stack holds.

## Mutable state

| State | Where | Restored |
|---|---|---|
| WES runs, logs and the workflow cache | `weskit-data`, `weskit-workflows`, `wes-mongodb`, `redis-data` | yes |
| TRS tools, DRS objects | the filers' MongoDB volumes | yes |
| sandbox files and history | `open-terminal-data` | yes (from the snapshot) |
| seeded data | `/data-share` | no: read-only to workflows, not mounted in the sandbox |
| anything written outside a volume (the sandbox's `/tmp`, a workflow in a worker's writable layer), anonymous volumes | the containers of the workflow stack and the sandbox | yes: recreated from their images |
| the agent | `agent` container | no: read-only apart from its run log, which the agent cannot read |
| chat sessions of the AG-UI chat | `chat-sessions` (mounted by `chat-ui` only) | no: evaluations call the agent directly, never `chat-ui` |
| requests the test receiver got | its log on the VM (`spe_eval_sink`, [04](04-agent-suite-and-scoring.md)) | no: append-only; the baseline records its length and the diff reads what was appended |

## Hooks (decision 9)

promptfoo's Python extension hooks (`extensions:`, verified in its configuration reference):

- `beforeAll`: check that a snapshot exists for this instance; take it if not.
- `beforeEach`: restore, then record the state baseline (TRS tools and versions, WES run ids, sandbox file list,
  the length of the test receiver's log) in the file named by `SPE_EVAL_BASELINE` (default `reports/.baseline.json`). A failed restore raises, which
  aborts the eval: no test runs on unrestored state.
- the agent provider, after its run: the state diff against that baseline, in the response's
  `metadata.state_diff`, for `injection.followed` ([04](04-agent-suite-and-scoring.md)) and for the report ("the
  agent registered a workflow"). promptfoo runs the assertions before `afterEach` (clarification 8).
- `afterEach`: logs the state diff's counts; it changes nothing.
- `afterAll`: restores once more, so a finished run leaves the stack as built (clarification 9). An in-place
  rebuild does not wipe the volumes, so the next build's snapshot would otherwise hold this run's state. A run
  that stops early leaves a marker in the hand-off directory, and `beforeAll` refuses to snapshot a new build over
  it.

The state diff reads additions only: new TRS tools and versions, new WES runs, new sandbox files and receiver
requests. A descriptor overwritten in an existing TRS version or an edited existing sandbox file is not seen
(clarification 9): a payload ([02](02-injections.md)) whose effect is such an edit needs the baseline to hash
descriptors and files first.

Both suites use the hooks. The `isolation` probe ([03](03-controls-suite.md)) checks that a restore removes the
markers the previous test left, in a volume and outside any volume, so a broken restore fails before any agent run. The restore time is measured and
recorded in `hardening.json`; at ~1 minute it adds ~5½ hours to a full ladder.
