# 2026-11-08: plan drafted, review round next


Read only this one. Previous: `docs/handoffs/2026-11-08T1845Z-spec-leave-running-chat-merged.md` (the spec's merge).

## Done this session

- **Claimed**: draft PR **#56** (label `plan`), opened by REST since `gh pr create` fails on the org parent
  (`docs/knowledge/gh-pr-create-token.md`; `gh pr ready` too: use the GraphQL mutation there).
- **Plan drafted** in `docs/superpowers/plans/2026-11-08-agui-leave-running-chat/` (`967941d`): README (rulings
  1–5, constraints, slices, Review Focus), three slice files, `progress.md` for slice 1's verdict. Self-review
  done. Indexed in `docs/README.md`; `AGENTS.md` *Current work* points at #56.
- Verified for the plan: CopilotKit **1.84.1** (not 1.79) has `UseAgentThreadScopedProps` and
  `CopilotKitCore.connectAgent({ agent })`; runtime routes are `…/agent/<id>/run|connect|stop`.
  `recorder.test.ts` already has an `isRunning` helper (slice 1 moves it into `sessions.ts`).
  `platform/dev/fake_agent.py` checks `fail` before `slow` (slice 3's `slow-fail` must come first).
  `node_modules` is installed in this worktree's chat dir (git-ignored).

## Next

1. Push is done by this session. **Local review round** on #56 (correctness and methodology reviewer subagents,
   `development-workflow.md`, *Review and merge*, *Local review*); post findings as one comment, address each.
2. Give #56 its title (`Plan: leave a running AG-UI chat (three slices)`) and body (what ran: `methodology sync
   --check`; no tests, docs only), mark ready (GraphQL), merge (squash) once checks pass, clean up, move the pin
   in `biohackathon`, then `methodology next --unit` for slice 1.
3. Waiting on the user, unchanged: the six upstream PRs; canary ladder 0015 and PR #3.
