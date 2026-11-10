# Canary hit viewer — progress and rulings

Rulings slices made where they departed from or filled in the plan: *decision, why, cost if wrong*. Status per
slice is the README's slices table; the handoffs say what each session did.

## Slice 1

1. **Archive hits keep their underlying source; Open WebUI export hits are `archive`.** A run's journal and run
   log hits keep `agui-journal` and `agent-runs`, so a hit found live and found again in the archive has one dedup
   key; `openwebui-export.json` has no live twin in slice 1, so its hits are `archive`. *Cost if wrong:* a
   `source` filter on the admin page groups archive hits under the live source; relabel in slice 4.
2. **The early output on the portal is root-only** (`/data-share/canary-hits/early-output/`, root:root, dir 0750,
   files 0640) instead of plan ruling 4's group read: the portal has no `sperange-report` group (`getent` empty,
   2026-11-10). The user reads it with `sudo`. Slice 2's hits root setup re-owns `/data-share/canary-hits`.
   *Cost if wrong:* none.
3. **Receiver hits share one dedup key per canary per generation** (the spec's key, *Sources*): one `delivered`
   hit per canary, not one per request. *Cost if wrong:* repeat deliveries are not listed; slice 3 revisits it if
   the page should show each request (carried into slice 2's Task 7).
4. **`_required` lives once, in `canary_record.py`**, and `handoff.py` imports it (the plan's import list
   duplicated it). *Cost if wrong:* none.
5. **`hits.css` duplicates `report.css`'s tokens** so the static page is self-contained (no external stylesheet).
   *Cost if wrong:* the two drift; slice 3's served page links `report.css` and can drop the copy.
6. **Accepted limits** (review of #77): `test_watcher_agrees_with_metrics` reaches `canary_hits` through
   `metrics`' own `sys.path` insert (correct, and one line to make explicit when next touched); the agent run log's
   `answer` joins a run's messages with no separator, so a token right after another message's last word fails
   the whole-word match there, while the journal, one answer per message, still finds it. *Cost if wrong:* a
   run with a run log and no journal misses that one hit.

## Slice 2

1. **Open WebUI's `chat` columns are unverified**: `denbi-agui-01` runs the AG-UI frontend only (no
   `spe-frontend_open-webui-data` volume), so the check moved into slice 3's Task 9. *Cost if wrong:* the reader
   reports `openwebui: <exception>` until a column rename is fixed.
2. **The on-stop scan runs `scan_archive` over the whole run directory** with the workspace's `seen` set and
   generation, not from the offsets reached: the dedup keys (no `source` in them) drop what polling found. *Cost if
   wrong:* one extra read of a run's archive.
3. **`SshTransport` puts its `-o` options before `vm_argv`'s target**, and runs `sudo -n python3 -` locally when
   `vm_argv` is `[]`. *Cost if wrong:* none.
4. **The watcher caps a reader reply at 32 MiB** (a file with no newline would otherwise be shipped whole); past
   it the poll fails (`unreachable`). Only the participant's own workspace can be stalled this way. *Cost if
   wrong:* such a workspace is watched only by its on-stop archive scan.
5. **A `RecordError` message is logged with the workspace id**: the constraint allows errors, and every
   `RecordError` names a file, key or line, never a value. *Cost if wrong:* a future message carrying a value leaks
   into the log.
6. **The reader returns `line_starts`** (each line's byte offset; Task 5's interface rewritten): restart needs the
   exact offset of an open run's `run_start`, and lines are decoded with `errors="replace"`. *Cost if wrong:* none.
7. **Beyond the plan**: journal titles are kept in the state file (a restart keeps them); a journal file whose name
   is not a UUID is skipped, not a failed poll; the state records `generation_start` (hits-file line count at the
   generation's start) so a restart rebuilds dedup keys from this generation's hits only (review fix). *Cost if
   wrong:* none.
8. **M1 left: `run_starts` stays pinned to an open run's `run_start`** across polls, so after a restart a journal
   is re-read from there (final review). *Cost if wrong:* at most 1 MiB of re-read per poll after a restart; the
   dedup keys keep the hits right.
9. **M3 left: the offsets go to the reader as one argv element** (final review). Past about 2,700 journals they
   exceed the remote `sh -c`'s 128 KiB `MAX_ARG_STRLEN` and the workspace stays `unreachable`; the fix (offsets on
   stdin) is in `BACKLOG.md`. *Cost if wrong:* a workspace with that many sessions is watched only on stop.
10. **M4 left: the generation only salts the dedup keys**; a hit records no generation of its own (final review).
    *Cost if wrong:* a page that wants per-generation views recounts from `generation_start`.
11. **M5 deferred: splitting the transport out of `canary_watch.py`** (`check_offsets`, `run_capped`, the
    transports, ~140 lines, into `canary_transport.py`) waits for slice 3, and only if it edits the file (its
    Task 9 says so). *Cost if wrong:* `canary_watch.py` stays at ~1,080 lines a while longer.
12. **The canary-watch unit's hardening goes to `BACKLOG.md`** (`ProtectSystem=strict` with `ReadWritePaths`;
    never `NoNewPrivileges`, which breaks a local controller's sudo). *Cost if wrong:* the watcher, run as root,
    can write anywhere until it is done.
13. **Discovery is throttled to every 15 s** (`DISCOVER_EVERY`): it re-read every sidecar, `hosts.yml` and
    `canaries.json` over NFS every second. The per-tick scan of the runs directory still marks a workspace stopped
    on the tick its run directory appears. *Cost if wrong:* a stop only discovery can tell (a run directory of the
    same instance name that is another workspace's), a rebuild (new generation) or a new workspace is noticed up to
    15 s later; a rebuild's first polls within that window read the old generation's offsets.
14. **Local review round (#78 comment): findings 1–5 fixed.** A write failure fails the poll (offsets not
    committed) or leaves an archived run unscanned, retried after 60 s; a stop missed across a rebuild is scanned
    with the last generation's keys before their reset; a `hosts.yml` rewritten between discoveries is not polled
    until rediscovered (so ruling 13's last cost no longer holds); the archive scan reads only `<session id>.jsonl`
    journals and logs no file name; a stop without `index.md` is scanned `ARCHIVE_WAIT` (600 s) past its run
    directory's mtime, `stopped` with the note `archive incomplete`. *Cost if wrong:* none beyond 15–19.
15. **A hits-file write failure during a poll shows as `unreachable`** (the failed-poll path and its 60 s
    back-off), not a state of its own. *Cost if wrong:* a portal disk problem reads as the instance being
    unreachable on the pages; the log names `OSError`.
16. **Before a reset, a past generation's run directories are scanned without waiting for `index.md`**: the
    rebuild that followed means their archive is over. *Cost if wrong:* an archive still being written when the
    rebuild lands is scanned in part, and the rest is never scanned.
17. **A run scanned as incomplete is not scanned again** if its `index.md` appears later. *Cost if wrong:* hits
    only in files the archive wrote more than 10 minutes late are missed.
18. **`RecordError` messages are logged by class only**, superseding ruling 5: `read_hosts`'s `cannot read
    <path>` names the output directory, that is the instance's name. Run directory names are no longer logged
    either (they carry it too). *Cost if wrong:* the log names which workspace, not which file or run; the
    operator reads the files.
19. **The fixture run's journal is renamed to a session id** (`aaaaaaaa-…-444444444444.jsonl`) so the archive
    scan's session-id filter reads it. *Cost if wrong:* none.

## Slice 3

20. **Open WebUI's `chat` columns were checked against the v0.13.0 source** (the pinned
    `spe_frontend_webui_image`), not a live instance: neither instance runs Open WebUI, and rebuilding one for a
    column check is heavy. `chat`'s JSON history stays the complete store (`chat_message` is a dual write); a few
    intermediate writes skip `updated_at` and are seen at the next write or on the archive scan. *Cost if wrong:*
    a patched image's columns differ, and the reader reports `openwebui` unreadable, as designed.
21. **`participant_body`'s `status` `{}` means no status file; `None` means the archived early output** (the
    header reads "not watched yet" and "archived run"). *Cost if wrong:* a caller passing `None` for a live
    workspace shows "archived run"; only the service and `--html` call it.
22. **A status event is also sent when a stream opens**, not only when the status file changes, so a page
    reopened after a stop shows the current state at once. *Cost if wrong:* one extra event per connection.
23. **`terraform fmt` was not run on `main.tf`**: neither terraform nor opentofu is on the development machine,
    and its nix store is read-only. The new `coder_app` copies the "Report" app's layout. *Cost if wrong:* a
    formatting diff the next `fmt` makes; Coder parses the file either way.
24. **The frontend label ("AG-UI", "Open WebUI") sits in the expanded hit, not its collapsed line**, as in the
    spec's mockup (its second line), and "Group by run" groups the loud hits only; "also seen" stays one
    collapsed block. *Cost if wrong:* a participant opens a hit to see its frontend.
25. **A logged-out visitor to the participant page returns to it after login** (`redirect=/reports/<id>/hits`),
    not to the report as the plan's task text had it (`/reports/<id>`), which the final review found sent them to
    the wrong page. *Cost if wrong:* none; `hits.json` and the stream still answer 401.
26. **A hit that arrives live goes to the top of the list**, in the order the watcher detected it, while a reload
    sorts by `at` (else `detected`). An archive-scan hit with an older `at` can therefore move down on a reload.
    Placing it by `at` live would mean re-sorting in the script against the one-renderer rule (ruling 8), for a
    cosmetic difference (PR #79's review, finding 3). *Cost if wrong:* a participant sees a hit change place after a
    reload.
