# Inputs for the plan

## Unverified claims to check first

Each is a task's first step; a claim that turns out false changes the part named.

| Claim | Part | If false |
|---|---|---|
| WESkit accepts `workflow_attachment` or non-TRS workflow URLs | [01](01-leak-paths-and-ladder.md) L1 | `wes-inline` is `closed` at L0 already; L1 is TRS writes only |
| The sandbox has open egress (the `tools` network is an ordinary bridge) | [01](01-leak-paths-and-ladder.md) L3 | P4 is closed at L0; L3 becomes a no-op and is dropped |
| Traefik v2.11 can route TRS by method (`Method(GET)` in the router rule) | [01](01-leak-paths-and-ladder.md) L1 | a small method filter in front of trs-filer |
| The listed volumes hold all of WESkit's and the filers' mutable state | [05](05-isolation.md) | add the missing ones; the `isolation` probe finds what was missed |
| A restore takes about a minute | [05](05-isolation.md), [06](06-runs-and-results.md) | above ~3 minutes: parallel stacks on one VM (out of scope until measured) |
| promptfoo 0.124.1 runs Python extension hooks with `beforeEach` / `afterEach` | [05](05-isolation.md) | restore from `run.sh` per test, running promptfoo once per test |
| promptfoo does not cache our Python provider's responses | [06](06-runs-and-results.md) | `--no-cache` covers it either way |

## Suggested slices

1. Scoring offline: the metrics, `probe_state`, `matrix.py`, the catalogue lint, with their unit tests. No instance.
2. Isolation: snapshot, restore, state diff, the hooks; measure the restore time.
3. Controls suite: the provider and the L0 probes, `e2e-exploit` included; `hardening.json`; `run.sh`.
4. Injections ([02](02-injections.md)) and the agent catalogue; the first L0 ladder run (de.NBI model calls).
5. L1. 6. L2. 7. L3: each its switch, its instance example, its probes passing, the ladder run for that level.
8. L5's airlock (L4 comes from its own spec; the L5 run waits for it).
