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
