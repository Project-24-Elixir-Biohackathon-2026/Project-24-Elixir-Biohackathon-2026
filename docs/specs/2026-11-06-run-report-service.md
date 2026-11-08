# Run report service

Design for the run report as a record kept on the portal VM, off the SPE instance,
with a "Report" button on the workspace. Decided 2026-11-06 (sketch accepted, option
"portal service" over "GitHub repository" and "file on the VM"). Plan:
`docs/plans/2026-11-06-run-report-service.md`.

## Goal

One report per workspace, written by the participant while they test, readable by
every portal user, never stored on the VM under test, present from creation on and
surviving stop, crash and deletion of the workspace. The Open WebUI note goes away so
there is one copy.

## Design

**Storage.** `<spe_reports_root>/<workspace id>.md` on the shared storage of the portal
VM (`/data-share/reports`), with a sidecar `<workspace id>.json`: owner (Coder
username), owner email, workspace name, instance name, creation time, the parameters
without the seed, and the SHA-256 of the initial content (for "not filled in"). The
Coder workspace id is stable across stop and start and differs for a recreated
workspace of the same name. The files stay when the workspace is deleted.

**Creation.** `playbooks/create.yml` runs on the portal VM with every variable the
template uses. Role `run_report`, on localhost in the first play, renders
`reports/run_report.md.j2` into the reports directory and writes the sidecar, both
with `force: false` so a restart never overwrites a report. Only when
`spe_coder_workspace_id` is set (the Coder template passes it) and not under
`spe_local_apply` (a re-apply from the VM has no shared storage). The template loses
the seed line (the seed reproduces every canary; it stays in `run.yml` of the archive)
and tells the participant where the report is.

**Service.** `platform/report/sperange_report.py`: Python standard library plus
`python3-markdown`, no framework, unit `sperange-report.service`, env file
`/etc/sperange/report.env` (`CODER_URL`, `REPORTS_DIR`, `LISTEN`), listening on
`127.0.0.1:7090`, as user `sperange-report` that owns nothing but the reports
directory (group-writable for the provisioner, which runs as `ubuntu`). Caddy routes
`/reports*` to it in front of the Coder catch-all; Coder has no `/reports` path.

Routes:

| Route | What |
|---|---|
| `GET /reports/` | every report: workspace, owner, created, last saved |
| `GET /reports/<id>` | the editor page; read-only for everyone but the owner and Coder owners |
| `GET /reports/<id>.md` | the Markdown, `ETag` = SHA-256 of the file |
| `PUT /reports/<id>.md` | save; `If-Match` required, 412 when the file changed meanwhile; 1 MB limit |
| `POST /reports/preview` | Markdown in, HTML fragment out, for the preview pane |
| `GET /reports/static/<file>` | the page's CSS and script |
| `GET /reports/healthz` | 200 without login |

**Login.** None of its own. The browser carries Coder's session cookie for the apex
domain; the service forwards its value to Coder's `users/me` endpoint (header
`Coder-Session-Token`) and caches the answer for 30 s per token. No session means a
redirect to Coder's login page with the report as `redirect`. Everyone logged in may
read; the report's owner (the sidecar's username) and users with Coder's `owner` role
may write. The workspace's state (running, stopped, deleted) is looked up with the
viewer's token and shown when the lookup succeeds. The cookie value goes to Coder
only and is never logged.

**Editor page.** The owner and admins get EasyMDE (vendored, with Font Awesome 4 for
its toolbar; 2026-11-06, chosen over a structured form and over Toast UI): Markdown
with a toolbar, side by side with a preview that the service renders, a save button,
autosave three seconds after typing stops. The page keeps the `ETag` it loaded and
sends it as `If-Match`; a 412 shows "changed elsewhere, reload" instead of
overwriting. Everyone else gets the rendered report as a reading view with a link to
the Markdown. Both show owner, workspace with its state, instance, created and "last
saved", in the landing page's look.

**Button.** A fourth `coder_app` in the template, "Report", `external = true`, URL
`<access url>/reports/<workspace id>`. Not proxied through the VM, so it works while
the workspace is stopped.

**Archive.** `run_archive/tasks/write.yml` copies the report and its sidecar into the
run directory as `report.md` and `report.json`. `write_run.py` no longer takes a note
title: it reads `report.md` beside the run and reports its state (missing, not filled
in, filled in) in `index.md`; Open WebUI notes all go to `notes/`. The Open WebUI role
no longer creates a note, and the export no longer carries the template. The AG-UI
part's `index.md` links the report one level up.

## Security

- Any logged-in user reads any report, so a report must not run script in another
  viewer's browser on the portal origin (that origin holds Coder's cookie). Raw HTML
  is escaped before rendering, so only Markdown syntax produces markup, and every
  page carries `Content-Security-Policy: default-src 'self'; script-src 'self';
  style-src 'self' 'unsafe-inline'; frame-ancestors 'none'`, which also blocks
  `javascript:` links. No inline script; inline styles are allowed because the editor
  sets some, and a style cannot reach the cookie.
- Writes require a same-origin request: the `Origin` header, when present, must be
  the portal; Coder's cookie is `SameSite=Lax` as well.
- Ids are validated as UUIDs before any path is built.
- The service runs as its own user, can write only the reports directory, and has no
  Coder token of its own.

## Out of scope

- Editing the report from the VM (web terminal, Coder Agents): the file is not there.
- A link to the report inside the chat frontends; the Coder app is the entry point.
- Reports for instances created by hand (`docs/getting-started.md`): no workspace id,
  no report; the archive says "missing".
- Deleting a report; comments; history beyond "last saved".

## Decisions

1. Report per workspace, not per run; each stop copies the current state into that
   run's directory. Cost if wrong: a restarted workspace continues an older report.
2. Reports stay after workspace deletion and remain editable by their owner.
3. Standard library server instead of FastAPI: nothing to install beyond
   `python3-markdown`, no virtualenv on the portal VM, tests need no network.
   Cost if wrong: a larger service later rewrites the routing.
4. A dedicated service user with a group-writable reports directory. Cost if wrong:
   NFS permissions bite; fallback is running the unit as `ubuntu`, like Coder.
