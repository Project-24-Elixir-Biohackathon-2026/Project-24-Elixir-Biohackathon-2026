# AG-UI chat sessions — design

**Status:** approved by the user (2026-10-29), PR #7. **Latest clarification:** 5.
Read against this repo at `ff3acc3` (`main`, equal to `upstream/main` plus the fork's files and the
optional token cap of upstream PR #9).

**Who reads it:** whoever plans or implements the chat UI in `platform/agui/copilotkit-chat/`, the `agui` and
`run_archive` Ansible roles, and whoever analyses archived AG-UI runs.

**Problem.** The CopilotKit chat (`spe_frontend: agui`) is one conversation that a reload throws away
(`docs/specs/2026-10-15-agui-frontend-design.md`, §6: "no persistence"). Participants cannot keep several
attempts apart, come back to one, or label them, as Open WebUI lets them. And because nothing is stored,
the run archive keeps nothing of an AG-UI run (`platform/coder/README.md`: "The `agui` frontend is not
archived"), so what participants tried is lost for later analysis.

**Decision.** The chat UI gets an Open WebUI-style sidebar of sessions: list, open, new, rename, search,
pin, tags (add, remove, filter), hide and delete. Each session is one JSON file on a `chat-sessions` volume
of the `chat-ui` container. Its conversation is recorded **on the server**, in the CopilotKit runtime
route, from the agent's AG-UI event stream; the browser only changes metadata. Delete removes a session
from the participant's view but keeps the file, marked deleted. `archive.yml` gains an `agui` export that
copies every session and the agent's run log into the run directory, rendered like an Open WebUI run.

## Decisions taken

| # | Decision | Section | Acceptance check |
|---|---|---|---|
| 1 | One JSON file per session, `/data/sessions/<uuid>.json` on volume `chat-sessions`, schema `version: 1`; the image creates `/data/sessions` owned by `node`, so a fresh volume starts writable; root filesystem stays read-only | [Storage](#1-storage-and-the-session-record) | `npm test`: a recorded run produces a file that validates against the schema; `docker build` of the image succeeds and, with a freshly created volume and the compose hardening, a first run is saved; `docker inspect` on an instance: `chat-ui` has `ReadonlyRootfs: true`, exactly one volume mount (`/data`) and tmpfs exactly `/tmp` and `/app/.next/cache` |
| 2 | Session ids are canonical UUIDs; nothing else ever names a file | [Storage](#1-storage-and-the-session-record) | `npm test`: ids like `../x`, `a/b`, upper-case or non-v4 strings get 400 from every route and a refused run from the recorder; no file is created |
| 3 | Writes are atomic (temp file + rename in the same directory) and serialised per session by one process-wide queue that every route bundle shares | [Storage](#1-storage-and-the-session-record) | `npm test`: a write interrupted before the rename leaves the previous file intact; 20 concurrent metadata updates to one session all land; against the built standalone server, `PATCH`es overlapping a run's finalisation all land and the run's messages too |
| 4 | The conversation is recorded by the server from the run stream, once per run, whatever its outcome; at most one run per session at a time; finalisation merges into the latest record | [Recording](#2-recording-and-the-session-api) | `npm test` with scripted event sequences: finished, `RUN_ERROR`, agent HTTP error before streaming, stream error, EOF without a terminal event, the stop button (`RUN_ERROR` with `code: "abort"` once the agent's response headers have arrived, or a raw `AbortError` before them: clarification 1), unsubscription before a terminal event, and terminal event followed by unsubscription each leave `messages` and exactly one `runs[]` entry with the status of §2's table; a second run on a running session is refused and never reaches the agent; `DELETE` or `PATCH {title}` during a run survive its finalisation; end-to-end against `fake_agent.py`: closing the tab mid-run leaves the whole run on disk, status `completed` |
| 5 | The browser changes metadata only, through `/api/sessions` (`GET` list, `GET`/`PATCH`/`DELETE` one); no `POST`: a session exists once its first run is recorded | [Recording](#2-recording-and-the-session-api) | `npm test`: `PATCH` with `messages`, `runs`, `id` or any unknown key gets 400 and changes nothing; a new UUID is absent from `GET /api/sessions` until a run on it ends |
| 6 | Delete is a soft delete: `deleted_at` set, the session gone from every API answer and refused for new runs, the file kept and archived; a run already in progress is not cancelled and is recorded into the deleted file | [Recording](#2-recording-and-the-session-api) | `npm test`: after `DELETE`, list omits it, `GET`/`PATCH`/`DELETE` give 404, a run on its id ends with `RUN_ERROR` and does not reach the agent; the file still exists with `deleted_at` |
| 7 | Titles start as the first user message cut to 60 characters and are never overwritten once the user renames | [Storage](#1-storage-and-the-session-record) | `npm test`: auto title after the first run; after `PATCH {title}` (`title_source: "user"`) a later run leaves it unchanged |
| 8 | Tags are normalised (trim, lower-case, `[a-z0-9._-]`, ≤ 32 chars, ≤ 20 per session, de-duplicated) | [Storage](#1-storage-and-the-session-record) | `npm test`: table of inputs → stored tags or 400 |
| 9 | The sidebar, in Open WebUI's look and behaviour (clarification 4): new chat, title search with Open WebUI's `tag:` filter (all named tags must match), pinned first then date groups, a popover row menu (rename, pin, tags, hide, delete with confirmation) that closes on outside click and Escape, show-hidden toggle; the open session is in the URL (`?session=`) | [Sidebar](#3-the-sidebar) | Playwright run against `fake_agent.py`: each action, then a reload reopens the same session with its tool cards; outside click, Escape and opening another row close the menu and commit or end an edit; screenshots (light and dark) in the slice's handoff |
| 10 | Switching session and New chat are disabled while a run is in progress; after a run ends the list is reconciled until it shows that run | [Sidebar](#3-the-sidebar) | Playwright: during a scripted slow run both controls are disabled; after stop they are enabled, the stopped run is recorded as `cancelled` and a new session's row appears, also with the save delayed by a test hook |
| 11 | `archive.yml` exports, for `spe_frontend: agui`, every session file (hidden and deleted included) and the agent's `runs.jsonl`, after stopping `chat-ui` and then `agent` so no run is in progress or unsaved; an absent run log is allowed, a missing `chat-ui` container fails the export | [Archive](#4-the-archive) | On the dev VM: `archive.yml` after the Playwright run gives a run directory with one `agui-sessions/<id>.json` per file on the volume and `agent-runs.jsonl`; `archive.yml` during a slow run has that run, `cancelled`, in both; on a fresh instance with zero runs it succeeds with an empty `agui-sessions/` and no `agent-runs.jsonl` (the run log's copy fails with `Could not find the file`, which the export accepts); with `chat-ui` removed, `archive.yml` fails and `destroy.yml` deletes nothing |
| 12 | `write_agui_run.py` renders the bundle in the Open WebUI run layout: `index.md`, `chats/NN-<title>.md` and `.json`, plus the raw files; re-runnable on an archived run; no run log or no sessions is a valid bundle | [Archive](#4-the-archive) | `pytest platform/dev/tests -k agui_run`: a fixture with active, hidden and deleted sessions renders the expected index rows and state, a deleted marker, fenced tool calls; a bundle with no sessions and no run log renders an index saying so; a second run on the output directory gives identical files |
| 13 | Session files and the archive never hold what comes from the request headers or the chat UI's configuration (the agent key); message content is stored unchanged, not redacted | [Security](#5-security-and-limits) | `npm test`: a run whose request carries `Authorization: Bearer <k1>` and whose runtime is configured with agent key `<k2>`, neither in the messages, leaves neither in the file; `checks.yml`'s key scan extended to the volume as a detector |
| 14 | Model text is rendered as text in the sidebar and fenced in the archive with a fence longer than any backtick run inside | [Security](#5-security-and-limits) | `npm test`/Playwright: a title of `<img src=x onerror=…>` shows as literal text; pytest: tool results containing a line of three, four and six backticks each render inside a longer fence (`write_run.py` too) |
| 15 | No-cost instance check: the session API answers | [Testing](#6-testing) | `verify.yml` on an `agui` instance: "Session API answers" passes (`GET /api/sessions` → 200, JSON list) |

## Early output

The plan builds first (slice 2, after slice 1's store and recorder), against `platform/dev/fake_agent.py`
(no model calls): **the sidebar with three sessions** (one tagged and pinned, one hidden, one deleted) **and the run directory `archive.yml`
writes for them** (`index.md` and one `chats/NN-*.md`). The user looks at both: the page for whether the
sidebar is the Open WebUI subset they want (decision 9), the run directory for whether it is what they
would read when analysing what participants tried (decision 12). Either can change the layout, the row
menu or what the archive renders, before the rest is built on it.

## Glossary

| Term | Meaning |
|---|---|
| session | one conversation in the sidebar; one AG-UI thread; one file on the volume |
| thread id | the AG-UI `threadId` of a session's runs; equal to the session id, a UUID chosen by the browser |
| recorder | the server-side hook on the `spe` agent's AG-UI stream that writes `messages` and `runs[]` |
| metadata | `title`, `tags`, `pinned`, `hidden` (changed by the browser) and `deleted_at` (set by `DELETE`) |
| hidden | removed from the default list, shown with *Show hidden*; still openable and editable |
| deleted | `deleted_at` set: invisible to the participant and the API, kept on disk and in the archive |
| run log | the agent's `runs.jsonl` (`platform/agui/pydantic-ai-agent/README.md`, *Run log*) |

## 1. Storage and the session record

Each session is one file, `/data/sessions/<id>.json`, on a new named volume `chat-sessions` mounted at
`/data` in `chat-ui` (`roles/agui/templates/docker-compose.yml.j2`). The app runs as `node` (uid 1000)
without the rights to fix ownership, so the image creates it: the Dockerfile runs
`install -d -o node -g node -m 0700 /data /data/sessions`, and Docker copies that directory, with its owner,
into the named volume when it is first mounted empty. `/data/sessions` therefore exists on every instance,
before any run. The container keeps `read_only: true`, its tmpfs mounts (`/tmp`, `/app/.next/cache`),
`cap_drop: ALL`, `no-new-privileges` and its limits.

The new code lives in `lib/` beside `app/`; the Dockerfile copies `lib/` into the build stage and
`.dockerignore` admits it (but not `lib/*.test.ts`). The image build is part of slice 1's checks, because
`npm run build` in the checkout passes even when the image cannot resolve `lib/`.

`<id>` is the session's thread id: a canonical lower-case UUID (v4, as `crypto.randomUUID()` makes). The
store refuses every other string before building a path, so no request input reaches the filesystem
except as a validated UUID.

```json
{
  "version": 1,
  "id": "6f1c0d2e-…",
  "title": "List the home directory",
  "title_source": "auto",
  "tags": ["exfil", "dns"],
  "pinned": false,
  "hidden": false,
  "created_at": "2026-10-29T10:02:11Z",
  "updated_at": "2026-10-29T10:14:40Z",
  "deleted_at": null,
  "messages": [],
  "runs": [{ "run_id": "…", "started_at": "…", "ended_at": "…", "status": "completed" }]
}
```

- `messages` is AG-UI `Message[]` (user, assistant with tool calls, tool results) exactly as the run ended
  with it; reopening a session passes it to `agent.setMessages()` unchanged.
- `runs[]` has one entry per recorded run; `status` is `completed`, `failed` or `cancelled`, as in the run
  log. `run_id` and the file's `id` (= `thread_id`) join a session to its run-log lines. The run log stays
  the authoritative record of tool calls; the session is the conversation as the participant saw it.
- `title`: the first user message's text, whitespace collapsed, cut to 60 characters (`title_source:
  "auto"`), set when the session's first run is recorded; `"Untitled"` if it has no text. A `PATCH` sets
  `title_source: "user"`; the recorder never changes a user title. Titles are at most 200 characters.
- `tags`: each trimmed, lower-cased, matching `[a-z0-9._-]{1,32}`, at most 20, de-duplicated, kept in the
  order given. An invalid tag makes the whole `PATCH` fail with 400.
- `updated_at` changes on every write; the list is ordered by it, newest first.

**Writes** go to `<id>.json.tmp-<random>` in the same directory, then `rename` over `<id>.json`, so a file
is never half-written. A per-id promise chain serialises writes to one session (read-modify-write
included). Next.js bundles each route separately, so a module-level map would give the session routes and
the CopilotKit route a queue each: the queue is kept on `globalThis` under `Symbol.for("spe.sessions.queue")`
and every bundle uses that one. `chat-ui` is one Node process (`node server.js`), so no cross-process lock
is needed; the spec assumes it stays one, and the plan notes it next to the queue. The same process-wide
object holds the set of sessions with a run in progress (§2).

Each run rewrites the whole file. A long session with large tool results (each already capped by the
agent's `tools.max_output_bytes`) stays within a few MB; there is no size limit per file (see
*Security and limits*).

## 2. Recording and the session API

### Recorder

The `spe` agent in `app/api/copilotkit/[[...slug]]/route.ts` gets a recorder on its AG-UI stream: AG-UI
`Middleware` (`runNextWithState`, which yields the messages after each event) attached with
`agent.use(...)`. The runtime clones the agent per request (`cloneAgentForRequest`); read in CopilotKit
1.79 and `@ag-ui/client` 1.0.2, `AbstractAgent.clone()` copies `middlewares` and the in-memory runner
calls `runAgent()`, which applies them, so the middleware survives the clone. The plan's first task pins
that with a test. The middleware object is shared by every clone, so it keeps no per-run state: each call
of its `run()` makes a fresh run state (messages, status, a `finalised` flag) in its own closure.

The in-memory runner runs the agent **detached** from the browser's request: when the client goes away the
run is not cancelled, it runs to its end. Only the stop button (the runtime's `/stop`, the runner's
`stop`) cancels a run.

For each run:

1. **Admit.** Validate `input.threadId` as a UUID. Then, under the session's queue, read the session and
   check the process-wide set of running sessions. Refuse the run if the id is invalid, the session is
   deleted, or it already has a run in progress (another tab, a second request): emit `RUN_STARTED` then
   `RUN_ERROR` ("invalid session" / "this session was deleted" / "this session is already running") and do
   not call the agent. Otherwise add the id to the running set, which also covers a new session that has no
   file yet. A missing file is a new session.
2. **During.** Keep the latest messages from each event.
3. **Finalise**, exactly once per run, on the first of the terminations below; any later one (a terminal
   event followed by teardown, say) does nothing. Under the session's queue: **re-read the file** (it may
   have changed since admission), set `messages`, append one `runs[]` entry, set `created_at` and the auto
   title if the file is new, set `updated_at`, and keep everything else as it is now on disk: a title
   renamed, tags changed or `deleted_at` set during the run all survive. Then remove the id from the
   running set.

   | Termination | `status` |
   |---|---|
   | `RUN_FINISHED` | `completed` |
   | `RUN_ERROR` with `code: "abort"` (the stop button, once the agent's response headers have arrived) | `cancelled` |
   | the stream errors with a raw `AbortError` (the stop button, before the agent's response headers arrive: clarification 1) | `cancelled` |
   | any other `RUN_ERROR`, or the stream errors with any other error (including an HTTP error from the agent before any event) | `failed` |
   | the stream completes without a terminal event | `failed` |
   | unsubscribed before a terminal event | `cancelled` |

   On a terminal event or a stream error the write completes before that event is passed on; on
   unsubscription it runs after. A write error is logged on the server (`console.error`, no message
   content); the only change it makes to the stream is the `spe.session_save_failed` event (*Security and
   limits*). When no client is listening any more, the server log is the only trace.

A run refused at admission writes nothing. The agent's run log records every run that reaches the agent's
own run recorder; a run the agent refuses before that (its 503s, for instance) is only in the session, as
`failed`.

**What the record means.** AG-UI clients send the whole history with every run, and the agent trusts it
(`pydantic-ai-agent/README.md`, *Runs*). So `messages` is exactly what the agent was sent plus what it
returned. A participant who rewrote the browser's history would appear as that rewritten history: the
record says what the agent saw, not more. The run log's per-run tool calls are the cross-check.

### Session API

Routes under `app/api/sessions/`, beside `/api/copilotkit`:

| Call | Answer |
|---|---|
| `GET /api/sessions` | `200`, a JSON list of metadata (`id`, `title`, `tags`, `pinned`, `hidden`, `created_at`, `updated_at`, and `last_run_at`: the last run's `ended_at`, `null` before the first), deleted sessions left out, hidden ones included, newest `updated_at` first, at most 1000 |
| `GET /api/sessions/{id}` | `200` with the full record minus `deleted_at` and `runs`; `404` if missing or deleted |
| `PATCH /api/sessions/{id}` | body: any of `title`, `tags`, `pinned`, `hidden`; `200` with the new metadata; `400` for an unknown key, a wrong type or an invalid value (nothing changed); `404` if missing or deleted |
| `DELETE /api/sessions/{id}` | sets `deleted_at`; `204`; `404` if missing or already deleted |

`DELETE` during a run does not cancel it: the run goes on and is recorded into the deleted file
(*Finalise* above), which stays invisible. An id that is not a UUID gets `400`. Bodies over 16 KB get `413`. Error bodies are
`{"error": "<generic message>"}` and never contain paths or stack traces; details go to the server log.

**No authentication of its own.** The chat UI has none: it is reached only through the SSH tunnel to
`127.0.0.1:{{ spe_agui_ui_port }}` or the Coder proxy, one participant per instance. The session API sits
behind the same boundary. If an instance ever serves several participants, sessions need an owner; that
is out of scope here (*Out of scope*).

## 3. The sidebar

Plain React and CSS in `app/` (no new dependencies); all session data is rendered as React text.

- **Look:** Open WebUI's sidebar and chat chrome, finished to the standard of claude.ai and chatgpt.com
  (clarification 4): its gray scale, type sizes, row and menu geometry and transitions, light and dark
  (`prefers-color-scheme`), Heroicons-style inline SVG icons; the CopilotKit chat restyled to the same
  palette. Still plain React and CSS.
- **Layout:** a left sidebar (about 260 px, collapsible) and the chat to its right. Top to bottom: *New
  chat*; a search box filtering by title (case-insensitive substring, in the browser), where Open WebUI's
  `tag:<name>` terms filter by tag (several must all match) and typing `tag:` suggests the tags in use;
  the list, pinned first, then grouped *Today*, *Yesterday*, *Previous 7 days*, *Older* by `updated_at`,
  each row with its title only (as in Open WebUI), the open one highlighted, `⋯` shown on hover, focus,
  the open row and the row whose menu is open (on a touch screen, `hover: none`, always); at the bottom a *Show hidden* toggle and the note "Deleted
  sessions are kept in the run archive."
- **Row menu (`⋯`):** a popover anchored to the button, one open at a time; it closes on a click outside,
  Escape, choosing an item, opening a session or *New chat*; Escape and a choice return focus to its `⋯` (a
  click outside leaves it where the click put it); arrow keys move between items. *Rename* (inline in the row,
  also by double-click; text selected; Enter, Tab or a click outside saves, Esc cancels), *Pin* / *Unpin*, *Tags* (Open WebUI's tag editor: the session's tags as pills, each
  removed by its ×, and an "Add a tag…" input whose suggestions are the tags in use; Enter adds), *Hide* /
  *Unhide*, *Delete* (a dialog "Delete chat?" with "This removes it from your list. It is kept in the run
  archive.", *Cancel* and *Delete*; Escape cancels, wherever focus is). The page-wide Escape handlers skip a key an
  earlier handler already took (`defaultPrevented`).
- **Chat header:** replaces today's one-line banner: a quiet row with the session's title (*New chat*
  before the first run), renamable in place, and the same `⋯` menu. No banner sentence: the note that this
  is the SPE agent and that every tool call is shown is the muted line under the composer, where claude.ai
  and chatgpt.com put theirs.
- **Open session in the URL:** `?session=<id>`. Loading the page with it fetches the session; without it,
  or with an id that answers 404, the page starts a new session (and drops the parameter).
- **Opening a session:** `GET /api/sessions/{id}`, then CopilotChat's `threadId` set to the id and
  `agent.setMessages(messages)`; the tool cards render again from the stored tool-call messages. **New
  chat:** a fresh `crypto.randomUUID()` and an empty history; the session joins the list when its first
  run is recorded.
- **During a run** (the agent's `isRunning`), switching and *New chat* are disabled, so a run never ends
  in a session the participant has left. CopilotChat's stop button ends the run (recorded `cancelled`).
  This is a convenience: the server's one-run-per-session admission (§2) is what keeps two tabs from
  overwriting each other.
- **Refresh:** the list is fetched on load, after each run ends and after each metadata change; no polling.
  A run that ends with a terminal event or a stream error — the stop button's included, as `RUN_ERROR`
  `code: "abort"` once the agent's response headers have arrived, or, on a stop clicked earlier, as a raw
  `AbortError` on the stream's own error path (clarification 1); either way `cancelled` — is saved before
  that event is passed on to the browser, so the fetch after it finds the run, or the
  `spe.session_save_failed` event has
  already said it was not saved. Only a run whose stream to the browser ends early (the connection dropped
  while the detached run goes on, §2) is saved after the browser's run has ended, and so can land after that
  fetch: after a
  run ends, until the list shows the open session with a `last_run_at` not older than the run's start, the
  page fetches it again, up to 5 times at 500 ms. If it still does not, the error bar says "this session
  could not be saved".
- **Errors:** a failed API call shows in the existing error bar; the open chat is never cleared. A run
  refused by the recorder shows its `RUN_ERROR` there as today. If the runtime is still not ready after 15 s,
  the bar says "The agent runtime is unreachable; reload the page.", and the message goes once it is ready.

Every current text that says the AG-UI chat keeps no history is rewritten in the slice that changes the
behaviour: `README.md` ("A reload starts a new conversation"), `docs/getting-started.md` ("a reload
starts a new conversation"), the chat header, and `docs/specs/2026-10-15-agui-frontend-design.md`, whose §6
line "no persistence (a reload starts a new chat)" and §2's "server-side sessions" out-of-scope entry are
cut down to a pointer to `platform/agui/copilotkit-chat/README.md`, *Sessions* (that spec goes upstream,
so the pointer names no fork-only file).

## 4. The archive

Same shape as the Open WebUI path in `roles/run_archive`: export on the VM, fetch, write on the
controller.

**Export** (`tasks/export.yml`, new block when `spe_frontend == 'agui'`; `archive.yml`'s play name
becomes "Export the frontend's chats"):

1. **Barrier.** Copying files while runs go on gives no consistent bundle: a run finishing after its
   session was copied would be missing from the archive and then destroyed with the volume. So first
   `docker compose -p spe-frontend stop -t 30 chat-ui`, then `… stop -t 30 agent`. On `SIGTERM` the chat
   UI refuses new runs, stops every run in progress (each is finalised `cancelled`), waits for the session
   queue to drain and exits (a handler registered in `instrumentation.ts`; the image sets
   `NEXT_MANUAL_SIG_HANDLE=true`, because Next.js's own handler closes the server and exits without
   waiting for a detached run's save). The agent, stopped second, has then seen its last
   request and closed its run log. A missing `chat-ui` container fails here, and so does a stop that did not
   end cleanly: each service running before the barrier must have exited 0 (`docker compose ps -a --format
   '{{.Service}} {{.ExitCode}}'`), since a drain timeout (the chat UI exits 1) or a kill after `-t 30` (137)
   leaves `stop` itself at rc 0. The containers are started again either way.
2. **Copy** from the stopped containers: `docker compose -p spe-frontend cp chat-ui:/data/sessions
   <tmp>/sessions` (always present: the image creates it, §1) and `… cp agent:/var/lib/spe-agent/runs.jsonl
   <tmp>/agent-runs.jsonl`. Only an absent run log is tolerated (no run reached the agent yet): the copy's own
   `Could not find the file` error is accepted, since the stopped agent cannot be asked whether the file
   exists; any other copy error fails the export.
3. **Restart** both (`docker compose -p spe-frontend start agent chat-ui`), so `archive.yml` run on its
   own leaves a working instance; under `destroy.yml` they are removed right after.
4. Pack `<tmp>` into `/tmp/spe-agui-export.tar.gz`, fetch it to
   `{{ spe_output_dir }}/archive-bundle-agui.tar.gz`, remove both from the VM.

Every file is exported, hidden and deleted included. The containers are still up when `archive.yml` starts
(`destroy.yml` imports it first; the Coder stop runs `destroy.yml`). If any step fails, `archive.yml` fails
and `destroy.yml` deletes nothing, as for Open WebUI today.

**Write** (`tasks/write.yml`): when the agui bundle exists, unpack it and run
`files/write_agui_run.py <bundle dir> <run dir>` (stdlib only, like `write_run.py`):

```
<run dir>/
  run.yml                    as today
  index.md                   sessions table: #, title, tags, created, runs, state (active / hidden / deleted <time>)
  chats/NN-<slug>.md         user and assistant text; each tool call with fenced arguments and result
  chats/NN-<slug>.json       the session record as stored
  agui-sessions/<id>.json    the raw files, untouched
  agent-runs.jsonl           the agent's run log
```

`NN` follows `created_at`. A deleted session's `.md` opens with "Deleted by the participant at <time>."
Slugs and fences come from `write_run.py` (imported, same directory). Its `fence()` today picks three or
four backticks, which content with four escapes; it is changed to a fence one longer than the longest run
of backticks in the content (at least three), which fixes the Open WebUI path too. A bundle with no
sessions gives an `index.md` saying no session was recorded; without `agent-runs.jsonl` the index says no
run reached the agent and no run log is written. `index.md` says that the AG-UI frontend has no run report.
Given an archived run directory (`agui-sessions/` present, `agent-runs.jsonl` if there was one), the script re-renders it
in place. The *Overview without a chat export* task stays for runs with no bundle (no frontend), with its
text corrected. `archive-bundle-agui.tar.gz` is removed after writing, like `archive-bundle.json`.

The same slice rewrites every current text that says the AG-UI chat is not archived or has no sessions:

- `platform/coder/README.md`: the *Known limitations* entry "The `agui` frontend is not archived", the
  `run_archive` row ("Exports OpenWebUI"), step 4 ("the AG-UI chat has no notes or tags yet"), the table
  of archived files (add the agui files) and the *Re-render an old run* row (add `write_agui_run.py`);
- `platform/coder/template/testbeds/agui.yml` ("Chats are not archived yet."), shown in the preset list;
- `platform/coder/template/main.tf`, the `frontend` parameter's description (archiving named for
  `openwebui` only);
- `platform/ansible/playbooks/archive.yml`'s header comment and `inventory/group_vars/all.yml`'s
  *Run archive* comment (chats for `openwebui` only);
- `platform/ansible/README.md`; `AGENTS.md`, *AG-UI agent frontend* ("Not done yet: archiving its chats on
  stop");
- `docs/getting-started.md`'s *Private configuration* table: a row for the volume
  `spe-frontend_chat-sessions` and the run directory's `agui-sessions/` and `agent-runs.jsonl`, both
  **not** shareable (they contain canaries), like the run log.

## 5. Security and limits

- **Isolation unchanged.** `chat-ui` gains only `/data`. The agent and sandbox cannot reach the volume
  (other containers; the sandbox is on `tools` only). The model supplies text, never a path.
- **No keys from the chat UI in sessions.** The recorder stores `messages` and run metadata, never request
  headers, the agent key (`AGENT_API_KEY`, the only secret `chat-ui` holds) or the runtime configuration.
  It does **not** redact message content: `messages` stays exactly what the agent was sent and returned
  (§1), so whatever a participant pasted or a tool returned is kept, as in the run log. Tool results may
  contain canary values and dataset content, as Open WebUI's export does; the run directory's existing
  handling applies to `agui-sessions/` and `agent-runs.jsonl` (outside git, treated like `canaries.json`).
- **Key scan as a detector.** `checks.yml`'s key check gains the volume: no file under `/data/sessions`
  contains the agent key, the LLM key or the sandbox key. The LLM and sandbox keys are not in `chat-ui`, so
  a hit there means one reached the conversation through the agent or a tool: the check fails and reports
  it, the recorder does not hide it.
- **Untrusted text.** Titles, tags and messages render as React text, never as HTML; the chat's own
  message rendering is unchanged. `chats/*.md` fences tool arguments and results with a fence longer than
  any run of backticks inside.
- **Input limits:** `PATCH` bodies ≤ 16 KB, titles ≤ 200 characters, tags as in §1, ids UUID-only, the list
  capped at 1000.
- **Size and failures.** No per-file limit. A failed write (disk full) is logged; the next list fetch
  cannot show what was not written, and the error bar says "this session could not be saved" when the
  page learns of it: the recorder emits a `CUSTOM` event named `spe.session_save_failed` before the
  terminal event (the write happens before the terminal event is passed on, for this reason), or the
  reconciliation of §3 gives up. The run log still has the run if it reached the agent.
- **Lifetime.** Only `destroy.yml` removes the volume (*Compose stacks down, with their volumes*), and only
  after `archive.yml` succeeded.

## 6. Testing

- **Chat UI unit tests**, no new dependencies: the store, validation and recorder live in `lib/`
  (`lib/sessions.ts`, `lib/recorder.ts`), with `lib/*.test.ts` run by `node --test` (Node 24 strips types)
  as `npm test`. They cover decisions 1–8, 13 and the text rendering of 14. `npm run build` stays the type
  check. Two properties need the built server, not a store instance: the queue shared across route bundles
  and per-run recorder state across clones (decision 3), checked against `node .next/standalone/server.js`
  with `fake_agent.py` behind it. The image is built (`docker build`) as part of slice 1's checks. `AGENTS.md`, *Running things*, gains `(cd platform/agui/copilotkit-chat && npm ci && npm test)`.
- **Archive writer:** `platform/dev/tests/test_write_agui_run.py` (pytest) over a fixture bundle with
  active, hidden and deleted sessions and a run log, and an empty bundle (decision 12, 14).
- **Fake agent:** `platform/dev/fake_agent.py` gains a slow scripted run (a user message containing
  "slow" streams its answer over about 10 s), for decisions 4, 10 and 11.
- **End to end, no model:** the built chat UI against `platform/dev/fake_agent.py`, driven by Playwright
  through every sidebar action (decisions 9, 10), with the files checked after each step; screenshots and
  the result in the slice's handoff. This is also the early output.
- **On an instance:** the new no-cost check in `roles/agui/tasks/checks.yml` (decision 15) and the
  extended key check (decision 13); then, on the dev VM, `archive.yml` after the Playwright run, during a
  slow run, and on a fresh instance with no run (decision 11). The existing smoke run calls the agent directly, not through `chat-ui`, and stays as is.
- **One paid check, with the user's OK at the time:** a two-turn chat in the browser on the dev VM
  (`claude-haiku-5-5`), then `archive.yml`; about $0.01.

## Out of scope

- **Sessions with owners** (several participants per instance): needs identity in the chat UI; in
  `BACKLOG.md` (chat sessions with owners), next to the per-user budgets item, as both wait for
  multi-participant instances.
- **A run report** in the CopilotKit chat (Open WebUI's "Run report" note): in `BACKLOG.md`; `index.md`
  states that there is none.
- **Upstream.** The code and its READMEs refer to nothing fork-only, so the work can go upstream as one PR
  cut from `upstream/main` (`AGENTS.md`, *Contributing upstream*), carrying a README section instead of this
  spec.
- **Branching, editing or regenerating messages**, export from the UI, full-text search over messages,
  folders: Open WebUI features not asked for.

## Inputs for the plan

- **Slices, in order.** The early output comes first, so it is slice 2, and nothing that depends on
  decisions 9 and 12 comes before it:
  1. Store, API and recorder with unit tests (decisions 1–8, 13); the volume in the compose template and
     `/data/sessions` in the image, `lib/` in the Dockerfile and `.dockerignore`, the image build; the slow
     run in `fake_agent.py`; the built-server test of the shared queue; `npm test` in `AGENTS.md`,
     *Running things*.
  2. **The early output:** the sidebar's list, *New chat*, opening a session, the URL and the row menu
     (decision 9's core, decision 14's text rendering); the archive export with its barrier and
     `write_agui_run.py` with its tests and the `fence()` change (decisions 11, 12, 14); every doc this
     makes stale (§3, §4). It ends with the Playwright run producing three sessions (tagged and pinned,
     hidden, deleted) and `archive.yml`'s run directory for them, for the user to look at.
  3. Title search, tag filter, date groups, *Show hidden*, the chat header, disabled controls and the
     list reconciliation (decisions 9, 10); the full Playwright run; the instance checks (decisions 13, 15)
     and the dev-VM archive checks (decision 11); the paid check with the user's OK.
- **First task of slice 1:** pin with a test that the recorder middleware survives `cloneAgentForRequest`
  and keeps per-run state per clone. This is a feasibility gate: if it fails, and no `HttpAgent` subclass
  overriding `run()` and `clone()` works either, the plan stops and the spec gets a clarification with a
  revised design. A browser-side save is not a fallback: it would break decisions 4 and 5.
- **Slice 2's archive task** checks that Next.js 16's standalone server leaves the `SIGTERM` handler time to
  drain within `stop -t 30` (§4, *Barrier*).
- How CopilotChat 1.79 reacts to a changed `threadId` together with `agent.setMessages()` (remount via
  `key`, or not) is checked in slice 2's first task.
- **The canary ladder's isolation** (plan `2026-10-22-canary-eval-ladder`, slice 2) lists every volume of
  the `spe-frontend` compose project and tests the list against the template. The new volume is **not
  restored** between evaluation cases (evaluations call the agent directly, never `chat-ui`). Slice 1,
  which adds the volume, adds `spe-frontend_chat-sessions` to `isolation.NOT_RESTORED` if
  `isolation.py` is on `main` by then; the ladder's slice-2 task text and spec part 05 already name it
  (rewritten in PR #7).

## Clarifications

1. **The stop button arrives as `RUN_ERROR` with `code: "abort"`, or a raw `AbortError` before the agent's
   response headers, and either way is recorded `cancelled`** (2026-10-30, amended 2026-11-02; slice 1/3,
   then slice 3/3's header task). The runner's `stop` calls `HttpAgent.abortRun()`, which aborts the agent's
   request. `@ag-ui/client` 1.0.2's HTTP transform converts the resulting `AbortError` into a `RUN_ERROR`
   event with `code: "abort"` only inside its SSE parser, which subscribes once the HEADERS frame has
   arrived (read from the package's minified bundle, `dist/index.mjs`: the outer byte-stream subscription's
   own `error:` handler passes anything through unconverted until a HEADERS frame has been seen); a stop
   clicked earlier — during admission, or after the request was sent but before the agent's response headers
   arrive — surfaces instead as the fetch's own raw `AbortError`, reaching the recorder's stream through its
   `error:` callback (never as a `RUN_ERROR` next() event). `lib/recorder.ts`'s `isAbort()` tells this apart
   from an actual failure (a dropped connection, a malformed frame) by `error.name === "AbortError"`, the one
   name the Fetch/DOM spec gives this case and nothing else in the chain produces; the Fetch/DOM spec gives a
   *timeout* its own different name (`TimeoutError`, from `AbortSignal.timeout()`), and neither
   `@ag-ui/client` 1.0.2 nor this project's fetch calls use one, so there is no name clash to confuse a stop
   with. Unsubscription before a terminal event stays `cancelled`, as before. *Reason:* read in
   `@ag-ui/client` 1.0.2 and pinned by `lib/clone.test.ts` (post-headers) and `lib/recorder.test.ts`
   (pre-headers, with `lib/test-agent.ts`'s `headerDelayMs`); the pre-headers gap was found by
   `platform/dev/e2e/sessions.py`'s `check_stop` recording `failed` on a stop clicked very soon after the
   sidebar showed the run as started. *Amends:* §2 (termination table), decision 4, §3 *Refresh* (which run
   can be saved after the fetch). *Status:* folded.
2. **The chat UI's `SIGTERM` handler replaces Next.js's** (2026-10-30; slice 2/3). The image sets
   `NEXT_MANUAL_SIG_HANDLE=true` and `lib/shutdown.ts` drains the sessions and exits by itself. *Reason:* Next.js
   16.4.1's handler (`start-server.js`) closes the HTTP server and calls `process.exit(143)`; a run whose browser has
   gone holds no response open, so its save would be cut off. *Amends:* §4 *Export*, step 1 (*Barrier*).
   *Status:* folded.
3. **An absent run log is recognised by the copy's own error, not by a check before it** (2026-10-30; slice 2/3).
   The export copies `agent:/var/lib/spe-agent/runs.jsonl` from the stopped agent and accepts only `docker compose
   cp`'s `Could not find the file` error; any other error fails the export. *Reason:* the agent is stopped by the
   time of the copy, so nothing can be checked inside it, and a check before stopping it races with its last write
   (Docker Compose 5.5.1: `cp` copies from a stopped container; a missing file fails with rc 1 and that message).
   *Amends:* §4 *Export*, step 2; decision 11 (acceptance check). *Status:* folded.
4. **The sidebar and chat follow Open WebUI's look and behaviour** (2026-11-02; slice 2/3, at the user's request
   on the early output). The row menu is a popover with Open WebUI's close and focus rules (outside click,
   Escape, choosing an item, opening a session; focus back to `⋯`); a rename is committed by Enter or a click
   outside and cancelled by Esc; tags are edited in Open WebUI's tag editor (pills with ×, "Add a tag…" with
   suggestions) and filtered with its `tag:` search syntax instead of tag chips; rows show the title only; the
   chat header is a title row and the "SPE agent — every tool call is shown" banner becomes the line under the
   composer. *Reason:* the user found the first sidebar's menu and rename left open after a click elsewhere,
   and asked for Open WebUI's look, polished like claude.ai and chatgpt.com, with identical tag features.
   Open WebUI (`main`, read 2026-11-02: `Sidebar/ChatItem.svelte`, `ChatMenu.svelte`, `SearchInput.svelte`,
   `common/Tags.svelte`, `chat/Navbar.svelte`) renders no tag editor in its menu today; the editor component
   it ships for that is the one followed. *Amends:* §3 *Look*, *Layout*, *Row menu*, *Chat header*; decision 9.
   *Status:* folded.
5. **The barrier fails on a stopped service's exit code** (2026-11-02; slice 2/3, review round on #10). After
   the two stops, the export reads each service's exit code and fails unless every service running before the
   barrier exited 0. *Reason:* `docker compose stop` returns 0 whether the chat UI drained (exit 0), timed out
   (exit 1) or was killed after `-t 30` (137), so a barrier that did not hold went unnoticed and the archive could
   lack the last run before `destroy.yml` drops the volume (§4: any failed step fails `archive.yml`). A service
   already stopped before the barrier keeps an old exit code, so it is not checked. *Amends:* §4 *Export*, step 1.
   *Status:* folded.
6. **The list reconciles a run by `last_run_at`, not `updated_at`** (2026-11-02; `change/agui-chat-minors`). Each
   list entry carries `last_run_at`, the session's last run's `ended_at`, and the page's reconciliation waits for
   that instead of `updated_at`. *Reason:* a rename, pin, tag or hide made while a run is in progress also moves
   `updated_at`, so a dropped stream plus a failed save could pass as saved (`BACKLOG.md`, from PR #11's local
   review). *Amends:* §2 *Session API* (`GET /api/sessions`), §3 *Refresh*. *Status:* folded.
7. **Keyboard and touch minors: Tab saves a rename, Escape reaches the dialog anywhere, touch shows `⋯`, an
   unreachable runtime is said** (2026-11-02; `change/agui-chat-minors`). Tab out of a rename saves it once focus
   has moved; the delete dialog's Escape listens on the document; the page-wide Escape handlers skip a key already
   taken; under `hover: none` every row shows its `⋯`; after 15 s without the runtime the error bar says so. A
   click outside the menu does not give focus back to `⋯`. *Reason:* the slice 2 and 3 reviews' deferred minors
   (`BACKLOG.md`); refocusing `⋯` after a click outside would take focus from whatever the click landed on.
   *Amends:* §3 *Layout*, *Row menu*, *Errors*; clarification 4's "focus back to `⋯`" (for Escape and a choice
   only). *Status:* folded.
