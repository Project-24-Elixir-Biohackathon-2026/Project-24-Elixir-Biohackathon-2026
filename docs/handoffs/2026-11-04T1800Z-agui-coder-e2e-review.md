# 2026-11-04: AG-UI via Coder, step 2, review fixes (context budget)

**Unit: `change/agui-coder-e2e-2026-11-04`, PR #38 (ready)**, worktree `.claude/worktrees/change-agui-coder-e2e-2026-11-04`.
Earlier handoff: `2026-11-04T1110Z-agui-coder-e2e-mid.md` (its open FAIL is resolved: a virtualized chat, `0aa4475`).
Named `T1800Z` so `ls docs/handoffs | tail -1` picks it (other units' handoffs carry later names than their times).

**State.**
- Step 2 passed: run 4 10/10; live archive journals and run log byte-identical, chats agree run for run.
  Results in PR #38's body; `BACKLOG.md` marks (2) done.
- Local review round posted: PR #38 comment `6629314016`, findings 1-17. Driver fixes (1, 4-7, 10) are in `d541664`,
  not yet re-run against the workspace (optional: a fresh full run costs a few dozen calls, already approved).
- Workspace `theo/agui-e2e` still **running**, `context_window_tokens: 48000` (test-only). The workspace's
  `~/sperange/platform/ansible/output/cw-theo-agui-e2e/hosts.yml` is a fake hand-off from the live archive: remove it.

**Next, in this unit:**
1. Findings 2, 3, 13, 16: **drop** the *Unscheduled* compaction-estimate item in `BACKLOG.md` and the note's bullet
   "A run can go in past the trigger" (`docs/knowledge/agui-coder-e2e-check.md`). Its premise was wrong: run
   `886e5629` ran at the 48000 window (agent restarted 10:51:31Z, run 10:53Z) and sent 36.3k tokens, below the
   38.4k trigger, so not compacting was right.
2. Finding 8: in the PR body's compaction row, say A's 1 manual + 4 automatic compactions come from run 3's run log,
   not from a driver check (run 4 skipped A).
3. Finding 9: the note's live-archive command gets `mkdir -p output/cw-<user>-<ws> &&`, says the name is lowercased,
   and ends with `rm` of the fake `hosts.yml`.
4. Finding 14: cut step (2) in `BACKLOG.md`'s *AG-UI via Coder* item to its done line (#38), leaving step (3) and
   the pass criteria.
5. Finding 15: add a *Current work* line to `AGENTS.md`: "AG-UI via Coder: (1)-(2) done (#36, #38); next: step 3
   (final archive via `create.yml`/`destroy.yml` from our checkout); handoff: <step-3 handoff path>".
6. Finding 17: add to `docs/knowledge/README.md:28` "`archive.yml` in a workspace: `hosts.yml missing`, write a local
   hand-off".
7. Finding 11: write the step-3 handoff (named to sort last), with: stop `theo/agui-e2e` first (one instance at a time),
   `create.yml`/`destroy.yml` from the main checkout with both frontends, `spe_repo_url` set to our fork, branch
   pushed; the pass criteria in `BACKLOG.md`; the note `docs/knowledge/agui-coder-e2e-check.md`.
8. Reply on PR #38 with one comment, one line per finding with its commit; then merge (squash, `--signoff` not
   needed for squash via gh; checks: DCO, `sync-agents.py --check`), clean up the worktree, move the pin in
   `biohackathon`, and start step 3 with `next-session.sh --next`.
