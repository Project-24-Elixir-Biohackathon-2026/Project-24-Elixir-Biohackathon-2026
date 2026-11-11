# 2026-11-11: experiments slice 4 denbi check


**Unit:** slice 4/7, the viewer and apps, branch `impl/experiments-4-viewer`, draft **PR #92**. Context for the
unit: `docs/handoffs/2026-11-11T1012Z-experiments-slice-4.md`. This is a mid-unit handoff written at the context
budget. Previous: `2026-11-11T1134Z-experiments-slice-4-task1-rereview.md`.

**How the work runs:** `superpowers:subagent-driven-development`. The workspace is git-ignored, in this worktree:
`.superpowers/sdd/slice4-plan/`.
- `plan.md` is the task list and PR #92's body.
- `progress.md` is the ledger. Read it first; its `Ruling:` lines go into the PR body.
- The scripts now write their briefs and diffs to `.superpowers/sdd/plan/`. It is the same plan.

## Where it stands

- **Tasks 1–3 are complete and reviewed:**
  - Task 2 (wiring): `0d8bf1d`, `294ab07`.
  - Task 3 (the Evaluations app, the spec, clarification 3): `c592628`, `4145b29`.
- **The final whole-branch review is done (opus).** It found **C1, request smuggling**: `proxy_pass …$uri` passed
  a decoded `%0D%0A` upstream, so one GET could deliver `POST /api/eval/job`.
  - The fix wave is `aeabd1c` (raw forwarding plus an exact `$request_uri` match on `/socket.io/`, a recording-stub
    test, and the docs), `70a3656` and `d86b804` (a uid-1000 assert in role `spe_eval`).
  - The scoped re-review addressed every finding (45 raw-socket probes). Everything is pushed; HEAD is `d86b804`.
- **Triage of the ledger's deferred minors:** 7, 10 and 15 are fixed. 2, 4, 5, 8, 9, 11, 12, 13 and 14 are left.
  Of those, **2** (some promptfoo GET routes make outbound calls; is egress control needed?) goes to `BACKLOG.md`
  in this unit's PR.
- **The de.NBI check failed outside the code.** `create.yml` stopped at `base : Install packages` because
  agent-service-1 cannot resolve `archive.ubuntu.com` (`docs/knowledge/denbi-apt-dns.md`, written this session).
  The run changed nothing (`changed=0`), and the VM is still on main's `instances/denbi.yml` stack.

## Next

1. **Check DNS** (`denbi-apt-dns.md`). Once it answers, rebuild from this worktree's `platform/ansible`:
   ```bash
   set -a; . ~/.config/spe-dev/llm.env; set +a
   ansible-playbook playbooks/create.yml -e @<main>/platform/ansible/instances/denbi.yml \
     -e @<worktree>/.superpowers/sdd/slice4-plan/ladder-l1.yml -e spe_output_root=<main>/platform/ansible/output \
     -e spe_repo_ref=impl/experiments-4-viewer </dev/null
   ```
   The `ladder-l1.yml` is already rendered, with `spe_instance`/`spe_seed` dropped
   (`experiment-arm-build-without-portal.md`). Prune the build cache first (`denbi-disk-full.md`).
2. **Acceptance on the VM** (decisions 14–16):
   - `curl 127.0.0.1:8200/api/results` lists evals.
   - From the sandbox container, a request to the host on port 8200 fails.
   - `POST /api/eval/job` and `POST /api/eval/replay` on :8200 get 403.
   - `docker exec <evals-promptfoo> env` has no `*_KEY`.
   - A smuggling probe (`GET /a%20HTTP/1.1%0D%0A…POST%20/api/eval/job…`) creates no eval.
   - The UI loads over the socket.io polling path.

   **The early output** (an eval visible in the viewer) needs one `spe-eval run`. It is de.NBI qwen, but this
   arm's agent is Anthropic Haiku from `denbi.yml`. Either run a controls-only suite, or check whether the qwen key
   works (`denbi-llm-key.md`); never a paid suite.
3. **Restore the VM** from the main checkout's `instances/denbi.yml` (`denbi-anthropic-haiku.md`).
4. **Then:**
   - the local review round (correctness and methodology focuses, one comment on #92);
   - fill #92's body: the task list, the rulings from the ledger, the acceptance results, and the checks that ran;
   - update the `BACKLOG.md` item (minor 2) and the *Current work* line;
   - `methodology sync --check` and DCO;
   - merge; clean up; move the pin in `biohackathon`; then the slice 5 handoff.
