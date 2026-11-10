# The run report service

One Markdown report per portal workspace, kept on the portal VM and edited in the
browser behind the workspace's "Report" button. Never on the SPE instance, present
from the first build on, kept after the workspace is gone. Design:
`docs/specs/2026-11-06-run-report-service.md`.

| | |
|---|---|
| `sperange_report.py` | The service: standard library plus `python3-markdown`; routes in its docstring |
| `static/` | The page's stylesheet and script (no inline script: the pages carry a CSP), plus the vendored editor: EasyMDE 2.21.0 (`easymde.min.js`, `easymde.min.css`, from the npm package `easymde`) and Font Awesome 4.7.0 for its toolbar (`font-awesome.min.css` with its `@font-face` cut down to `fontawesome-webfont.woff2`, from the npm package `font-awesome`) |
| `tests/` | `pytest` against a fake Coder API |
| `../coder/deploy/sperange-report.service`, `report.env.example` | The unit and its env file |
| `canary_watch.py`, `canary_reader.py`, `canary_record.py`, `canarymatch.py`, `canary_hits.py` | The canary hit viewer's watcher: see *Canary hit watcher* below |
| `hits_view.py` | Renders a hit to HTML, the participant page's body and the admin page's (its workspace rows), and reads the hits root and the watcher's status files; used by both the watcher (`--html`, the standalone early output) and `sperange_report.py` (both pages, *Canary hits pages* below) |
| `../coder/deploy/sperange-canary-watch.service` | The watcher's unit |
| `../ansible/roles/run_report/` | Writes the report and its sidecar at the first build of a workspace |
| `../ansible/reports/run_report.md.j2` | The template the report starts from |

How it fits together: `create.yml` renders the template into
`/data-share/reports/<workspace id>.md` with a sidecar `.json` (owner, workspace,
parameters, the SHA-256 of the initial content). Caddy sends `/reports*` to the
service, which learns who is asking from Coder's session cookie (forwarded to Coder's
`users/me` endpoint, nowhere else). Everyone logged in reads every report; the owner
and portal admins write. On stop, the archive copies both files into the run
directory as `report.md` and `report.json`.

The owner (and portal admins) get the EasyMDE editor, side by side with a preview
that the service renders, so it is the same sanitized HTML everyone else sees in the
reading view. The look follows `platform/site/static/site.css`. To update the editor,
replace the two EasyMDE files from a newer npm tarball and keep `spellChecker: false`
in `report.js` (the spell checker would fetch a dictionary from a CDN, which the CSP
forbids anyway).

Run the tests:

```bash
python3 -m venv .venv && .venv/bin/pip install pytest markdown && .venv/bin/python -m pytest tests -q
```

Run it by hand: `REPORTS_DIR=/tmp/reports CODER_URL=http://127.0.0.1:7080 python3 sperange_report.py`,
then `curl -I http://127.0.0.1:7090/reports/healthz`.

## Canary hit watcher

`canary_watch.py` is a separate unit (`../coder/deploy/sperange-canary-watch.service`,
`sperange-canary-watch`), not part of the report service: a daemon that polls every running Coder
workspace's instance over SSH (the reader, `canary_reader.py`, sent on stdin and run read-only) and
scans each stopped run's archive once, matching against the workspace's canary record
(`canary_record.py`, `canarymatch.py`) and writing hits, state and status under `<hits
dir>`, default `/data-share/canary-hits` (design: `docs/specs/2026-11-10-canary-hit-viewer.md`).
It reads: each workspace's report sidecar (`/data-share/reports/<id>.json`, to learn its
instance), that instance's output directory (`hosts.yml`, `canaries.json`), and each archived run
directory (`/data-share/runs/*_<instance>/`). It writes only under `<hits dir>`: a hits file
(`<id>.jsonl`, mode 0640), a state file (`<id>.state.json`, mode 0600) and a status file
(`<id>.status.json`, mode 0640) per workspace, never anything on the instance (decision 1,
*Nothing on the instance changes*) or in the run archive.

Three forms:

- **The daemon** (`canary_watch.py`, no flags needed beyond the defaults): `Watcher.run_forever()`,
  as the unit runs it.
- **`--archive RUN_DIR --out HITS.jsonl`**: scans one already-archived run directory into a hits
  file by hand (also used by tests and re-renders), optionally `--html PAGE.html` for a standalone
  participant page.
- **`--once --output-dir DIR --out HITS.jsonl`**: a hand check only, never run by the unit (the
  daemon never scans an instance without a report sidecar). One poll of `DIR`'s instance from zero
  offsets, through the real SSH transport,
  appending new hits to `--out`; no report sidecar, no state or status file, nothing written under
  `<hits dir>`. Prints the sources the reader found, what is missing, any source errors and the hit
  count per kind to stdout — never a token, an excerpt or a line of a source.

## Canary hits pages

`sperange_report.py` reads `<hits dir>/<workspace id>.jsonl` and `.status.json` (never writes
there; only the watcher does) to serve, narrower than the report (decision 10: the workspace's
owner and Coder owners only, 403 for everyone else, 401/redirect when logged out):

- `GET /reports/<id>/hits` — the participant page (`hits_view.participant_body`, HTML behind
  `static/hits.js` and `hits.css`): header, headline counts, the literal-matching notice, then
  the hits newest first. Every hit is a collapsed `<details>`: loud ones in the list, quiet ones
  under one "also seen (N)".
- `GET /reports/<id>/hits.json` — the same hits as JSON, `?after=<id>` for only the new ones.
- `GET /reports/<id>/hits/events` — the same hits live, as server-sent events: `event: hit` with
  the hit's id, kind, loudness, canary type, frontend and server-rendered HTML (one renderer,
  `hits_view.hit_html`, so a hit inserted live reads as one loaded with the page); `event: status`
  with the watcher's status line and `empty` (`hits_view.empty_text`, the text a hits list with
  none to show would use for this status, so a shown placeholder can be kept current). Sent again
  on change, and also every `stream_status_refresh` seconds (10) even when the status file is
  unchanged, so "watched N s ago" keeps ageing instead of freezing once the watcher stops touching
  it. Resumes past `Last-Event-ID` (else `?after=`); ends after 30 minutes (the browser
  reconnects) and refuses a 201st concurrent stream with 503.

`static/hits.js` opens the event stream, inserts each hit's HTML at the top of the list (no HTML
built in the browser but the server's own, parsed once from the event), keeps the headline counts,
the status line and an already-shown placeholder's text in sync, offers "Notify me" (kind and type
only, never the value or excerpt)
and "Group by run" (reorders the hits on the page, live ones included, by `data-session`/
`data-run`; builds no HTML of its own but the group headings. Only the loud hits are grouped —
"also seen" stays one collapsed block regardless). Both buttons are rendered `hidden` by
`hits_view.py` and shown once the script runs, so a page with no script (the standalone early
output, `--html`) never shows one that does nothing.

## Admin canary hits page

Coder owners only (403 for everyone else, 401/redirect when logged out, same rule as the
participant pages above); `/reports/` links to it ("Canary hits") for an admin, and shows no such
link to anyone else:

- `GET /reports/hits` — every workspace with hits or a status file, newest first
  (`hits_view.workspace_rows`): a table (name linking to that workspace's own `/hits` page, owner,
  instance, the viewer's Coder state for it, loud counts, quiet count, "Newest (detected)": the
  newest hit's `detected`, watcher status; a row with no state lookup or a failed one leaves that
  cell blank; a hits file that cannot be read shows as no hits, logged), the same banner as the
  participant page, then every workspace's hits merged, newest first by `detected` (the watcher's
  clock, not the instance's own `at`). Four filters (kind, type, frontend, workspace), applied in
  the browser over what the page already rendered. Capped at 500 hits (`ADMIN_PAGE_HITS`; "N more,
  older: ..." when capped — the rest are on each workspace's own page, uncapped).
- `GET /reports/hits.json` — the same rows and hits as JSON, hits capped at 2000
  (`ADMIN_JSON_HITS`).
- `GET /reports/hits/events` — the same hits live across every workspace, as server-sent events
  (`static/hits-admin.js`): rescans the hits directory on every poll, so a workspace that starts
  being watched mid-stream is picked up; a file already present when the stream opened starts at
  its end (no replay of old hits), one that appears later starts from its first line. Event id
  `<workspace>:<n>`; no status events. A hit for a workspace not in the opening table's row list
  bumps no count until the next reload. A workspace's hits file that cannot be read is dropped from
  the stream after one log line (the others keep streaming); the stream itself still ends if a
  followed file is replaced, cut or removed, same as the participant stream, and the page reloads
  to recover — at most once a minute per browser tab, so a flapping file does not reload in a loop.
