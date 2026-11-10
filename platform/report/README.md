# The run report service

One Markdown report per portal workspace, kept on the portal VM and edited in the
browser behind the workspace's "Report" button. Never on the SPE instance, present
from the first build on, kept after the workspace is gone. Design:
`docs/specs/2026-11-06-run-report-service.md`.

| | |
|---|---|
| `sperange_report.py` | The service: standard library plus `python3-markdown` and `python3-yaml`; routes in its docstring, the runs browser's API included |
| `static/runs.js`, `static/runs.css` | The runs browser (`/reports/runs`): list, one run, one chat, drawn from the JSON API |
| `static/` | The page's stylesheet and script (no inline script: the pages carry a CSP), plus the vendored editor: EasyMDE 2.21.0 (`easymde.min.js`, `easymde.min.css`, from the npm package `easymde`) and Font Awesome 4.7.0 for its toolbar (`font-awesome.min.css` with its `@font-face` cut down to `fontawesome-webfont.woff2`, from the npm package `font-awesome`) |
| `tests/` | `pytest` against a fake Coder API |
| `../coder/deploy/sperange-report.service`, `report.env.example` | The unit and its env file |
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

## The runs browser and the API

`/reports/runs` is a page for the archives that `playbooks/archive.yml` writes under
`RUNS_DIR` (default `/data-share/runs`, read-only here) and for the live reports: tiles,
a filterable table of every run (participant, workspace, model, frontends, chats, report
state), one run with its parameters, its report and the chats of both frontends, and a
chat as turns. Everyone logged in sees everything; the participant's e-mail and
`canaries.json` are never served.

The same data is JSON for scripts, with the Coder session token in the cookie or in a
`Coder-Session-Token` header (`coder tokens create` makes one):

```bash
TOKEN=$(cat ~/.config/coderv2/session)
curl -s -H "Coder-Session-Token: $TOKEN" https://sperange.bihealth.org/reports/api/runs | jq '.runs[] | {id, participant, model, chats}'
curl -s -H "Coder-Session-Token: $TOKEN" https://sperange.bihealth.org/reports/api/runs/<run>            # parameters, report, chat list
curl -s -H "Coder-Session-Token: $TOKEN" https://sperange.bihealth.org/reports/api/runs/<run>/chats/agui/01-title      # turns
curl -s -H "Coder-Session-Token: $TOKEN" https://sperange.bihealth.org/reports/api/runs/<run>/chats/agui/01-title.json # as archived
curl -s -H "Coder-Session-Token: $TOKEN" https://sperange.bihealth.org/reports/api/reports                 # the live reports
```

The routes are listed in the service's docstring. A chat's turns come from the archived
Markdown (`write_run.py` renders both frontends the same way), split at its `## role · time`
headings and sanitized like the reports; the raw `.md` and `.json` are one link away.

Run it by hand: `REPORTS_DIR=/tmp/reports RUNS_DIR=/tmp/runs CODER_URL=http://127.0.0.1:7080 python3 sperange_report.py`,
then `curl -I http://127.0.0.1:7090/reports/healthz`.
