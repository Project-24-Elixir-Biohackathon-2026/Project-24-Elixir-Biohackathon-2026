# 2026-11-04: merge upstream's both-frontends change, then resume the Coder e2e test

**Unit: `change/merge-upstream-2026-11-04-both-frontends`, PR #39** (draft), worktree
`.claude/worktrees/change-merge-upstream-2026-11-04-both-frontends`. Mid-unit handoff at the context budget.

**Why this unit.** Started as `change/agui-coder-e2e-2026-11-04` (#38, draft, claim only, nothing else on it).
Upstream had moved on after #35: `d2a6232` (kraatz #16) runs both chat frontends on every instance against one
sandbox (`spe_frontends`, no portal `frontend` parameter), plus `bc0ba90` (kraatz #15). The portal builds from
upstream, so the e2e test needs our `main` on that layout first; the user agreed (2026-11-04: merge, not
rebase; the kraatz PR is then cut from current `upstream/main` with no conflicts).

**Done (commit `36bb78c`, pushed).** The merge with every conflict resolved; the resolutions are in its message
and spec clarification 23 (the AG-UI part of a run is archived in `<run>/agui/`). `pytest platform/dev/tests`
93 passed (two new tests for the shared run directory), `validate.py` OK, `ansible-playbook --syntax-check` on
create/archive/destroy OK. The knowledge note for this session's push failure is committed alongside this handoff.

**Next, in this unit:**
1. Run the remaining test commands of *Running things* for the areas the merge touched: the agent's pytest, the
   promptfoo pytest, the chat UI `npm run build` and `npm test` (no paid calls).
2. Check `platform/dev/tests/test_archive_export.py`: it still passes `-e spe_frontend=agui` (works through the
   compatibility default); decide whether it should pass `spe_frontends=[agui]` and add a both-frontends case.
3. Not yet reviewed: `platform/ansible/roles/run_archive/tasks/export.yml` with both frontends on (Open WebUI's
   export block runs first, then AG-UI's final barrier stops `chat-ui` and `agent`). The rest of the spec's
   `spe_frontend` mentions are history (plan 2026-10-15, `07-ansible.md:136` is the dev inventory's `frontend:`).
4. PR body (what ran; DCO red only on upstream's commits, as for #35), mark ready, local review round
   (correctness + methodology), address findings, merge **with a merge commit**
   (`docs/guides/contributing-upstream.md`, *Merge upstream into our `main`*), clean up, move the pin in
   `biohackathon`.
5. Then resume #38 from `docs/handoffs/2026-11-04T0845Z-agui-coder-e2e-start.md`, with these facts:
   - `theo/theo-workspace` is **stopped** (archived). No workspace exists; `denbi-agui-01` is idle, left running.
   - `coder create theo/agui-e2e --template spe-ga4gh-baseline --preset "All data" -y` failed on an interactive
     prompt (`prepare build: EOF`): add `--parameter seed=0`.
   - After the merge, `spe-apply all` on our `main` deploys both frontends, as the portal does.
   - Existing instance scenarios to reuse: `platform/dev/e2e/sessions.py` (`stop`, `two-turn`, `live-run`,
     `compaction-live`; they read journals with local `docker compose`, so run them through a workspace tunnel
     or adapt `InstanceRun._exec` to `coder ssh`).

**Pushes fail on and off** (GitHub side, 2026-11-04): retry; `docs/knowledge/github-ssh-intermittent-denied.md`.
