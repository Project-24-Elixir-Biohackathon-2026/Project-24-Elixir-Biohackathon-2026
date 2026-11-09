# 2026-11-09: slice 3's review round posted, fix wave next

Read only this one. Slice 3 (`impl/agui-leave-running-chat-3-rejoin`, PR #62, ready, not draft) has its four tasks
built ([`2026-11-09T0348Z-slice-3-tasks-done.md`](2026-11-09T0348Z-slice-3-tasks-done.md)) and its one local review
round posted on #62 (comment `issuecomment-6731833386`): 1 Important, 5 Minor; methodology clean. The session that
ran it reached its context budget, so the fix wave is yours. Work in this worktree,
`.claude/worktrees/impl-agui-leave-running-chat-3-rejoin`. The SDD ledger (git-ignored) is
`.superpowers/sdd/slice-3-rejoin/progress.md` in it, with every task's commits and rulings.

## The fix wave (one implementer subagent, then one scoped re-review)

Read #62's review comment for the findings' text. Rulings already taken for it:

1. **Fix** finding 1: at a rejoined run's end (`lib/run-watch.ts`, the `rejoined` branch, `saved` true) fetch
   `GET /api/sessions/{id}` and set the holder's messages when they differ, so "equal to `GET` at the end" holds on
   every path (a branch the journal's tip left is otherwise appended). Unit test in `run-watch.test.ts`; add a
   ruling to [`progress.md`](../progress.md) (a departure from task 2's rule) and the slice file's task 2 text.
2. **Fix** finding 2: don't rejoin again an id whose connect failed until a list shows it not running.
3. **Fix** finding 3: the run end's `LIST_FAILED` error is cleared by a later successful list too
   (`afterListApplied`, bare or titled form), so §6 *Errors* as written holds.
4. **Defer** finding 4 to `BACKLOG.md`, beside the switch-away-mid-connect entry.
5. **Fix** the two one-liners: `run-watch.ts` `noteRunError`'s JSDoc back above it; `page.tsx:47` "1.79.0" → 1.84.1.
   The rest of 5, and 6: no change.

Then `npm test`, `npm run build`, e2e `--scenario rejoin`, `running-marks`, `all`; a scoped re-review (sonnet) over
the fix range; reply on #62 in one comment, one line per finding, naming the fix commits; update the PR body's
*Checks* and rulings; `methodology sync --check`; DCO green.

## Then merge and close the track

Merge squashed (`gh pr merge` may fail on the org parent: `docs/knowledge/gh-pr-create-token.md`; use
`gh api -X PUT repos/thodkatz/elixir-biohackathon-2026-test/pulls/62/merge -f merge_method=squash`), clean up the
worktree and branch (`development-workflow.md`, *Review and merge*, step 7), move the pin in `biohackathon`, write
the after-merge handoff on `main`, and end with `methodology next --end`: this is the track's last unit.

## Rulings made by the session that built the tasks (overrule on #62)

- `waitNotRunning` answers `saved: false` at once when the list lacks the session; the page treats it as gone, never
  as a save failure. Cost if wrong: a deleted running session shows no save error, which is right.
- A rejoined run ends through the holder's existing run watch (`rejoining()`/`rejoined()`), in `progress.md`.
- A left session's save failure is named `“<title>”: …` too, in `progress.md`. Cost if wrong: one prefix.
- Task 4 (docs) was reviewed by the round's methodology focus, not a separate task review. Cost if wrong: a docs
  slip the user catches on the PR.
- #58's two early-output questions had no answer: nothing built; they wait in `BACKLOG.md`'s *Next*.
