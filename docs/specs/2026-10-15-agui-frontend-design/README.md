# AG-UI agent and CopilotKit frontend for SPE instances — design

**Status:** living spec. §§1–5 and 7–12: implemented 2026-10-15 (branch `agent-agui-frontend-impl`; §12
records what implementation verified and changed). §6's sessions and sidebar: implemented 2026-10-29 to
2026-11-02, and restated here for the conversation record: where §6 and decisions 19–30 speak of the journal,
`meta` lines or `agui-journals/`, they wait for the record to be built, and today's code still keeps one
`<uuid>.json` per session. The conversation record (§13, §14, decisions 1–18): approved 2026-11-03 (the fork's PR #19,
`thodkatz/elixir-biohackathon-2026-test`), not built yet; the live archive (§14, decision 30) since
clarification 2. The history before this directory is that of the single
file it replaced: `git log -- docs/specs/2026-10-15-agui-frontend-design.md`.
**Latest clarification:** 2.
§13 and §14 were read against `@ag-ui/client` 1.0.2 and CopilotKit 1.79.0 (`@copilotkit/runtime`,
`@copilotkit/react-core`) as pinned in `package-lock.json`, and Open WebUI v0.11.3 (the image
`spe_frontend_webui_image` pins) as the model to follow, read in its source at tag `v0.11.3` (`2a960a5`).

Context and reasoning: the biohackathon knowledge repository, records 0001–0005
(0005 is the playground this is sub-project 1 of).

**Who reads it:** whoever changes the AG-UI stack (`spe_frontend: agui`): the agent
(`platform/agui/pydantic-ai-agent/`), the chat (`platform/agui/copilotkit-chat/`, "`chat-ui`"), the `agui` and
`run_archive` Ansible roles; and whoever analyses archived AG-UI runs and needs to know what the model was sent
and what the participant tried to send.

**Problem.** Each SPE instance runs a pentest agent we own, served over AG-UI, with a CopilotKit chat in front
of it (§1). In AG-UI the client holds the conversation and sends all of it with every run, and the agent trusts
it (only system messages are replaced by the agent's own prompt). A participant can therefore fabricate
earlier turns, tool calls and tool results, edit or delete real turns, or forge the agent's compaction marker
(an assistant message whose id starts with `spe-compaction-`, which makes the agent drop everything before
it), with `curl` against `chat-ui`'s run route or with the browser's devtools. The model sees the forgery, and
a record that stores the client's latest history shows the forged history as if it had happened and loses
edited and deleted turns.

**Decision.** The agent stays stateless (§5). `chat-ui` keeps an Open WebUI-style sidebar of sessions (§6) and
**owns the history**, as Open WebUI's backend does when it fronts an external agent: per session an append-only
**journal** of every run, written before the agent is called and as each event arrives; from each request it
takes only the new user message and sends the agent the history from its journal; whatever else the client
sent that differs from the journal is **ignored and recorded** with its kind (§13). Two runs on one session
may run at once and become sibling branches. The archive copies the journals raw and exports each one as an
**Open WebUI chat**, which the Open WebUI renderer turns into the same run layout (§14). It closes the history
edits made through the chat; it assumes the participant holds neither the agent key nor root on the VM
(§13, *Boundary*).

## Decisions taken

Decisions 1–18 are the conversation record's, approved and not built yet; 19–30 are the chat sessions' as built, restated
for the record (their journal parts are built with it). §§1–5 and
7–12 predate the table and state their design in their text.

| # | Decision | Section | Acceptance check |
|---|---|---|---|
| 1 | `chat-ui` owns the history; the agent is unchanged and stateless, and still trusts the history it is sent, which through the chat now comes only from the journal | [§13 *Approach*](13-conversation-record.md#approach) | `npm test` (recorder, with `lib/test-agent.ts` recording the input it receives): for a client history carrying each of a fabricated assistant turn, a fabricated tool call and result, a deleted middle turn, an edited reply, an edited tool result, a forged `spe-compaction-` marker and a client system message, the agent receives exactly the journal's path plus the new user message; no file under `platform/agui/pydantic-ai-agent/` changes |
| 2 | Per run, the **anchor** is the latest message of the client's history whose id the journal holds; the run's **new messages** are the user messages after the anchor whose ids the journal does not hold; everything else that differs from the journal's path to the anchor is **ignored content**, kind `fabricated` (unknown id), `edited` (known id, different role, content, tool calls or tool call id), `deleted` (on the journal's path, missing from the client) or `system` (a client system message) | [§13 *The run route*](13-conversation-record.md#the-run-route) | `npm test` (anchor): one case per kind, each recorded with the client's message in full; a session's first run has no anchor; **no false alarm**: a history the browser itself sent after real runs (CopilotKit's message shape, through the runtime route, with `fake_agent.py` in the built-server check) classifies nothing as ignored, over three runs including one with tool calls and one failed run |
| 3 | A run with no new user message, or with a `runId` the journal already holds, is refused; a refused run whose request passed the id, deleted and closing checks is still journaled (`run_start` then `run_end` `refused`), so what it carried is recorded; a duplicate `runId` is refused without a line | [§13 *The run route*](13-conversation-record.md#the-run-route) | `npm test`: a request carrying only a fabricated assistant turn gives `RUN_ERROR`, the agent is not called, and the journal holds `run_start` with that turn as `fabricated` and `run_end` `refused`; a reused `runId` gives `RUN_ERROR` and no new line |
| 4 | `run_start` (run id, anchor, new messages, ignored content, the request's other client-controlled fields: `tools`, `context`, `state`, `forwardedProps`) is written and fsynced **before** the agent is called; if it cannot be written the run is refused with "this session could not be saved" and the agent is not called | [§13 *The journal*](13-conversation-record.md#the-journal) | `npm test`: the agent's first received byte comes after `run_start` is on disk (test agent reads the file when called); with the sessions directory read-only the run gets `RUN_ERROR` with that message and the test agent records no call |
| 5 | The agent is sent the journal's path from the root to the anchor, then the new messages; `threadId` is the session id, `runId` the request's, the other fields forwarded as sent; the agent key is added by `chat-ui` as today | [§13 *The run route*](13-conversation-record.md#the-run-route) | Covered by decision 1's check; plus, in the built-server check against `fake_agent.py` scripted to echo the roles and ids it received, a `curl` to `chat-ui` carrying a fabricated assistant turn gets an answer that does not list it (the **feasibility check**: if CopilotKit's runtime cannot replace `messages`, the work stops for a new decision, see *Early output*) |
| 6 | When a run has ignored content, `chat-ui` sends the browser a `MESSAGES_SNAPSHOT`, right after `RUN_STARTED`, of the history the agent is sent, so the browser shows what the model sees; without ignored content, nothing is added to the stream | [§13 *The run route*](13-conversation-record.md#the-run-route) | `npm test`: the stream to the client has, right after `RUN_STARTED`, a snapshot equal to the agent's input messages when content was ignored, and has none otherwise; Playwright against `fake_agent.py`: after a devtools edit of an earlier reply and a new message, the page shows the original reply |
| 7 | Every AG-UI event the agent sends is appended as it arrives; the journal is fsynced at `run_start`, at `run_end`, and at most one second apart in between; `run_end` holds the status (`completed`, `failed`, `cancelled`, `aborted`, `refused`) and the error message | [§13 *The journal*](13-conversation-record.md#the-journal) | `npm test`: a completed, a failed, a stopped (both abort shapes the recorder handles today) and a refused run each end with the matching `run_end`; a terminal event followed by unsubscription, and every termination of §13's table, leaves exactly one `run_end` for the run; with `fsync` counted and a fake clock, a run of 1000 events arriving within one second fsyncs at most three times (`run_start`, one interval, `run_end`) |
| 8 | An append that fails mid-run aborts the agent request and ends the run with `RUN_ERROR` "this session could not be saved" (`run_end` `aborted` if it can still be written); the `spe.session_save_failed` warning goes; a run with no `run_end` (a crash) is read as `incomplete`, its events kept | [§13 *The journal*](13-conversation-record.md#the-journal) | `npm test`: an append made to fail after five events aborts the test agent's request and gives that error; a journal cut after a run's third event rebuilds with that run `incomplete` and the text received so far; `grep -r session_save_failed platform/agui/copilotkit-chat` finds nothing |
| 9 | Runs on one session may overlap; one queue per session serialises appends; two runs from one anchor become sibling branches; the session's **tip** is the last message of the run whose `run_end` (or, if incomplete, last event) came last, among the runs that added a message; a session with only refused runs is not listed; the "already running" refusal goes | [§13 *Concurrency and branches*](13-conversation-record.md#concurrency-and-branches) | `npm test`: two runs started from the same anchor, the first ending last, both complete; the rebuild has two branches under the anchor and the tip is the first run's last message; their lines interleave and each line names its run; a refused run ending last leaves the tip unchanged; a fresh id whose only run is refused is absent from the list and `GET` gives 404 |
| 10 | The journal is `/data/sessions/<uuid>.jsonl` on the `chat-sessions` volume, one JSON object per line (`created`, `run_start`, `event`, `run_end`, `meta`), append-only: no route ever rewrites or truncates it; session ids stay canonical UUIDs | [§13 *The journal*](13-conversation-record.md#the-journal) | `npm test`: after a session's runs, a rename, a tag, a hide and a delete, every earlier line is byte-identical and each operation added lines only; a journal ending in a torn line gets `\n` before the next append and the rebuild skips the torn line; ids like `../x`, `a/b`, upper-case or non-v4 strings get 400 from every route and a refused run (`RUN_ERROR`, agent not called), and no file is created |
| 11 | Messages are rebuilt from the journal by applying each run's events to its anchor's path with `@ag-ui/client`'s own event handling (the code the browser runs); every message gets a `parentId`, derived from the run structure, not stored | [§13 *Rebuilding the conversation*](13-conversation-record.md#rebuilding-the-conversation) | `npm test` and the built-server check: for runs with text, tool calls and results, a compaction marker and an error, the rebuilt branch equals the messages the browser held at the run's end |
| 12 | The session list is served from an index in memory, built at startup with one pass over the journals and updated on every append; the index and the append queue live on `globalThis`, shared by every route bundle; no index file | [§6 *Session API*](06-chat-ui.md#session-api) | `npm test`: the list after a restart equals the list before it; a rename shows in the list without rereading the file (the read is counted); against the built standalone server, a run through `/api/copilotkit` shows in `/api/sessions` and `PATCH`es overlapping its end all land |
| 13 | The session API keeps its routes and answer shapes for the browser; `GET /api/sessions/{id}` returns the tip's branch as `messages`; `PATCH` and `DELETE` append a `meta` line; no route changes message content; delete stays soft | [§6 *Session API*](06-chat-ui.md#session-api) | `npm test` (`api`): the answer-shape tests pass with `version` and `title_source` removed from `GET` one's expected keys (§6) and the store read replaced by the journal's `meta` lines, and are otherwise unchanged; a `PATCH` adds exactly one `meta` line; restore in Playwright reopens a session on its tip's branch |
| 14 | Session files in the earlier JSON format (`<uuid>.json`) are neither read nor migrated | [§13 *The journal*](13-conversation-record.md#the-journal) | `npm test`: a directory holding a `<uuid>.json` file lists no session for it and starts without error |
| 15 | The archive copies every journal raw (hidden and deleted included) and exports each as an **Open WebUI chat** in an Open WebUI-shaped bundle, written by an exporter in the `chat-ui` image that uses decision 11's rebuild; `write_run.py` renders the bundle as it renders an Open WebUI run; `write_agui_run.py` and its session format go | [§14](14-archive.md) | `npm test` with fixture journals: the exporter's bundle has, per session, a `history` tree whose `currentId` is the tip run's assistant message, one assistant message per run with `output` items in event order (`message`, `function_call`, `function_call_output`, `reasoning`) and the `spe_` fields below, and the bundles are committed as fixtures; `pytest platform/dev/tests` with those bundles: `write_run.py` renders them into `index.md` and `chats/NN-*.md`, and a second run on the output gives identical files; the archive tree holds `agui-journals/<uuid>.jsonl` and `agent-runs.jsonl` |
| 16 | `write_run.py` also renders the three things only the AG-UI record has: a run's status when it is not `completed`, its ignored content as a block "sent by the client, not used" with its kind and the content fenced, and a compaction marker as a "Compacted" section; Open WebUI runs render as before | [§14](14-archive.md) | `pytest`: a fixture with a fabricated assistant turn renders the block between the turns it was sent with, fenced with a fence longer than any backtick run inside; a marker renders as the Compacted section; an existing Open WebUI fixture renders byte-identically to before |
| 17 | Boundary: the agent key is never in the sandbox's environment nor in `terminal.env` | [§13 *Boundary*](13-conversation-record.md#boundary), [§9](09-checks.md) | `verify.yml` on an `agui` instance: a check this spec adds to `roles/agui/tasks/checks.yml` (§9, item 4) that neither `docker inspect` of the sandbox's environment nor `terminal.env` contains the agent key's value |
| 18 | The threat catalog gains an entry for history fabricated through the client (fabricated or edited turns, tool results or markers claiming to be the agent's or the environment's words), with this design as its mitigation for the chat path | [§13 *Boundary*](13-conversation-record.md#boundary) | `uv run --with pyyaml --with python-frontmatter python validate.py` passes with the new `threats/TM-007-*.md` |
| 19 | Journals live on volume `chat-sessions` at `/data` in `chat-ui`; the image creates `/data/sessions` owned by `node`, so a fresh volume starts writable; the root filesystem stays read-only | [§6 *Sessions*](06-chat-ui.md#sessions) | `docker build` of the image succeeds and, with a freshly created volume and the compose hardening, a first run is journaled; `docker inspect` on an instance: `chat-ui` has `ReadonlyRootfs: true`, exactly one volume mount (`/data`) and tmpfs exactly `/tmp` and `/app/.next/cache` |
| 20 | The browser changes metadata only, through `/api/sessions` (`GET` list, `GET`/`PATCH`/`DELETE` one); no `POST`: a session exists once its first run has started | [§6 *Session API*](06-chat-ui.md#session-api) | `npm test`: `PATCH` with `messages`, `runs`, `id` or any unknown key gets 400 and changes nothing; a new UUID is absent from `GET /api/sessions` until a run on it starts |
| 21 | Delete is soft: `deleted_at` set, the session gone from every API answer and refused for new runs, the journal kept and archived; a run already in progress is not cancelled and goes on being journaled | [§6 *Sessions*](06-chat-ui.md#sessions) | `npm test`: after `DELETE`, the list omits it, `GET`/`PATCH`/`DELETE` give 404, a run on its id ends with `RUN_ERROR` and does not reach the agent; the journal still exists with a `meta` line setting `deleted_at` |
| 22 | Titles start as the first user message cut to 60 characters and are never overwritten once the user renames | [§6 *Sessions*](06-chat-ui.md#sessions) | `npm test`: auto title after the first run; after `PATCH {title}` a later run leaves it unchanged |
| 23 | Tags are normalised (trim, lower-case, `[a-z0-9._-]`, ≤ 32 chars, ≤ 20 per session, de-duplicated) | [§6 *Sessions*](06-chat-ui.md#sessions) | `npm test`: table of inputs → stored tags or 400 |
| 24 | A run is detached from the browser's request: closing the tab does not cancel it, only the stop button does; the hook survives the runtime's per-request clone and keeps its state per run | [§13 *The run route*](13-conversation-record.md#the-run-route) | `npm test` (`clone`): the middleware survives `cloneAgentForRequest` with per-run state; end to end against `fake_agent.py`: closing the tab mid-run leaves the whole run in the journal, `run_end` `completed` |
| 25 | The sidebar, in Open WebUI's look and behaviour: new chat, title search with Open WebUI's `tag:` filter (all named tags must match), pinned first then date groups, a popover row menu (rename, pin, tags, hide, delete with confirmation) that closes on outside click and Escape, show-hidden toggle; the open session is in the URL (`?session=`) | [§6 *The sidebar*](06-chat-ui.md#the-sidebar) | Playwright against `fake_agent.py`: each action, then a reload reopens the same session with its tool cards; outside click, Escape and opening another row close the menu and commit or end an edit |
| 26 | Switching session and New chat are disabled while a run is in progress; after a run ends the list is reconciled by `last_run_at` until it shows that run | [§6 *The sidebar*](06-chat-ui.md#the-sidebar) | Playwright: during a scripted slow run both controls are disabled; after stop they are enabled, the stopped run is journaled `cancelled` and a new session's row appears, also with the journal's append delayed by a test hook |
| 27 | Journals and the archive never hold what comes from the request headers or the chat UI's configuration (the agent key); message content is stored unchanged, not redacted; the instance's key scan covers the volume as a detector | [§6 *Security and limits*](06-chat-ui.md#security-and-limits) | `npm test`: a run whose request carries `Authorization: Bearer <k1>` and whose runtime is configured with agent key `<k2>`, neither in the messages, leaves neither in the journal; `verify.yml`'s key check (§9, 4) scans `/data/sessions` |
| 28 | Model text is rendered as text in the sidebar and fenced in the archive with a fence longer than any backtick run inside | [§6 *Security and limits*](06-chat-ui.md#security-and-limits) | `npm test`/Playwright: a title of `<img src=x onerror=…>` shows as literal text; `pytest`: tool results containing a line of three, four and six backticks each render inside a longer fence |
| 29 | No-cost instance check: the session API answers | [§9](09-checks.md) | `verify.yml` on an `agui` instance: "Session API answers" passes (`GET /api/sessions` → 200, JSON list) |
| 30 | `archive.yml` copies the journals and the run log from the running containers and interrupts nothing, so it can run at any time as a backup; only the final archive (`destroy.yml`, `spe_archive_final: true`) first stops `chat-ui`, then `agent`, so no run is in progress or unjournaled, each service running before must have exited 0, and they are not started again; an absent run log is allowed, a missing `chat-ui` container fails the export; the bundle says whether it was `live` or `final` | [§14 *Export*](14-archive.md#export) | `npm test` (exporter): a journal copied mid-append (cut inside a line, after a run's third event) exports with the torn line skipped and that run `incomplete`, and a bundle marked `live` makes `write_run.py`'s `index.md` say incomplete runs may still have been going; on the dev VM: `archive.yml` during a slow run leaves `chat-ui` and `agent` running (their container start times unchanged), the run ends `completed` in the browser, the archive has it `incomplete`, and a second `archive.yml` after it ends has it `completed`; `destroy.yml` during a slow run archives that run `cancelled` in its journal and the run log; on a fresh instance with zero runs `archive.yml` succeeds with an empty `agui-journals/` and no `agent-runs.jsonl`; with `chat-ui` removed, `archive.yml` fails and `destroy.yml` deletes nothing |

## Early output

Two samples for the conversation record, the first one before anything else is built. **First, the
feasibility check** (decision 5): the built server with `fake_agent.py`, a `curl` request to `chat-ui` carrying
a fabricated assistant turn and a forged `spe-compaction-` marker, the agent's echo of what it received, and
the session's journal lines, shown to the user in the first slice. If CopilotKit's runtime will not let
`chat-ui` replace the history it forwards, the user decides again whether the agent should own the history
instead. **Second, the rendered archive chat** of that session (`chats/01-*.md`) and of one normal session
with tool calls: `fake_agent.py` is enough for both, since what the user judges is the record and its rendering, not the
model's replies; the user reads whether the ignored content and the run statuses are clear to someone
analysing a run, and whether the browser should also show the ignored content (decision 6 only shows what the
model saw). Either sample can change decisions 2, 6 and 16 while they are still cheap to change.

## Glossary

| Term | Meaning |
|---|---|
| `chat-ui` | the CopilotKit chat's container and its server: the runtime route and the session API |
| Session | one conversation in the sidebar; one AG-UI thread (`threadId` = session id, a UUID the browser chooses); one journal |
| Metadata | `title`, `tags`, `pinned`, `hidden` (changed by the browser) and `deleted_at` (set by `DELETE`) |
| Hidden | removed from the default list, shown with *Show hidden*; still openable and editable |
| Deleted | `deleted_at` set: invisible to the participant and the API, kept on disk and in the archive |
| Journal | a session's append-only record, `/data/sessions/<uuid>.jsonl` |
| Run | one request to `chat-ui`'s run route and the agent run it starts; `run_start` to `run_end` in the journal |
| Run log | the agent's `runs.jsonl` (§5, *Run log*) |
| Path | the chain of messages from the root to a message, following `parentId` |
| Anchor | the message a run continues from: the latest client message whose id the journal holds |
| New messages | the user messages after the anchor that the journal does not hold; the only part of a client's history that reaches the agent |
| Ignored content | whatever else in the client's history differs from the journal's path, recorded with its kind |
| Branch | a path ending at a message with no children; runs from one anchor make sibling branches |
| Tip | the message the chat reopens on: the last message of the run that ended last, among the runs that added a message |

## Parts

| File | What it contains | Read when |
|---|---|---|
| [`01-goal.md`](01-goal.md) | §1 Goal: what an instance runs with `spe_frontend: agui`, and what success means | you need the purpose |
| [`02-non-goals.md`](02-non-goals.md) | §2 Non-goals | you wonder whether something is in scope |
| [`03-architecture.md`](03-architecture.md) | §3 Architecture: the three containers, the key boundary, why the agent needs a bearer key | you change what a container holds or who talks to whom |
| [`04-layout.md`](04-layout.md) | §4 Layout in the repository (as of 2026-10-15) | you look for where a piece lived |
| [`05-agent-service.md`](05-agent-service.md) | §5 The agent service: endpoints, model, tools, prompt, limits, run log, configuration, history | you change the agent |
| [`06-chat-ui.md`](06-chat-ui.md) | §6 The chat UI: the app, sessions, the session API, the sidebar, security and limits | you change the chat UI |
| [`07-ansible.md`](07-ansible.md) | §7 Ansible: existing-VM provisioning, the development VM, variables, the `agui` role, compose, handoff | you change how an instance is built |
| [`08-error-handling.md`](08-error-handling.md) | §8 Error handling and known gaps | you handle a failure or look for a known gap |
| [`09-checks.md`](09-checks.md) | §9 Checks (role end and `verify.yml`) | you change the checks |
| [`10-testing.md`](10-testing.md) | §10 Testing: agent unit tests, chat UI, archive, promptfoo | you write or run tests |
| [`11-verify-during-implementation.md`](11-verify-during-implementation.md) | §11 Things to verify during implementation | you check what was open when §§1–10 were built |
| [`12-implementation-findings.md`](12-implementation-findings.md) | §12 Implementation findings (2026-10-15): versions, §11 settled, behaviour made precise, observed results | you need what implementation verified |
| [`13-conversation-record.md`](13-conversation-record.md) | §13 The conversation record: approach, run route, journal, concurrency, rebuild, boundary | you change how `chat-ui` keeps a conversation, or analyse what a run was sent |
| [`14-archive.md`](14-archive.md) | §14 The archive: the live copy and the final archive's barrier, the Open WebUI chat export, the rendered run directory | you change or read an AG-UI run's archive |
| [`out-of-scope.md`](out-of-scope.md) | what the chat sessions and the record leave out | you wonder whether something was considered |
| [`inputs-for-plan.md`](inputs-for-plan.md) | inputs for the conversation record's plan | you write that plan |
| [`clarifications.md`](clarifications.md) | the decision log (history) | you need why the design changed |
