# 2026-11-11: experiments slice 5

**Track:** experiments. **Spec:** `docs/specs/2026-11-10-experiments-design/` (README: decisions 1–23; slices in
`inputs-for-plan.md`). No plan stage: each slice is one PR, `impl/experiments-<n>-<slug>`, titled `… (n/7)`, its
task list in the PR body, worked with `superpowers:subagent-driven-development`.
**Previous:** slice 4, **the viewer and apps** (fork PR #92):
- `evals-view` is two containers, both in compose profile `evals` on network `evals`:
  - nginx `1.29-alpine`, the read-only proxy on `127.0.0.1:8200`. It forwards the raw request URI and refuses
    every non-GET except socket.io's.
  - `evals-promptfoo`: `promptfoo view` 0.125.1, sharing that netns, with no key in its environment.
- The `spe_eval` role gates it on `spe_experiments` and asserts uid 1000.
- The **Evaluations** Coder app is on `spe-experiments` only.
- `test_evals_view.py` checks the proxy's rules against 0.125.1's own routes (clarification 3).
- Decisions 14–15 checked on a portal-less de.NBI build (#92's body has the results); 16 only statically, its live
  check in `BACKLOG.md`.

## Next

Slice 5, **eval runs apart in canary hits** (decision 12). Branch `impl/experiments-5-canary-source`. Scope:
`inputs-for-plan.md` row 5 and spec `03-evaluation-in-workspace.md`, *Canary hits*. It covers four things:
- the promptfoo provider marks each run it starts (AG-UI `forwardedProps`);
- the agent writes `source: eval` on that run's log lines;
- a receiver hit inside a window from `~/spe-eval/windows.jsonl` (written by slice 3's `spe-eval`) is an eval hit;
- the watcher keeps each hit's source, and the hits pages show eval hits under their own heading, out of the chat
  hits' counts.

The acceptance checks are in README decision 12. The canary hit viewer's code is `platform/report/canary_record.py`
and the template's Canary hits app. Slice 5 needs de.NBI (standing OK: one instance at a time, `qwen3.8-27b`).

## Carried from slice 4

- **de.NBI DNS:** agent-service-1's resolver still times out on `*.ubuntu.com`, so `create.yml` stops at
  `base : Install packages`. The `/etc/hosts` pin in `docs/knowledge/denbi-apt-dns.md` gets past it. Remove the pin
  after the build.
- **Building an arm without the portal:** `docs/knowledge/experiment-arm-build-without-portal.md`.
  - Render the experiment's vars, drop `spe_instance`/`spe_seed`, and run `create.yml` from the worktree with the
    main checkout's `instances/denbi.yml`, `spe_output_root` and `spe_repo_ref=<branch>`.
  - Prune the build cache first (`denbi-disk-full.md`).
  - Restore the VM from main's `instances/denbi.yml` afterwards.
- **Results already on the VM:** the viewer's database `~/spe-eval/promptfoo` on denbi-agui-01 holds 14 ladder
  evals from slice 3. On an experiments build, `curl 127.0.0.1:8200/api/results` lists them without a new run.
- **Deferred:** the viewer's egress (some GET routes call out) is in `BACKLOG.md`, *Unscheduled*. Minors 5, 8, 9
  and 11–14 from #92's ledger were judged not worth a change (minor 4 was fixed, `d86b804`). #92's body lists them.
