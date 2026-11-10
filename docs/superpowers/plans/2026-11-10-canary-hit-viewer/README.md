# Canary hit viewer — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` (`AGENTS.md`,
> *Working Conventions*) to implement one slice per session and PR. Steps use checkbox (`- [ ]`) syntax.

**Goal:** a participant sees, live, every canary their workspace's agent or Open WebUI chat leaked, with the trace
around it, on a "Canary hits" page; Coder owners see every workspace's hits on one admin page.

**Spec:** [`docs/specs/2026-11-10-canary-hit-viewer.md`](../../../specs/2026-11-10-canary-hit-viewer.md),
decisions 1–11, *Early output*, clarification 1 (Open WebUI's chats are a source). Latest clarification when this
plan was written: 1. Each slice file names the decisions it implements.

**Architecture.** Five modules in `platform/report/`, standard library only, each with one job:

- `canarymatch.py`: whether and where a canary is in a text (decision 2); `metrics.py` imports it.
- `canary_record.py`: reads the canary record and `hosts.yml` (ruling 2); `handoff.py` imports it.
- `canary_hits.py`: turns one source's records into **places** (a text with its trace: frontend, session, run,
  prompt, tool) and places into **hits** (kind, excerpt), dedups them, and appends them to a hits file.
- `canary_watch.py`: the watcher: `--archive` scans one archived run (slice 1); the daemon finds running
  workspaces, pulls new lines with the **reader** (`canary_reader.py`, sent over SSH on stdin) and scans
  stopped runs' archives (slice 2).
- `hits_view.py`: renders hits as HTML (the early output's static file, then the service's pages).

`sperange_report.py` serves the participant page, `hits.json` and the event stream (slice 3) and the admin page
(slice 4) from the hits files the watcher writes; it never writes them.

**Tech stack:** Python 3 standard library (`sqlite3`, `subprocess` with `ssh`, `http.server`), pytest; plain JS in
`platform/report/static/` (the service's CSP allows no inline script); Terraform for the Coder app; systemd.

## Rulings

Each is *decision, why, cost if wrong*; a slice that departs from this plan adds one to [`progress.md`](progress.md)
(created by the first slice that departs) and rewrites the task text it changes.

1. **Open WebUI is read live from its SQLite database, not its API.** The reader opens `webui.db` with
   `sqlite3.connect("file:<path>?mode=ro", uri=True)` and selects `id, title, updated_at, chat` from `chat` where
   `updated_at > <offset>`. *Why:* no credential is needed (with `spe_webui_auth` on, the API wants the admin
   password, which the watcher does not hold), one query per poll, and the row's `chat` JSON is the shape
   `openwebui-export.json` holds, so one parser serves live and archive. *Cost if wrong:* an Open WebUI upgrade
   renames the table or columns; the reader then reports the source as unreadable (the page says so) and the
   fallback is the API (`/api/v1/chats/all/db`, as `export_openwebui.py` calls it) with credentials passed on stdin.
2. **The watcher imports nothing from `platform/promptfoo-evals/`.** `is_file_canary` and `METADATA_TYPES` move
   into `canarymatch.py`; `load_canaries`, `read_hosts` (with its `_scalar`) and the error they raise move into a
   new `platform/report/canary_record.py` (`RecordError`); `promptfoo-evals/handoff.py` imports all of them from
   there (`from canary_record import RecordError as ConfigError, …`, so its callers and `ManifestError` keep
   working). *Why:* the watcher needs the file/metadata rule for `touched` vs `seen` (decision 4) and the record and
   `hosts.yml` readers, and upstream has `platform/report/` but neither `handoff.py` nor `metrics.py` (checked
   2026-11-10, slice 5): an import of `handoff` would break the port. One rule keeps one copy (decision 2).
   *Cost if wrong:* none expected; the ladder's upstream port then needs `canary_record.py` and `canarymatch.py`
   upstream first (slice 1 says so in `BACKLOG.md`).
3. **Agent run log hits are `frontend: "agui"`.** Only the AG-UI chat drives the agent (Open WebUI calls the model
   itself, clarification 1). *Cost if wrong:* another frontend added on the agent gets mislabelled until the run
   log names its caller.
4. **The early output stays on the portal VM.** It shows canary values (decision 10), so the HTML is written to
   `/data-share/canary-hits/early-output/<run dir>.html` (mode 0640) and never committed; the PR commits only
   per-kind counts (`evidence/slice-1/counts.md`). *Cost if wrong:* none: the user reads it on the portal
   (`sudo cat`, or `scp` after a `sudo cp` to their home).
5. **A one-shot scan of an instance without a sidecar exists only by hand** (`canary_watch.py --once
   --output-dir <dir>`, slice 2), for checking the reader on our own de.NBI instance; the daemon never scans
   without a sidecar (decision 9). *Cost if wrong:* none: the flag only reads.
6. **The watcher writes a status file per workspace** (`<hits root>/<workspace id>.status.json`: `state`
   `running`|`stopped`|`unreachable`|`encrypted`|`capped`, `since`, `last_poll`), which the pages read for the
   header ("running · watched 3 s ago"). *Why:* the service must not hold the watcher's state or SSH access
   (spec ruling 4). *Cost if wrong:* none.
7. **Event streams are bounded**: each ends after 30 minutes (the browser reconnects and resumes), and the service
   holds at most 200 open streams (503 past it). *Why:* the service is a `ThreadingHTTPServer`, one thread per open
   stream; without a bound, open tabs pile up threads. *Cost if wrong:* a busy event (more than 200 open pages)
   sees 503s and a page that stops updating until reload; raise the cap.
8. **The stream carries each hit's HTML, rendered by the server** (`hits_view.hit_html`), which the page script
   inserts. *Why:* one renderer, in Python, escaped and tested once; the script holds no template to drift from
   it. *Cost if wrong:* none expected; the CSP still forbids inline script, so escaped HTML cannot run.
9. **The admin page shows the newest 500 hits and `hits.json` the newest 2000**; each workspace's own page and
   JSON hold all of it. *Why:* 50 workspaces at the 10 MB cap would be half a gigabyte per page load. *Cost if
   wrong:* an admin follows the workspace link for older hits.
10. **A workspace is running when its `hosts.yml` is newer than its newest run directory**, two mtimes that
   both come from the NFS server (the output tree and `/data-share` sit on the portal VM). *Why:* no Coder API call
   and no state on the service side. *Cost if wrong:* if the two trees ever live on hosts with skewed clocks, a
   stopped workspace is polled (its SSH fails: `unreachable`) or a running one waits for its next build; then ask
   Coder's API for the build state instead.

## Global Constraints

Every task's requirements include these.

- **Tests, before every commit:** `uv run --with pytest --with markdown pytest platform/report/tests -q` and, for a
  slice touching `metrics.py` or `handoff.py`, `(cd platform/promptfoo-evals && uv run --group dev pytest -q)`;
  slice 1 also `(cd platform/agui/pydantic-ai-agent && uv run --group dev pytest -q)` (the airlock test). New tests live in `platform/report/tests/` (`test_canarymatch.py`, `test_canary_hits.py`,
  `test_canary_reader.py`, `test_canary_watch.py`, `test_hits_pages.py`, `test_hits_service.py`).
- **Standard library only** in `platform/report/` (the portal runs it from the checkout with the system Python).
- **Nothing on the instance changes** (decision 1): no file under `platform/instance/`, no task in a role that runs
  on the instance. A test asserts the reader opens files read-only.
- **No canary value in a commit, a log line, a hit id or a URL** (decision 10). Fixtures use made-up tokens
  (`FCANARY-TEST01`, `MCANARY-TEST02`); logs carry workspace ids, counts and errors only.
- **Names fixed by the spec:** kinds `answer`, `sent`, `delivered`, `touched`, `seen`, `args`, `prompt`; places
  `answer`, `tool_args`, `tool_result`, `prompt`, `request`; sources `agui-journal`, `agent-runs`, `openwebui-db`,
  `receiver`, `archive`; frontends `agui`, `openwebui`; the unit `sperange-canary-watch.service`; hits root
  `/data-share/canary-hits`; excerpts at most 400 characters; poll 3 s, backoff 60 s, 1 MiB per poll, 200 hits per
  poll, 10 MB per hits file; routes `/reports/<id>/hits`, `/reports/<id>/hits.json`, `/reports/<id>/hits/events`,
  `/reports/hits`, `/reports/hits.json`, `/reports/hits/events`; the notice "Matching is literal: an encoded,
  split or paraphrased canary is not seen."
- **Upstream-clean:** code, `platform/` READMEs and the spec name nothing fork-only (`AGENTS.md`, *Contributing
  upstream*).
- **No model calls, no new instance.** Checks use fixtures, a fake instance (a local reader, no SSH), the portal's
  archive read over SSH (`ssh agent-service-1`, read-only), and at most our one de.NBI instance (standing OK,
  `AGENTS.md`, *Setup*). Deploying the watcher on the portal VM happens through upstream (slice 5), never by hand
  from a session.
- **Gates:** none beyond the floor. Opening the upstream PR (slice 5) is publishing: the session prepares the
  `contrib/` branch and leaves the PR to the user (`docs/guides/contributing-upstream.md`).

## File structure

| File | Slice | Job |
|---|---|---|
| `platform/report/canarymatch.py` | 1 | matching functions, file/metadata rule |
| `platform/report/canary_record.py` | 1 | `load_canaries`, `read_hosts` (ruling 2) |
| `platform/promptfoo-evals/metrics.py`, `handoff.py` | 1 | import from `canarymatch` and `canary_record` instead of defining |
| `platform/report/canary_hits.py` | 1 | places per source, hits, dedup, `HitsFile` |
| `platform/report/hits_view.py` | 1, 3, 4 | HTML for hits (static file, participant page, admin page) |
| `platform/report/canary_watch.py` | 1 (`--archive`), 2 (daemon) | the watcher |
| `platform/report/canary_reader.py` | 2 | the reader sent to the instance |
| `platform/coder/deploy/sperange-canary-watch.service`, `platform/coder/README.md` | 2 | unit, hits root setup |
| `platform/report/sperange_report.py`, `static/hits.js`, `static/hits-admin.js`, `static/hits.css` | 3, 4 | routes, event streams, page scripts |
| `platform/coder/template/main.tf` | 3 | the "Canary hits" app |
| `platform/report/README.md` | 2, 3, 4 | what the watcher and pages do, how to run `--archive` |

## PR slices

| n/N | Branch | Tasks | Delivers | Est. LOC | Reviewer checks | File | Status |
|---|---|---|---|---|---|---|---|
| 1/5 | `impl/canary-hit-viewer-1-match-archive` | 1–4 | `canarymatch` (metrics on it), hits from every source, `--archive`, the early output on a real run | ~750 | tests; counts in `evidence/slice-1/counts.md`; the HTML on the portal | [slice-1-match-archive.md](slice-1-match-archive.md) | planned |
| 2/5 | `impl/canary-hit-viewer-2-watcher` | 5–8 | the reader, discovery, polling with state and generations, on-stop scan, unit | ~700 | fake-instance tests; `--once` against our de.NBI instance | [slice-2-watcher.md](slice-2-watcher.md) | planned |
| 3/5 | `impl/canary-hit-viewer-3-participant-page` | 9–11 | participant page, `hits.json`, event stream, notifications, Coder app | ~600 | service tests incl. 10 s latency; screenshot | [slice-3-participant-page.md](slice-3-participant-page.md) | planned |
| 4/5 | `impl/canary-hit-viewer-4-admin-page` | 12–13 | admin page, its stream and filters; docs | ~400 | service tests; screenshot | [slice-4-admin-page.md](slice-4-admin-page.md) | planned |
| 5/5 | `impl/canary-hit-viewer-5-upstream` | 14 | `contrib/canary-hit-viewer` branch for upstream; the track line removed | ~0 (port) | the fork-only check; the user opens the PR | [slice-5-upstream.md](slice-5-upstream.md) | planned |

Slice 1 builds the spec's early output before anything that depends on decisions 4, 5 and 10's display.

## Review Focus

Inputs the spec implies and no single acceptance check covers; each line's test lives in the task named.

1. **Hostile reader output**: the participant is root on the instance, so lines may be non-JSON, huge, or carry
   HTML in titles and excerpts. Expected: dropped or capped, always escaped on the page (Task 5:
   `test_reader_output_untrusted`; Task 10: `test_page_escapes_titles_and_excerpts`).
2. **A watcher restart in the middle of a run**: expected no lost and no repeated hit (Task 7:
   `test_restart_mid_run_no_loss_no_repeat`).
3. **An instance rebuilt under the same workspace** (new `hosts.yml`, journals and `webui.db` start again, Open
   WebUI's `updated_at` lower than the stored offset): expected a new generation, offsets from 0 (Task 7:
   `test_new_generation_resets_offsets`, including the database offset).
4. **One canary in several places of one run, and one token the prefix of another** (`FCANARY-TEST01` and
   `FCANARY-TEST011`): expected one hit per place, no hit for the shorter token inside the longer (Task 2:
   `test_one_hit_per_place`, `test_prefix_token_not_matched`).
5. **An event stream reconnecting with a `Last-Event-ID` past the file's end, or a hits file not there yet**:
   expected an empty catch-up and live hits after, no error (Task 10: `test_events_resume_past_end`,
   `test_events_before_file_exists`).

## Spec clarifications a slice may add

None planned. A slice that finds the spec wrong adds a numbered clarification, folds it, and names it in its PR
body.

## Handoffs

[`handoffs/`](handoffs/): read only the newest (`methodology handoff newest
docs/superpowers/plans/2026-11-10-canary-hit-viewer/handoffs`).
