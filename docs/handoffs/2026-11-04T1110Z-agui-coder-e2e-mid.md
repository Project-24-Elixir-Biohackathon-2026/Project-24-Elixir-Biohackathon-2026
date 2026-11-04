# 2026-11-04: AG-UI via Coder, step 2, mid-unit (context budget)

**Unit: `change/agui-coder-e2e-2026-11-04`, draft PR #38**, worktree `.claude/worktrees/change-agui-coder-e2e-2026-11-04`.
Checklist and pass criteria: `BACKLOG.md` *Next*, *AG-UI via Coder*. Earlier handoff: `2026-11-04T0845Z-agui-coder-e2e-start.md`.
#39 (both frontends) merged, then this branch merged `main`.

**State.**
- Workspace **`theo/agui-e2e`** (main template `spe-ga4gh-baseline` at `d2a6232`, preset "All data", `seed=0`,
  both frontends) is running: the only instance; `theo/theo-workspace` stopped, `denbi-agui-01` untouched.
  `~/sperange` is at our `main` `62f8458` (detached), `spe-apply all` ok=100 failed=0.
- **Test-only change:** `~/spe-frontend/agent.yaml` `context_window_tokens: 48000` (real: 262144), agent
  restarted. `spe-apply all` restores it. Why 48000: `docs/knowledge/agui-coder-e2e-check.md`.
- Driver `docs/knowledge/agui-coder-e2e-check.py` (committed with its note). The tunnel was
  `coder port-forward theo/agui-e2e --tcp 13001:3000` (it dies with the session: start it again; :13000 is
  another session's tunnel, leave it).

**Run 3 results** (sessions A `9901acbf-97b8-43da-9f57-96913a68d51a`, B `e059b3d4-eedb-4778-a9d0-4ecb8ba4c437`;
C and D are `8b5ccd4e-4c5e-4726-b3ac-0bec5f09c6e5` and `e27de82d-3b28-41b0-888c-122ca4c85077`, the one with
`deleted_at` is D):
- PASS: two sessions at once; tab B opens A mid-run; stop then send at once (no "Thread already running",
  journal `completed, cancelled, completed`); new chat; rename (journal title); delete (row gone, `deleted_at`).
- PASS (read from the run log, the driver had crashed): A has 1 manual + 4 threshold compactions over turns
  1-9, every run `completed`, no error.
- **Open FAIL to investigate first:** tab B, after opening A mid-run, then `goto ?session=A` after A's run ended,
  showed **0 user messages** (`.copilotKitUserMessage`); the journal has the run `completed`, and a fresh
  browser on the same URL shows 1 user message and 2 tool groups. Reproduce alone (same context, tab B on
  A mid-run, then the same URL again after the end); a chat bug goes to its own PR before this step completes.
- Unchecked: run `886e5629` in A (after the stop) went in at 21.4k input tokens with a 24k window (trigger
  19.2k) without compacting: does the threshold only look at history before the run? Read the agent's code.

**Next, in this unit:**
1. Investigate the FAIL above.
2. `--resume A,B,C,D --turns 16` (skips 1-3 and A): C's `/compact` with a focus and its compactions, then step
   5 (reopen each session, chat vs journal), `journals.json`.
3. Agent and `chat-ui` logs over the run: no error.
4. Live archive: run `archive.yml` in the workspace (`platform/coder/README.md` *Save a run without stopping*;
   in a workspace try `cd ~/sperange/platform/ansible && ansible-playbook playbooks/archive.yml -e @instances/local.yml`)
   and compare its `agui/` journals with the containers', run for run. The final archive is step (3)
   (`create.yml`/`destroy.yml` from our checkout): the portal's stop archives from upstream's checkout, not readable here.
5. Write the results into PR #38 and `BACKLOG.md` (step 2 done or not), then the step-3 plan; stop the workspace
   before step 3's `create.yml` (one instance at a time).
