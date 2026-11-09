# 2026-11-09: plan refreshed, next is slice 2

**Done (PR #59, change).** The plan follows `main`'s layout (compose overlays added by `spe-apply`, the runbook at
`roles/sandbox/files/agent/AGENTS.md`, `spe_frontends`); `biohackathon` 0015 is folded as spec clarification 7
(clean and injected runs at L0 and L1, one-fixture runs deferred to `BACKLOG.md`); runs on de.NBI need no OK;
`handoff.read_hosts` reads the `frontends` list (`b210508`). Every ruling: [README *Rulings*](../README.md#rulings).

**Overtaken.** The handoff `2026-10-23T0810Z-slice-1-done-next-is-slice-2.md`, R1, says slice 2's clarification is
7: it is now **8** (slice 2, task 1, step 5; ruling *slice 2's clarification is 8*).

**Known stale, fixed later.** The docstrings and comments in `platform/promptfoo-evals/handoff.py` (~181) and
`matrix.py` (~11, ~181) still say "clarification 6" and "clean control"; slice 3, task 5 rewrites them.

**Next unit: slice 2/9** `impl/canary-eval-ladder-2-isolation`, [slice-2-isolation.md](../slice-2-isolation.md).
One de.NBI instance has the user's standing OK (`AGENTS.md`, *Setup*): no asking before building, rebuilding or
running against it. Keep slice 2's own stop: a median restore above ~180 s.
