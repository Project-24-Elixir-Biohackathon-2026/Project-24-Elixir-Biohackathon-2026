# Runs browser

A third section of the site next to the portal and the catalog: the archived runs and the
live reports, in the browser and as an API. Decided 2026-11-10: built into the report
service (over a static section built by the sync, which has no login, and a separate API
service), readable by everyone logged in, archived runs and live reports together.

## Goal

A participant or operator opens one page and sees every run of the range: who ran what,
with which model and frontends, whether the report was filled in, and the chats as they
happened. Scripts get the same data as JSON to analyse chats and reports across runs.

## Design

**Where.** `platform/report/sperange_report.py`, the service behind `/reports`. It already
logs people in through Coder's session cookie, lists the live reports and renders Markdown
through an allowlist sanitizer. The archives it reads are the directories
`playbooks/archive.yml` writes under `/data-share/runs` (`RUNS_DIR`), read-only.

**API.** `GET /reports/api/runs` (every run, newest first: parameters without the e-mail,
chat counts per frontend, report state), `GET /reports/api/runs/<run>` (parameters, the
report as Markdown and rendered HTML, the chat list of both frontends, which raw files
exist), `GET /reports/api/runs/<run>/chats/<frontend>/<chat>` (the chat as turns: role,
model, time, sanitized HTML and the Markdown of each), the raw `.md` and `.json` of a chat,
`report.md`, `agui/agent-runs.jsonl`, `agui/journals/<session>.jsonl`, and
`GET /reports/api/reports` (the live reports), and `GET /reports/api/workspaces/<id>` (one workspace's runs with their chats, matched by the archived sidecar's workspace id, or by instance name for archives without one, plus its live report). The session token is read from the cookie or
from a `Coder-Session-Token` header, so `curl` with the token of the `coder` CLI works.
Without a session the API answers 401 as JSON; the pages still redirect to the login.

**Turns.** `write_run.py` renders both frontends' chats to Markdown with one `## role · time`
heading per turn (Open WebUI adds the model in parentheses; AG-UI has a few other sections
such as `## Compacted`). The service splits at those headings, outside fenced code, and
renders each turn like a report. The browser shows them as a conversation; the JSON export
as archived is one link away for anyone who wants the structure.

**Page.** `/reports/runs` is a shell; `static/runs.js` draws the list (tiles, filters, a
sortable table, the live reports), one run (facts, report, chats, raw files) and one chat
(turns) from the API, with the view in the URL's hash so every state has a link. Vanilla
script, no inline script, the service's Content Security Policy unchanged. The landing page
gets a third card, and every Coder workspace a "Chats" button (`coder_app.chats`) that opens
`#/workspace/<id>`: the workspace's archived runs with their chats and a link to its report.

**Access.** Everyone logged in reads everything, as with the reports. Never served: the
participant's e-mail (`run.yml`, the sidecar) and `canaries.json`. Every path component is
validated against a fixed pattern before it touches the filesystem, and only the files of
the known layout are reachable.

**Permissions.** The archive's `agui/` directory, the journals and the agent's run log were
written owner-only; the service runs as its own user, so `roles/run_archive` now writes
them world-readable like the rest of the run. Archives made before that need one `chmod`.

## Not done, and why

- Live updates when a workspace is archived: the list is a fetch away and the archive is
  written once; server-sent events can be added on top of the JSON later.
- Search inside transcripts across runs: the raw files are served, so a script does it;
  the page searches the table only.
- Charts: tiles only in this version.
