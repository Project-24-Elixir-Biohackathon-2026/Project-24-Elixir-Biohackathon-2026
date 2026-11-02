# 2026-11-03: AG-UI chat minors, hop 1

Written on `change/agui-chat-minors` (draft PR #14), at the context budget, mid-unit. The user's instruction
and the order of the work after this unit are in `2026-11-02T2351Z-agui-chat-minors-next.md` (still current:
no upstream PRs, Haiku runs approved, merge fork PRs yourself, then the compaction spec).

## Done (pushed on the branch)

- `08aff49`: store fsyncs the directory after a write; list entries gain `last_run_at` and `showsRun`
  reconciles by it (spec clarification 6). Two items out of `BACKLOG.md`.
- `07fd3a7`: recorder keys agent requests by `[threadId, runId]` (test holds both fetches behind a gate;
  fails on the old key); `check-built-server.mjs` per-request bound and 180 s deadline (SIGTERM, see
  `docs/knowledge/uv-sigkill-orphan.md`). Two items out.
- Verified: `npm test` 96 pass, `npm run build`, `node scripts/check-built-server.mjs` all pass.

## Next, in this unit (triaged; cheap and safe)

1. `app/sidebar.tsx` and `app/chat-header.tsx` document Escape listeners: return early on `e.defaultPrevented`.
2. `app/globals.css`: under `@media (hover: none)` show `.spe-row-menu` (opacity 1) and give `.spe-row-open`
   its `padding-right: 32px`; the renaming rules (two classes) keep it hidden while renaming.
3. Keyboard minors: Tab out of a rename saves it (`app/row-menu.tsx` `RenameInput`: on Tab, without
   `preventDefault`, call a new `onLeave` via `setTimeout(…, 0)` so focus moves first; sidebar passes `end()`,
   header `end()`); `app/delete-dialog.tsx` Escape on `document`, not only the dialog's `onKeyDown`.
   Leave "click outside the menu doesn't refocus `⋯`" in the backlog: refocusing would steal the click's focus.
4. `app/page.tsx`: if `isReady` is still false after ~15 s, `setError("The agent runtime is unreachable; reload
   the page.")`; clear that message when `isReady` turns true.
5. `write_agui_run.py`: `shutil.rmtree(<run>/chats)` before rendering (never the source dir); skip a tool
   message whose `toolCallId` is any assistant's call id (collect all call ids first), not only those already
   shown. Tests in `platform/dev/tests/test_write_agui_run.py`.
6. `platform/dev/e2e/sessions.py`: a scenario (part of `all`) that `DELETE`s the open session via the API,
   sends a message, expects "this session was deleted" in `.spe-error` and, after 3.5 s, no
   "this session could not be saved".
7. Stay in `BACKLOG.md`, line unchanged: `list()` parse cost, recorder body parse/clone cost, the
   stop-before-POST window, and the click-outside refocus (add the reason above to its line).
8. Run `npm test`, `npm run build`, `check-built-server.mjs`, `uv run --with pytest pytest platform/dev/tests -q`,
   `python3 platform/dev/e2e/sessions.py`; then mark #14 ready, local review round (correctness + methodology),
   merge, clean up, pin in `biohackathon`, and hand off the compaction spec.
