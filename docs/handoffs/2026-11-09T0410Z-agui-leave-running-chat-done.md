# 2026-11-09: AG-UI leave a running chat: track done

Slice 3/3 (`impl/agui-leave-running-chat-3-rejoin`, #62) merged squashed as `86cd332`, the track's last unit; its
own handoffs are in `docs/superpowers/plans/2026-11-08-agui-leave-running-chat/handoffs/`.

- Review round: 1 Important, 5 Minor, methodology clean (#62 `issuecomment-6731833386`). Findings 1–3 and 5's
  one-liners fixed, finding 4 deferred to `BACKLOG.md`; scoped re-review (sonnet): no findings; reply
  `issuecomment-6732011096`. Checks at the merge: `npm test` 298, `npm run build`, e2e `rejoin`, `running-marks`,
  `all` (55) ok, `methodology sync --check` 0, DCO green.
- New ruling on the PR and in `progress.md`: a rejoined run's end replaces the chat with `GET /api/sessions/{id}`
  when they differ; a failed `GET` leaves the replay, with no error bar.
- Left for later: #58's two early-output questions wait in `BACKLOG.md`'s *Next*. Porting the track upstream is
  not scheduled.
