# 2026-11-09: slice 5 done (tasks 1–3); slice 6 next, controls only

Slice 5 shipped tasks 1–3: the provider's state diff, the `metrics.py` carry-overs, `agent.yaml` with the
13-test catalogue, and the dry run against the scripted agent on de.NBI L0, which passed its wiring checks (PR
#64). This note replaces the older slice-5 handoffs.

- **Reordered around the missing de.NBI key**, by the user's ruling on #64 (comment 6738237144), recorded in the
  plan README's *Rulings*. Slices 6–9 build their level and verify it with the controls suite only, with no model
  calls; their builds use a placeholder `SPE_LLM_API_KEY`. Every agent run moves to the new slice 10
  (`slice-10-agent-runs.md`). It opens the key gate on its own PR, and `BACKLOG.md` *Next* holds the key until
  then. The gate on #64 was cleared at the merge.
- **The de.NBI VM stands at L0** (slice 4's build). Snapshots exist. The jump host was closed from about
  08:25Z to 09:36Z today: probe TCP once before any login, and never retry ssh blindly.
- **Open questions for the user** in `BACKLOG.md` *Next*: F11 (study-id canaries in DRS object names) and the
  key.
- **For slice 7's session:** `slice-7-l2.md:316` asks the user about a failed genomes run. That stop is not on
  *Gates*' list, so rule on it and record the ruling (#64 review, item 11).

## Next

Slice 6/10, `impl/canary-eval-ladder-6-l1` (`slice-6-l1.md`): `spe_harden_trs_readonly`, L1 built on de.NBI, and
the controls suite at L1. Task 1 verifies Traefik method routing and WESkit first.
