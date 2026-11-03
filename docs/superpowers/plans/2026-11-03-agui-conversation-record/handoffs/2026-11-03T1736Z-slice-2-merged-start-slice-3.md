# 2026-11-03: slice 2/4 merged, start slice 3/4, `impl/agui-conversation-record-3-route`

Slice 2 (#23) merged the archive's two halves, still unwired: `lib/export.ts` (a rebuilt session as an Open WebUI
chat, a journals directory as the bundle), `scripts/export-journals.ts` in the `chat-ui` image, and
`write_run.py` rendering AG-UI bundles (status, ignored block, `## Compacted`, the AG-UI `index.md` columns) with
the Open WebUI output pinned byte for byte by a golden tree. Spec clarification 8 folds what was built into §14.
`tasks/export.yml` and `tasks/write.yml` still use `write_agui_run.py`: slice 3 switches them. `npm test`: 169
tests; `pytest platform/dev/tests`: 89.

## Rulings this slice took

- **The exporter never overwrites a message id** (pre-flight scan; the task review found the first fix could
  still collide). *Decision:* a client message whose id is already exported, or starts with `spe-run-` or
  `spe-msg-`, is exported as a fresh `spe-msg-<n>` (tried until free) carrying `spe_original_id`; `messages` is
  a null-prototype object, so an id `__proto__` is a key like any other (final review). *Why:* a participant
  could make a run's message its own parent, and the branch walks in the exporter and `write_run.py` never
  ended: the archive, and with it `destroy.yml`, hung. *Cost if wrong:* a renamed id and one extra field in
  rare bundles. `interfaces.md`, §14 and clarification 8 say it.
- **`write_run.py`'s AG-UI branch walk stops at a message it has seen.** *Decision:* defence in depth on top of
  the remap, in `agui_branch` only (`active_branch`, the Open WebUI walk, is unchanged). *Why:* a hand-edited or
  forged bundle must not hang the archive. *Cost if wrong:* none known.
- **The compaction marker prefix is imported** from `lib/compaction.ts` (`MARKER_PREFIX`), not copied.
- **The Dockerfile's exporter step fails the build** if `npm query` fails or `@ag-ui/client` or `rxjs` is
  missing (`pipefail` scoped to that `RUN`, then `test -d`). *Why:* a silent empty copy would ship an exporter
  only slice 3's archive finds broken.
- **`write_run.py` carries copies of `one_line`, `pretty_args`, `count_lines` and `when`** from
  `write_agui_run.py`. *Why:* slice 3 deletes `write_agui_run.py`, so the copy lives one slice; delete them
  there, not here. *Cost if wrong:* a review finding pointing at slice 3.
- **Clarification 8 covers more than the plan's step 7**: `spe_run` carries `error` (§14 and the README's
  *Global Constraints*), a run's `content` leaves out a compaction marker's summary, an anchor folded into a
  run's message is that message as parent, §14 *Write* names the AG-UI `index.md` columns and lists
  `openwebui-export.json`.
- Deferred, in `BACKLOG.md` (*Unscheduled*, "from #23's review"): `owner` keyed by the original id and
  `new_messages` vs `added` in the exporter; the missing-directory test checks only the exit code; a refused
  run's status line repeats its reason; `when()` raises on a non-numeric timestamp. The round's comment on #23
  lists every finding.

## For slice 3's `tasks/export.yml`

- **The exporter's command**, in the `chat-ui` image (the image grew 441 MB → 485 MB):

      docker run --rm --user 1000:1000 --entrypoint node \
        -v <journals dir>:/in:ro -v <run dir>:/out \
        <chat-ui image> scripts/export-journals.ts /in /out/openwebui-export.json <live|final>

  It prints `N sessions (H hidden, D deleted), <mode> archive`; a wrong mode or argument count exits 2, an error
  (e.g. a missing journals directory) exits 1 with its message on stderr. A torn line logs
  `journal: line N skipped (…)` and is counted, not fatal.
- **`/out` must be writable by uid 1000** (the image's `node` user), or the run needs `--user` matching the
  directory's owner. The check here ran with `--user 1000:1000` (the VM user's uid).
- **`write_run.py` expects `agui-journals/` and `agent-runs.jsonl` in the run directory** before it runs, beside
  the bundle; it renders `chats/`, the notes and `index.md` from them.

## Next

Slice 3, [`slice-3-route.md`](../slice-3-route.md): start at its claim step, then its tasks with
`superpowers:subagent-driven-development`. Names come from [`interfaces.md`](../interfaces.md).
