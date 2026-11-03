# AG-UI chat sessions — design

**Status:** approved by the user (2026-10-29), PR #7; **folded into**
[`docs/specs/2026-10-15-agui-frontend-design/`](../../specs/2026-10-15-agui-frontend-design/README.md) (#19), which
holds the current design (clarification 8). **Latest clarification:** 8.
Read against this repo at `ff3acc3` (`main`, equal to `upstream/main` plus the fork's files and the
optional token cap of upstream PR #9).

**Who reads it:** whoever plans or implements the chat UI in `platform/agui/copilotkit-chat/`, the `agui` and
`run_archive` Ansible roles, and whoever analyses archived AG-UI runs.

**Problem.** The CopilotKit chat (`spe_frontend: agui`) is one conversation that a reload throws away
(`docs/specs/2026-10-15-agui-frontend-design.md`, now a directory, §6: "no persistence"). Participants cannot keep several
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

History: the decisions as approved and amended up to clarification 7. Their current form is the living spec's
[decisions table](../../specs/2026-10-15-agui-frontend-design/README.md#decisions-taken) (clarification 8 maps each
one).

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

Superseded after #19 by [the living spec's *Early
output*](../../specs/2026-10-15-agui-frontend-design/README.md#early-output). The sessions' early output was shown and
accepted
in slice 2/3 (clarification 4).

## Glossary

Superseded after #19 by [the living spec's
*Glossary*](../../specs/2026-10-15-agui-frontend-design/README.md#glossary).

## 1. Storage and the session record

Superseded after #19 by [§13 *The
journal*](../../specs/2026-10-15-agui-frontend-design/13-conversation-record.md#the-journal) and [§6
*Sessions*](../../specs/2026-10-15-agui-frontend-design/06-chat-ui.md#sessions).

## 2. Recording and the session API

Superseded after #19 by [§13 *The run
route*](../../specs/2026-10-15-agui-frontend-design/13-conversation-record.md#the-run-route) and [§6 *Session
API*](../../specs/2026-10-15-agui-frontend-design/06-chat-ui.md#session-api).

## 3. The sidebar

Superseded after #19 by [§6 *The sidebar*](../../specs/2026-10-15-agui-frontend-design/06-chat-ui.md#the-sidebar).

## 4. The archive

Superseded after #19 by [§14 *The archive*](../../specs/2026-10-15-agui-frontend-design/14-archive.md).

## 5. Security and limits

Superseded after #19 by [§6 *Security and
limits*](../../specs/2026-10-15-agui-frontend-design/06-chat-ui.md#security-and-limits).

## 6. Testing

Superseded after #19 by [§9](../../specs/2026-10-15-agui-frontend-design/09-checks.md) and
[§10](../../specs/2026-10-15-agui-frontend-design/10-testing.md).

## Out of scope

Superseded after #19 by [the living spec's *Out of
scope*](../../specs/2026-10-15-agui-frontend-design/out-of-scope.md).

## Inputs for the plan

Superseded after #19 by [the living spec's *Inputs for the
plan*](../../specs/2026-10-15-agui-frontend-design/inputs-for-plan.md).

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
8. **Folded into the living AG-UI spec** (2026-11-03; PR #19). This spec's design now lives in
   `docs/specs/2026-10-15-agui-frontend-design/`; its sections 1–6, *Glossary*, *Early output*, *Out of scope* and
   *Inputs for the plan* are cut to pointers there. Its decisions are carried as the living spec's **19** (1: the
   volume and image part), **20** (5), **21** (6), **22** (7), **23** (8), **24** (4: the detached run and the
   clone), **25** (9), **26** (10), **27** (13), **28** (14), **29** (15) and **30** (11: the barrier part); 2 is
   inside the living spec's 10, 3's queue shared by every route bundle in 12, 4's termination table in 7, and 12's
   identical re-render in 15. Replaced by the conversation record: 1's file format, 3 (atomic rewrite), 4's "at
   most one run at a time" (now 9), 11's copy (15) and 12's renderer (15, 16). *Reason:* the sessions stored the client's
   history, which a participant can forge; the record replaces that storage, and one spec kept current lets the
   AG-UI work be read, reviewed and ported as one package (the living spec's clarification 1). *Amends:* every
   section (cut to a pointer); the decisions table (now history). *Status:* folded.
