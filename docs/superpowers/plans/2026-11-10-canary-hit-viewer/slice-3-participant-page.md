# Slice 3/5: the participant page, live

Branch `impl/canary-hit-viewer-3-participant-page`. Spec: decisions 6, 8, 10, 11 (*Participant page*, *Security*,
*Watcher*'s latency); plan rulings 6, 7, 8. Global constraints: [README](README.md#global-constraints). Plan a
mid-slice handoff after Task 10 if the context budget is past half.

What the service has (read against `cd6a555`): `Store.meta(wid)` reads the report sidecar (`owner`, `workspace`,
`instance`); `Handler.user()` asks Coder for the viewer (`Coder.me`), `is_admin(user)` is the `owner` role;
`Handler.route()` splits `/reports/<rest>`; `Handler.send` sets `Content-Length` and the CSP (`script-src 'self'`:
no inline script, page scripts are `static/*.js`); `page(title, body, user)` wraps a body;
`Handler.log_message` logs address, method and path only; `make_server(listen, reports_dir, coder_url)`; the unit
runs `python3 -I`, so the script's directory is **not** on `sys.path` (an import of a sibling module needs
`sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))` first). Tests in `tests/test_report.py` start
the service and a `FakeCoder` on port 0 and call it with `urllib`.

### Task 9: the page and `hits.json`

Decisions 6, 10, 11; ruling 6.

- [ ] **Open check carried from slice 2** (its Task 5 Step 0): Open WebUI's `chat` table columns (`id, title, updated_at,
  chat`) are unverified, since `denbi-agui-01` runs the AG-UI frontend only. On an instance with Open WebUI, run the
  `pragma table_info(chat)` check slice 2's Task 5 names; a difference is a ruling in `progress.md` and a reader fix.
- **If this slice edits `canary_watch.py`**, it first splits `check_offsets`, `run_capped` and the transports
  (~140 lines) into `canary_transport.py`, as slice 2's final review recommended (progress ruling 11).

**Files:**
- Modify: `platform/report/sperange_report.py`, `platform/report/hits_view.py`
- Create: `platform/report/tests/test_hits_service.py`

**Interfaces:**
- Consumes: `HitsFile` (`canary_hits`, slice 1), `participant_body`, `NOTICE` (`hits_view`, slice 1), the status
  file (`<hits_dir>/<id>.status.json`, slice 2, ruling 6).
- Produces:
  - `make_server(listen, reports_dir, coder_url, hits_dir=None)`; env `HITS_DIR`, default
    `/data-share/canary-hits` (`main`); `Handler.hits_dir`.
  - `Handler.can_see_hits(meta: dict | None, user: dict) -> bool`: `is_admin(user)` or `meta` is not `None` and
    `user["username"] == meta["owner"]`. A workspace with no sidecar is visible to admins only.
  - `GET /reports/<id>/hits`: 404 for a malformed id; 403 (`message_page`) when `can_see_hits` is false; else 200,
    `page("Canary hits · <workspace>", participant_body(meta, hits, status), user, scripts=("hits.js",),
    styles=("hits.css",))`; `page` gains `scripts` and `styles` (file names under `static/`, linked as
    `{PREFIX}/static/<name>`, absolute like its others). The body's list is
    `<section id="hits" data-wid="<id>" data-last="<newest id or 0>">`.
    No hits file: the page says "No hits yet." with the status line; status `encrypted`: "The canary record is
    encrypted: the watcher cannot match this workspace."; no status file: "Not watched yet.".
  - `GET /reports/<id>/hits.json`: same rule; `{"workspace": id, "status": status | null, "hits": [records]}`;
    `?after=<int>` returns the records past that id (any other query key is ignored, a non-integer is 400).
  - `hits_view.status_line(status: dict | None, now: float) -> str`: "running · watched 3 s ago", "stopped",
    "not reachable since 14:02", "hits file full", from `state`, `last_poll`, `since`, `note`.
  - The status file's per-kind `hits` counts are cumulative over every generation and run in the hits file (slice
    2's final review): where the page shows counts, it either says so or recounts from this generation's hits.
- A participant who is logged out gets the login redirect (as `/reports/<id>`), `hits.json` a 401.

- [ ] **Step 1: Write the failing tests** in `test_hits_service.py`, with a fixture like `test_report.py`'s
  `service` plus a hits dir holding `<WID>.jsonl` (one `agui` and one `openwebui` hit built by
  `canary_hits.hits_for` over slice 1's fixture places) and `<WID>.status.json`:
  `test_owner_sees_both_frontends_with_value` (200; "AG-UI" and "Open WebUI" labels; `FCANARY-TEST01` in the
  page), `test_admin_sees_any_workspace`, `test_other_user_gets_403` (page and `hits.json`),
  `test_logged_out_redirect_and_401`, `test_notice_on_page` (decision 11), `test_stopped_workspace_renders`
  (status `stopped`: 200, "stopped", the hits), `test_no_hits_file_yet` and `test_encrypted_record_says_so`,
  `test_hits_json_after` (`?after=1` gives the second record only; `?after=x` 400),
  `test_page_escapes_titles_and_excerpts` (*Review Focus* 1: a session title and an excerpt holding
  `<img src=x onerror=alert(1)>` appear only escaped), `test_csp_and_no_inline_script` (the hits page carries the
  CSP header and no `<script>` without `src`).
- [ ] **Step 2: Run** `uv run --with pytest --with markdown pytest platform/report/tests/test_hits_service.py -q`.
  Expected: FAIL.
- [ ] **Step 3: Implement** the routes, `can_see_hits`, `status_line`, the `HITS_DIR` setting, and the
  `sys.path` line before the sibling imports.
- [ ] **Step 4: Run** the report suite. Expected: PASS, `test_report.py` unchanged.
- [ ] **Step 5: Commit** `Report service: the canary hits page and hits.json`.

### Task 10: the event stream, and the latency check

Decisions 6 (2 s), 8 (10 s), 10; ruling 7; *Review Focus* 5.

**Files:**
- Modify: `platform/report/sperange_report.py`, `platform/report/hits_view.py` (`hit_html(hit) -> str`, the one
  hit's `<details>` with `data-id`, `data-kind`, `data-session`, `data-run`, which `participant_body` now uses for
  each hit)
- Modify: `platform/report/tests/conftest.py` (create it if slice 2 left its fake instance inside
  `test_canary_watch.py`: move the fake-instance fixture here, `fake_instance(tmp_path) -> (LocalTransport,
  output_root, reports_dir, runs_dir)`, and have slice 2's tests use it)
- Test: `platform/report/tests/test_hits_service.py`

**Interfaces:**
- Produces: `GET /reports/<id>/hits/events`, same access rule as the page (403/401, no redirect). Response:
  status 200, `Content-Type: text/event-stream`, `Cache-Control: no-store`, `X-Accel-Buffering: no`, the CSP, no
  `Content-Length`; it does not go through `Handler.send`. The start is `Last-Event-ID` (header) when it parses
  as an integer, else `?after=<int>`, else 0; a value past the file's end is clamped to its current line count (nothing is replayed, no
  error, and the next hit appended is sent). Then every 0.5 s: the hits file's complete new lines, each as `id: <n>`, `event: hit`,
  `data: {"id", "kind", "loud", "type", "frontend", "html": hit_html(hit)}`; when the status file's mtime
  changes, `event: status` with `data: {"line": status_line(...)}`; every 15 s with nothing to send, a `: ping`
  comment. A missing hits file is no hits yet; the stream waits for it. The stream ends after 30 minutes
  (`EventSource` reconnects with `Last-Event-ID`), on a write error (`BrokenPipeError`, `ConnectionResetError`),
  or at once with 503 when 200 streams are already open (ruling 7).
- Loud kinds are `answer`, `sent`, `delivered`, `touched` (spec *Hits*); `hits_view.LOUD` holds them.

- [ ] **Step 1: Write the failing tests** (a helper reads events from the open response with a deadline):
  `test_new_line_reaches_stream_within_2s` (decision 6: open the stream, append a hit with `HitsFile.append`, the
  event arrives within 2 s), `test_events_resume_past_end` (`Last-Event-ID: 99` over a 2-line file: no event,
  then an appended hit arrives as id 3), `test_events_before_file_exists` (no hits file when the stream opens:
  an appended first hit arrives as id 1), `test_last_event_id_catch_up` (`Last-Event-ID: 1` over 3 lines: ids 2
  and 3), `test_status_event`, `test_events_access_rule` (another user 403, logged out 401),
  `test_no_route_takes_a_token` (decision 10: the service answers 404 or ignores every query key but `after`; the
  routes table in the source has no path parameter but the workspace id), `test_service_logs_no_token` (decision
  10: `capfd` over a page, `hits.json` and stream session: no fixture token in the output),
  `test_latency_fake_instance` (decision 8: a `Watcher` from slice 2 over `fake_instance`, `tick` in a thread every
  second, the service on the same hits dir; open the stream, append a journal run whose `TOOL_CALL_RESULT` holds
  `FCANARY-TEST01` to the fake instance's journal: the `touched` hit arrives within 10 s).
- [ ] **Step 2: Run** the hits service tests. Expected: FAIL.
- [ ] **Step 3: Implement** the stream in the handler (`do_GET` routes `<id>/hits/events` before the page), with a
  per-server counter of open streams under a lock.
- [ ] **Step 4: Run** the report suite. Expected: PASS.
- [ ] **Step 5: Commit** `Report service: the canary hits event stream`.

### Task 11: the page script, the Coder app, the docs

Decisions 6, 10 (a notification names kind and type only); ruling 8.

**Files:**
- Create: `platform/report/static/hits.js`
- Modify: `platform/report/static/hits.css` (the live parts: the notify button, a new hit's highlight),
  `platform/coder/template/main.tf` (a `coder_app "hits"` after `coder_app "report"`),
  `platform/coder/deploy/sperange-report.service` (comment: it reads the hits root, writes nothing there),
  `platform/coder/deploy/report.env.example` (`HITS_DIR=/data-share/canary-hits`),
  `platform/report/README.md` (the hits page, `hits.json`, the stream, who may read them),
  `platform/coder/README.md` (the "Canary hits" button beside "Report" in *Testbed presets and the run report*)
- Test: `platform/report/tests/test_hits_service.py`

**Interfaces:**
- `hits.js`: reads `data-wid` and `data-last` from `#hits`, opens
  `new EventSource("/reports/" + wid + "/hits/events?after=" + last)`; on `hit`, inserts `data.html` at the top of the list with
  `insertAdjacentHTML` (the server escaped every field: ruling 8), bumps the headline count for a loud kind or
  "also seen" for a quiet one, marks it new; on `status`, sets the status line's `textContent`. A "Notify me"
  button calls `Notification.requestPermission()`; once granted, each `hit` event with `loud` and an id past the
  list's `data-last` raises `new Notification("Canary hit: " + kind, {body: type})`: kind and type, never the
  value or excerpt. No `eval`, no `innerHTML` from anything but `data.html`.
  A "Group by run" toggle (spec *Participant page*: grouped by session and run on demand) reorders the hits'
  `<details>` under one heading per session and run, from the `data-session` and `data-run` attributes `hit_html`
  puts on each (Task 10), and back to newest first; it moves the server's elements, it builds no HTML.
- `coder_app "hits"`: `slug = "hits"`, `display_name = "Canary hits"`, `icon = "/emojis/1f6a8.png"`,
  `url = "${data.coder_workspace.me.access_url}/reports/${data.coder_workspace.me.id}/hits"`, `external = true`,
  `open_in = "tab"`, with a comment like the report's (served by the portal; works while stopped; owner and
  admins only).

- [ ] **Step 1: Write the failing tests** `test_page_loads_hits_script` (the page has a "Group by run" button,
  each hit `data-session` and `data-run`, `<script src="/reports/static/hits.js">` and `data-wid`;
  `GET /reports/static/hits.js` is 200 `text/javascript`), and `test_coder_app_hits` (`main.tf` holds `slug = "hits"` and the `/hits` URL; skip when the file is absent).
- [ ] **Step 2: Write** `hits.js`, the CSS, the app, the unit comment, `report.env.example`, both READMEs.
- [ ] **Step 3: Run** the report suite and `terraform fmt -check platform/coder/template` (skip it if
  `terraform` is not installed, and say so in the PR body). Expected: PASS.
- [ ] **Step 4: Screenshot** (skill `browser-playwright`): run the service locally over the fixture hits dir with
  a `FakeCoder` that knows one owner token (a small script in the scratchpad, not committed), set the session
  cookie, open `/reports/<WID>/hits`, append a hit while the page is open, and take one screenshot showing the
  new hit at the top. Fixture tokens only (`FCANARY-TEST01`). Commit it to
  `docs/superpowers/plans/2026-11-10-canary-hit-viewer/evidence/slice-3/participant-page.png` and embed it in the
  PR body.
- [ ] **Step 5: Commit** `Canary hits: page script, Coder app and docs`.
