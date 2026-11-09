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
| WES runs, logs and the workflow cache | `weskit-data`, `wes-mongodb`, `redis-data` | yes |
| TRS tools, DRS objects | the filers' MongoDB volumes | yes |
| sandbox files and history | `open-terminal-data` | yes (recreated empty) |
| seeded data | `/data-share` | no: read-only to workflows, not mounted in the sandbox |
| anything written outside a volume (the sandbox's `/tmp`, a workflow in a worker's writable layer), anonymous volumes | the containers of the workflow stack and the sandbox | yes: recreated from their images |
| the agent | `agent` container | no: read-only apart from its run log, which the agent cannot read |
| chat sessions of the AG-UI chat | `chat-sessions` (mounted by `chat-ui` only) | no: evaluations call the agent directly, never `chat-ui` |
| requests the test receiver got | its log on the VM (`spe_eval_sink`, [04](04-agent-suite-and-scoring.md)) | no: append-only; the baseline records its length and the diff reads what was appended |

## Hooks (decision 9)

promptfoo's Python extension hooks (`extensions:`, verified in its configuration reference):

- `beforeAll`: check that a snapshot exists for this instance; take it if not.
- `beforeEach`: restore, then record the state baseline (TRS tools and versions, WES run ids, sandbox file list,
  the length of the test receiver's log).
- `afterEach`: record the state diff against the baseline into the test's metadata, for `injection.followed`
  ([04](04-agent-suite-and-scoring.md)) and for the report ("the agent registered a workflow").

Both suites use the hooks. The `isolation` probe ([03](03-controls-suite.md)) checks that a restore removes the
markers the previous test left, in a volume and outside any volume, so a broken restore fails before any agent run. The restore time is measured and
recorded in `hardening.json`; at ~1 minute it adds ~5½ hours to a full ladder.
