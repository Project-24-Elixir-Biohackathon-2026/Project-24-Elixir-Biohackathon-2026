# 2026-11-09: slice 2 tasks done


Mid-unit handoff (context budget). Read only this one. Previous: `2026-11-09T0052Z-after-merge-slice-1.md`.
Branch `impl/agui-leave-running-chat-2-agents`, draft PR #58, worktree
`/workspace/biohackathon/elixir-biohackathon-2026-test/.claude/worktrees/impl-agui-leave-running-chat-2-agents`.

## Where it stands

- All four tasks of [`slice-2-agents.md`](../slice-2-agents.md) are built, each reviewed by a task reviewer and
  clean after at most one fix round (`3c3796f..de727a4`):
  - Task 1 `lib/live-sessions.ts`; task 2 `app/session-agent.tsx`, the page, `lib/list-order.ts` (fix: lists applied
    in the order they started); task 3 the running mark and Delete rule; task 4 `check_leave_running` in
    `platform/dev/e2e/sessions.py`, screenshots in `evidence/slice-2/`, and an app fix (`715305f`, `de727a4`): a chat
    reopened mid-run froze, because `@ag-ui/client` copies its subscribers at a run's start; the holder now
    forwards message changes and the page redraws the open chat while it was mounted mid-run.
- Checks run (task 4's last round): `npm test` 265 pass, `npm run build` OK, e2e `leave-running` 7 ok, `stop` OK
  (also `--save-delay-ms 1500`), `all` 47 ok. **Not run:** the instance scenarios `slow-loop`, `two-turn`,
  `compaction-live`, `live-run` (changed to `wait_run`; need `--url`): say so in the PR body.
- Rulings are in [`progress.md`](../progress.md) (*Rulings while building*, the six slice-2 lines) except the one
  from task 4, still to add there: **the mid-run freeze is fixed in this slice** (decision 41 is slice 2's), narrowed
  to redraw only while the open chat was mounted mid-run; *cost if wrong:* a missed case freezes again, and
  `leave-running` step 3 catches it.
- The SDD ledger (git-ignored) is `.superpowers/sdd/slice-2-agents/progress.md` in the worktree: deferred Minors per
  task, for the final review to triage.

## Next

1. Add task 4's ruling to `progress.md`; mark slice 2 in the plan README's slices table and `AGENTS.md` *Current
   work* as the PR's state needs; commit.
2. Fill #58's title (`AG-UI leave a running chat: an agent per session, switching, running mark (2/3)`) and body
   (what, checks run and not run, rulings, the re-render cost while a reopened chat streams), mark it ready (GraphQL
   mutation: `docs/knowledge/gh-pr-create-token.md`).
3. Review round, local: correctness (opus, the whole branch against slice 2's acceptance; point it at the ledger's
   deferred Minors) and methodology. One comment on #58, one fix wave, one scoped re-review, reply.
4. After the PR opens, one comment with the two screenshots, no gate: "Does a reply that finished while you were
   away need a mark of its own? (yes/no)" and "Should the open row show its running spinner while it runs (today
   `⋯` takes its place, §6 *Layout*)? (yes/no)".
5. Merge (checks in `AGENTS.md` *Overrides*), clean up, after-merge handoff, `methodology next --unit
   impl/agui-leave-running-chat-3-rejoin <handoff>`.

## Gotchas met

- The chain started this unit on slice 1's merged branch; claimed slice 2's instead (ruling in `progress.md`).
  The stray worktree `.git/modules/elixir-biohackathon-2026-test/.claude/worktrees/impl-agui-leave-running-chat-1-rejoin-check`
  (local branch only; origin's was deleted) is left for `methodology worktree --prune` or `git worktree remove`.
- `gh pr create`/`ready` fail on the organization's token rule: REST and GraphQL forms in
  `docs/knowledge/gh-pr-create-token.md` work.
