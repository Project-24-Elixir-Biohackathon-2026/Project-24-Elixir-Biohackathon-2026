# 2026-11-08: spec leave running chat draft


Read only this one. Previous on `main`: `2026-11-08T1706Z-upstream-port-title-on-send.md` (its port is done, see
below). **Work in the worktree `.claude/worktrees/spec-agui-leave-running-chat`**, branch
`spec/agui-leave-running-chat`, draft PR #55 (claimed by hand: `methodology worktree` misplaced it,
`docs/knowledge/methodology-worktree-submodule.md`; `gh pr ...` needs the REST forms in
`docs/knowledge/gh-pr-create-token.md`). The user is in the session: this is the spec stage they attend.

## Done this session

- **Upstream port of #52 finished**: `contrib/agui-title-on-send` got `1651bd8` (dropped "the fork's PR #52" from
  clarification 26), pushed; `npm test` 250/250 and build ok on it. PR text is fork issue #53 (ledger line
  `cd38eaf` already on `main`); my duplicate #54 closed. The user opens the six upstream PRs (issues #42, #45, #47,
  #49, #51, #53) and said they will do so after this work.
- **Brainstorm, with the user's choices:** leave a running chat (old `BACKLOG.md` item, asked 2026-11-04).
  On return to a running session: **the live stream** (A), not the saved part filled in later. Build approach:
  **one private CopilotKit agent per session kept mounted in the page** (1), not one shared agent that
  rejoins on every switch (2).
- **Spec draft committed `da57425`, pushed** (living spec `docs/specs/2026-10-15-agui-frontend-design/`):
  clarification 27; §6 *A session's agent*, *Opening a session*, *Leaving a running chat*, *Refresh*, *Errors*,
  *Layout* (running spinner), *Session API* (`running` in list and `GET` one); decision 26 rewritten, 40–44 new;
  README *Early output* (rejoin check first, then a screenshot); `inputs-for-plan.md` and `out-of-scope.md`
  sections; the backlog item removed; *Current work* line in `AGENTS.md`.
- What CopilotKit 1.79 was read to do (in `node_modules`): `useAgent({agentId, runtimeAgentId, threadId})` gives a
  private `ProxiedCopilotRuntimeAgent`, unregistered on unmount (no abort; the object is just lost);
  `InMemoryAgentRunner.connect` replays the thread's in-memory past runs (`compactEvents`) then streams the live
  one; `Shared.running` is keyed `runKey(threadId, runId)`.

## Next

1. **Builder check** (brainstorming skill, `builder-check-prompt.md` in its directory): a fresh subagent reads
   clarification 27, §6 *The sidebar* and *Session API*, decisions 26 and 40–44 and `inputs-for-plan.md`'s new
   section. Sort its questions: answer in the spec, settle minor ones as your call (mark them), bring the
   user's in one message.
2. Hand the spec to the user with the calls made in it (each my call, not theirs): spinner at the row's end as
   the running mark; Delete disabled for a running session; poll every 2 s only while a run the page doesn't
   stream is listed; a background session's run error in the error bar prefixed with its title; a finished
   background agent dropped (next open reads the journal); no limit on runs at once; no unread mark (out of scope,
   decided at the screenshot).
3. Then PR #55's title and body, ready (GraphQL mutation from the token note), the local review round
   (`development-workflow.md`, *Review and merge*), and the user's approval (`methodology gate approve` at their
   word). On approval change README's "proposed 2026-11-08 in the fork's PR #55" to approved; merge; worktree
   cleanup; pin in `biohackathon`; then the plan unit.
