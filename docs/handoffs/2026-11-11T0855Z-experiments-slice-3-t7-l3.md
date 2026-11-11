# 2026-11-11: experiments slice 3 (`spe-eval`, PR #88), task 7: L1, L2 measured; L3 found a Compose bug

Mid-unit handoff (context budget). Same unit, same worktree:
`.claude/worktrees/impl-experiments-3-spe-eval`, branch `impl/experiments-3-spe-eval`, draft PR **#88**.
Previous handoffs: `2026-11-10T2141Z-experiments-slice-3-t7-l1.md` (how builds are made) and
`2026-11-10T2124Z-experiments-slice-3-before-t7.md` (its *Rulings to carry into the PR body* still apply).

## Done this session

- **Bug 2 fixed** `aa6b647`: `spe_data_root`, `spe_min_free_gb`, `spe_manage_docker` in `spe_local_vars`
  (test in `test_repo_local_vars.py`); confirmed in the VM's `local.yml`.
- **Full dev suite** at `f8eb713`: 443 passed. (Since then only `2bb3077`; its tests and the lock tests: 10 passed.)
- **Disk:** agent-service-1 was at 4 GB free; `docker builder prune -af` before each build (note updated `f8eb713`).
- **L1** run `20261110T215959Z` and **L2** run `20261110T231725Z` (`--repeat 1`, qwen3.8-27b): both arms ok,
  controls "all 10 as expected", payload digests as in `docs/results/canary-ladder-qwen3.8-27b.md`, restore 44-45 s.
  Agent counts are single samples (some differ from the committed 3-5 repeat columns). Reports on the VM under
  `~/spe-eval/reports/ladder-l{1,2,3}/`; tables for the PR body: `scp -r` an arm dir, then from
  `platform/promptfoo-evals` `python3 matrix.py counts <arm dir> > x.json` per arm, `python3 matrix.py render *.json`.
- **L3** run `20261111T081252Z`: baseline ok; **mitigated failed** before any test, and the return to the build's
  arm failed too: Compose 5.3 / Docker 29 drop the agent's `agent` alias when the egress overlay recreates the
  `tools` network. Reproduced, fixed in `spe-apply up` (`--force-recreate` when the networks digest changes or is
  unknown) `2bb3077`, note `docs/knowledge/compose-network-alias-lost.md`. **Not yet verified on the VM.**

## Ruling: no rebuild between ladder levels (asked by the user, checked in code)

`check_creation_time` skips `experiment` and `mitigations`; L1..L3 have identical creation-time settings (the
rendered builds differ only in mitigation switches); `arm_vars` sets every mitigation's on/off and `spe-eval run`
applies each arm with `spe-apply all`. So one build serves `spe-eval run ladder-l1|l2|l3`; the gate refuses an
experiment whose creation-time settings differ. Cost if wrong: a level measured on a stack that differs from a
fresh build in something the arm does not set; the empirical check (L2 mitigated vs L3 baseline `hardening.json`
`switches`) is still to do. Record this in the PR body's rulings.

## Next

1. On the VM: the instance is now broken (agent has no `agent` alias on `tools`, last arm's state). `cd ~/sperange
   && git pull` (branch at `2bb3077`), then `spe-apply all` (the missing digest recreates everything); check
   `docker compose -p spe-frontend exec -T sandbox getent hosts agent`. Then re-run
   `env -u XDG_RUNTIME_DIR -u DBUS_SESSION_BUS_ADDRESS spe-eval run ladder-l3 --repeat 1 --detach` (no rebuild;
   the build is L3's). Do the `hardening.json` comparison above.
2. **Wait by polling, not one long ssh**: last night's `spe-eval wait` over ssh never returned and the run sat done
   for ~7 h. Use a background loop of `ssh … spe-eval status` every ~5 min that exits when `lock: free`.
3. Destroy/restore the shared denbi-agui-01 as earlier handoffs say (ask if unsure); then the before-t7 handoff's
   step 3: local review round, PR body (L1-L3 tables, both bugs, the rulings), merge, pin, chain to 4/7.
