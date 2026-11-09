# 2026-11-09: slice 3 tasks done

Slice 3/3 (`impl/agui-leave-running-chat-3-rejoin`, PR #62), the track's last. All four tasks built, each by an
implementer subagent with a task review (task 4's docs reviewed in the PR's methodology focus instead).

- **Task 1** (`42e4b39`): `lib/refresh.ts` (`POLL_MS`, `needsPoll`), `waitNotRunning` in `lib/reconcile.ts`; the page
  fetches the list on focus and on becoming visible, and polls while a running session is not streamed here. A
  runtime connection that drops after the first load no longer re-disables the buttons or re-arms the first-load
  timer. `waitNotRunning` stops at once (`saved: false`) when the list lacks the session: gone, not a save failure.
- **Task 2** (`e25e140`): live rejoin as slice 1's verdict says (`lib/rejoin.ts`: `rejoinedMessages`,
  `nextInProgress`, `rejoinAgent`; `SessionAgent`'s `rejoin`); a rejoined run ends through the holder's run watch
  (`lib/run-watch.ts`, `rejoining()`/`rejoined()`) with `waitNotRunning`. Ruling in [`progress.md`](../progress.md).
- **Task 3** (`d1085cb`): `lib/run-error.ts` (`runErrorText`), `slow-fail` in `fake_agent.py`, e2e `rejoin` and
  `running-marks`; a failed list refresh's error clears once a list loads again (`afterListApplied`).
- **Task 4** (`85c172c`): clarification 28, §12 *Leaving a running chat*, the chat README, `BACKLOG.md` (#58's two
  unanswered questions in *Next*; the switch-away-mid-connect gap), *Current work* line removed.

Checks at the tasks' end: `npm test` 292, `npm run build`, e2e `rejoin` 4 ok, `running-marks` 4 ok, `all` 53 ok
(one run), `methodology sync --check` 0.

#58's early-output questions had no answer when this slice started or ended: nothing built for them; they wait in
`BACKLOG.md`'s *Next*.
