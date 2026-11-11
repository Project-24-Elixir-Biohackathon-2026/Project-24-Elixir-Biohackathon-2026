# The run report service

`sperange_report.py` serves the run reports and the runs browser of the portal at
`https://sperange.bihealth.org/reports/…`. Caddy forwards everything under `/reports`
to it (port 7090). Every portal user can read everything here; only a report's owner
and portal admins can write it. Design: `docs/specs/2026-11-06-run-report-service.md`
and `docs/specs/2026-11-10-runs-browser.md`.

| | |
|---|---|
| `sperange_report.py` | The service (standard library plus `python3-markdown` and `python3-yaml`) |
| `static/` | The pages' CSS and scripts, the runs browser (`runs.js`, `runs.css`) and the vendored EasyMDE editor |
| `tests/` | `pytest` against a fake Coder API |
| `../coder/deploy/sperange-report.service`, `report.env.example` | The systemd unit and its env file (`REPORTS_DIR`, `RUNS_DIR`, `CODER_URL`, `LISTEN`) |

## Logging in

The service asks Coder who you are. In the browser the `coder_session_token` cookie
from the portal login does that. From a script, send a Coder token in the
`Coder-Session-Token` header (make one with `coder tokens create`, or use the CLI's
own token in `~/.config/coderv2/session`):

```bash
TOKEN=$(cat ~/.config/coderv2/session)
curl -s -H "Coder-Session-Token: $TOKEN" https://sperange.bihealth.org/reports/api/runs
```

Without a login, a page redirects to the portal login; an API or `.md` request
answers `401` with `{"error": "not logged in"}`.

## Pages

| Route | What it is |
|---|---|
| `GET /reports/` | The list of live reports, one per workspace |
| `GET /reports/<workspace id>` | One report: the EasyMDE editor for the owner and admins, read-only for everyone else |
| `GET /reports/runs` | The runs browser: every archived run, one run with its report and chats, one chat as turns. Its views are hash routes: `#/run/<run>`, `#/run/<run>/chat/<frontend>/<chat>`, `#/workspace/<workspace id>` |
| `GET /reports/healthz` | `200 ok`, no login |

A workspace's "Report" button opens `/reports/<workspace id>`; its "Archived chats"
button opens `/reports/runs#/workspace/<workspace id>`.

## Live reports

| Route | What it does |
|---|---|
| `GET /reports/<workspace id>.md` | The report's Markdown. The `ETag` header is the SHA-256 of the file |
| `PUT /reports/<workspace id>.md` | Saves the report. Body: the Markdown (UTF-8, under 1 MB). `If-Match` with the ETag you read is required; `412` if the file changed meanwhile, `403` unless you are the owner or an admin. Answer: `{"etag", "saved"}` |
| `POST /reports/preview` | Markdown in, the same sanitized HTML fragment the pages show out |
| `GET /reports/api/reports` | `{"reports": [...]}`: every live report with `workspace_id`, `workspace`, `owner`, `instance`, `created`, `parameters`, `template_sha256`, `last_saved` |

Reading and saving a report from a script:

```bash
URL=https://sperange.bihealth.org/reports/<workspace id>.md
curl -s -D headers.txt -o report.md -H "Coder-Session-Token: $TOKEN" $URL
ETAG=$(grep -i '^etag' headers.txt | cut -d' ' -f2 | tr -d '\r')
# edit report.md, then:
curl -s -X PUT -H "Coder-Session-Token: $TOKEN" -H "If-Match: $ETAG" --data-binary @report.md $URL
```

`PUT` and `POST` from a browser must come from the portal's own origin.

## Archived runs

`playbooks/archive.yml` writes one directory per stopped workspace under `RUNS_DIR`
(default `/data-share/runs`). The API reads them as they are; `<run>` is the
directory name (`<UTC time>_<instance>`, for example
`2026-11-10T105525Z_cw-yasinmiran-chicken`), `<frontend>` is `openwebui` or `agui`,
`<chat>` the chat file's stem (`01-title`). The participant's e-mail and
`canaries.json` are never served.

| Route | What it returns |
|---|---|
| `GET /reports/api/runs` | `{"runs": [...]}`, newest first. One summary per run: `id`, `archived_at`, `instance`, `participant`, `workspace`, `model`, `flavor`, `frontends`, `workflows`, `samples`, `tiers`, `seed`, `chats` (count per frontend), `report` (`filled`, `workspace_id`) |
| `GET /reports/api/runs/<run>` | The summary plus `parameters` (all of `run.yml`), `chat_list` (every chat: `frontend`, `id`, `title`, `created`, `updated`, `messages`, `tags`, `archived`), `report` (`markdown`, `html`, `filled`, `workspace_id`, `created`) and `files` (`agent_runs`, `journals`) |
| `GET /reports/api/runs/<run>/report.md` | The report as archived, `text/markdown` |
| `GET /reports/api/runs/<run>/chats/<frontend>/<chat>` | One chat as turns: `title`, `meta`, `facts` (the key/value lines above the first turn), `turns` (each `role`: user, assistant, system, tool or section; `label`, `model`, `at`, `markdown`, `html`) and `links` to the two raw files |
| `GET /reports/api/runs/<run>/chats/<frontend>/<chat>.md` | The chat's Markdown as `write_run.py` rendered it |
| `GET /reports/api/runs/<run>/chats/<frontend>/<chat>.json` | The chat's export as archived (Open WebUI or AG-UI) |
| `GET /reports/api/runs/<run>/agui/agent-runs.jsonl` | The agent's run log, `application/x-ndjson` |
| `GET /reports/api/runs/<run>/agui/journals/<session id>.jsonl` | One AG-UI session journal as stored (the ids are in `files.journals`) |
| `GET /reports/api/workspaces/<workspace id>` | `{"workspace_id", "live_report", "runs"}`: the workspace's live report (as in `api/reports`, or `null`) and its archived runs, each with `chat_list`. A run belongs to the workspace when its archived report names the workspace id; older archives without that are matched by instance name |

Anything else under `/reports/api/` answers `404` with `{"error": "not found"}`.
The run listing is cached for ten seconds.

Examples:

```bash
H="Coder-Session-Token: $TOKEN"
B=https://sperange.bihealth.org/reports/api

curl -s -H "$H" $B/runs | jq '.runs[] | {id, participant, model, chats}'
curl -s -H "$H" $B/runs/<run> | jq '.chat_list'
curl -s -H "$H" $B/runs/<run>/chats/agui/01-title | jq '.turns[] | {role, at, markdown}'
curl -s -H "$H" $B/runs/<run>/chats/agui/01-title.json > chat.json
curl -s -H "$H" $B/runs/<run>/report.md
curl -s -H "$H" $B/workspaces/<workspace id> | jq '.runs[].id'
```

## Running and testing

```bash
REPORTS_DIR=/tmp/reports RUNS_DIR=/tmp/runs CODER_URL=http://127.0.0.1:7080 python3 sperange_report.py
curl -I http://127.0.0.1:7090/reports/healthz
```

```bash
python3 -m venv .venv && .venv/bin/pip install pytest markdown pyyaml && .venv/bin/python -m pytest tests -q
```

On the portal VM the service runs as the systemd unit `sperange-report`; restart it
after a change: `sudo systemctl restart sperange-report`.
