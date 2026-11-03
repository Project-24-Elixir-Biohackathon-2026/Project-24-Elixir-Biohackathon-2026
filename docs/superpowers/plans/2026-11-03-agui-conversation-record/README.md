# AG-UI conversation record: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` (`AGENTS.md`,
> *Working Conventions*) to implement one slice per session and PR. Steps use checkbox (`- [ ]`) syntax.

**Goal:** `chat-ui` owns each session's history as an append-only journal: from every run request it takes only
the new user message, sends the agent the history from its journal, and records whatever else the client sent as
ignored content; the archive copies the journals raw and exports each as an Open WebUI chat that `write_run.py`
renders.

**Spec:** the living AG-UI spec [`docs/specs/2026-10-15-agui-frontend-design/`](../../../specs/2026-10-15-agui-frontend-design/README.md):
§13 (the record), §14 (the archive), §6 (sessions, as restated for the record), decisions 1–30 in its README,
*Early output*, and [`inputs-for-plan.md`](../../../specs/2026-10-15-agui-frontend-design/inputs-for-plan.md).
Latest clarification when this plan was written: 5. Each slice file names the decisions it implements; shared
names and signatures are in [`interfaces.md`](interfaces.md).

**Architecture.** Four new modules in `platform/agui/copilotkit-chat/lib/`, each with one job, and two
rewritten ones:

- `journal.ts`: the line format, parsing (a torn line skipped), `JournalWriter` (the only appender).
- `rebuild.ts`: lines → a `Conversation` (messages with `parentId`, runs, tip) with `@ag-ui/client`'s
  `defaultApplyEvents`, the browser's code; one module for the route, the API and the exporter (decision 11).
- `anchor.ts`: a client history against a `Conversation` → anchor, new messages, ignored content (decision 2).
- `export.ts`: a `Conversation` → an Open WebUI chat (§14), run in the image by `scripts/export-journals.ts`.
- `sessions.ts` (rewritten): the index on `globalThis`, the per-session queue, metadata as `meta` lines.
- `recorder.ts` (rewritten): the run route's middleware: admit, classify, `run_start`, replace `messages`,
  journal every event, `run_end`.

The archive's writer `write_run.py` learns the three AG-UI additions (status, ignored content, compaction) and
`write_agui_run.py` goes. The agent (`platform/agui/pydantic-ai-agent/`) does not change.

**Tech stack:** Next.js 16.4.1, CopilotKit 1.79.0 (v2 runtime), `@ag-ui/client` 1.0.2, rxjs 7.8.1, Node 24
`node --test` with type stripping (chat); Python standard library (`write_run.py`, `platform/dev/tests`);
Playwright (Python, `platform/dev/e2e/`); Ansible from the system package.

## Order against the compaction track

Compaction 2/3 (#18) merged on 2026-11-03, while this plan was in review; no slice waits for compaction 3/3 (de.NBI
variables and docs, no shared file). What #18 added is carried over: `## Compacted` and the `Compactions` column
move into `write_run.py` (slice 2, task 3; inputs-for-plan, bullets 5 and 8), its recorder test that the record
keeps the marker becomes a journal test (slice 3, task 2), the fake agent's `compact` stays. A slice that adds a
clarification takes the next free number in the spec's `clarifications.md` when it commits.

## Rulings

Each is *decision, why, cost if wrong*; a slice that departs from this plan adds one to its handoff and rewrites
the task text it changes.

1. **Slice 1 lands the pure modules unwired.** `journal.ts`, `rebuild.ts` and `anchor.ts` merge before anything
   uses them, so the feasibility check and the hardest logic are reviewed on their own. *Cost if wrong:* a module shaped wrongly for its caller is reshaped in slice 3, at the price of one
   rewritten test file.
2. **The exporter ships before the route switches storage** (slice 2 before slice 3), so `main` never has
   journals that the archive cannot render: slice 3 switches the store, the route and the archive's export in one
   PR. *Cost if wrong:* slice 2's exporter is tested only on fixture journals until slice 3; slice 3's built-server
   sample is its first real input.
3. **The feasibility check is a runtime-level test plus the built-server sample.** Slice 1, task 1 pins, through
   `createCopilotRuntimeHandler` and a real `HttpAgent`, that a middleware replacing `input.messages` decides what
   the agent receives; slice 3, task 5 produces the spec's sample once the journal is wired (spec clarification 4,
   added by this plan's PR). If task 1 fails, the work stops for the user's decision (spec, *Early output*): a PR
   comment, the session ends blocked. *Cost if wrong:* none beyond the order; the sample is the same.
4. **`ignored` entries share one shape.** `run_start.ignored` is a list of `{kind, message}`; for `deleted`,
   `message` is the deleted message's id (a string), the literal reading of §13 *The journal*. *Cost if wrong:* a
   reader that expects an object for every kind needs one `typeof` check.
5. **What the agent does with `context`, `state`, `forwardedProps`:** nothing of its own. `app.py` hands the
   whole `RunAgentInput` to pydantic-ai's `AGUIAdapter` after rewriting only compaction markers; `RunDeps` takes
   only `thread_id`. So `run_start.request` records them and the route forwards them unchanged (decision 5). Read
   2026-11-03; *cost if wrong:* none: the record stores them either way (inputs-for-plan, bullet 4).
6. **Classification's readings of decision 2** (slice 1, task 4; notes 3(a)–(e) of `slice-1-history.md`): (a)
   the anchor is the client message the journal added last, not the last in the client's order; (b) a known
   message whose compared fields equal the journal's is not recorded, even off the anchor's path (a message
   resent from another branch): the journal already holds it verbatim, and `run_start.anchor` shows which branch
   the run continued; (c) messages cut when the anchor moves back to a boundary are `deleted` even if the client
   sent them; (d) a message without a string id is `fabricated`, and a repeated new id counts once; (e) `ignored`
   lists client-order entries first, then `deleted` in path order. A run's last message is no boundary while a
   tool call the run made has no result in that run, nor while the run has no `run_end` (`isBoundary`; the
   second rule from #22's review, clarification 7). Slice 1 folds them into §13 step 2 with a
   clarification. *Cost if wrong:* an analyst
   cannot see that a client resent an unchanged message from another branch; recording it later is one more
   `ignored` kind and its rendering in `write_run.py`, absent from journals written before.

## Global Constraints

Every task's requirements include these.

- **Tests, before every commit**, the suites a slice touches (`AGENTS.md`, *Running things*):
  `(cd platform/agui/copilotkit-chat && npm ci && npm test && npm run build)`,
  `uv run --with pytest pytest platform/dev/tests -q`,
  `cd platform/ansible && ansible-playbook --syntax-check playbooks/create.yml playbooks/verify.yml playbooks/archive.yml playbooks/destroy.yml </dev/null`,
  `uv run --with pyyaml --with python-frontmatter python validate.py` (slice 4).
- **No new dependencies.** The chat uses `@ag-ui/client`, `@copilotkit/runtime`, `rxjs` and Node's standard
  library; Python stays standard library.
- **No file under `platform/agui/pydantic-ai-agent/` changes** (decision 1).
- **The journal is append-only**: no code path opens a journal for anything but appending (`fs.open(path, "a")`)
  or reading; nothing renames, truncates or rewrites one (decision 10). `JournalWriter` is the only writer.
- **Names fixed by the spec:** journal path `/data/sessions/<uuid>.jsonl` (`SPE_SESSIONS_DIR`, default
  `/data/sessions`); line types `created`, `run_start`, `event`, `run_end`, `meta`; statuses `completed`,
  `failed`, `cancelled`, `aborted`, `refused`, and `incomplete` for a run without `run_end` (never written);
  ignored kinds `fabricated`, `edited`, `deleted`, `system`; `source: "chat"`; `created.version: 1`; the six
  refusal and failure messages `invalid session`, `this session was deleted`, `the chat UI is shutting down`,
  `this session could not be saved`, `this run carries no new message`, `this run was already recorded`;
  `globalThis` keys `Symbol.for("spe.sessions.queue")` and `Symbol.for("spe.sessions.index")`; archive paths `agui-journals/<uuid>.jsonl`, `agent-runs.jsonl`; bundle field
  `spe_archive_mode` `live` | `final`; chat fields `spe_run` (`run_id`, `status`, `started_at`, `ended_at`, `error`),
  `spe_ignored`, `meta.spe_deleted_at`; the block heading "sent by the client, not used".
- **Never stored:** request headers and the chat UI's configuration (the agent key) are never in a journal, a
  log line or the archive; message content is stored unchanged (decision 27). Log lines name ids, never content.
- **Model text is text:** React text in the sidebar; in the archive a fence one backtick longer than the longest
  backtick run inside (at least three), with `write_run.py`'s existing `fence()`.
- **No model calls, no cloud instances.** Every check uses `lib/test-agent.ts` or `platform/dev/fake_agent.py`.
  The dev VM's instance is redeployed in place with `create.yml` from the main checkout and
  `-e spe_agui_source_dir=<worktree>/platform/agui` (`AGENTS.md`, *Worktrees and deploying*); a playbook the slice
  changes runs from the worktree with the main checkout's instance file and `spe_output_root`. `destroy.yml` runs
  only against the dev VM's instance in slice 4, task 5, after asking the user (it is a destroy).
- **Upstream-clean:** code, READMEs, Ansible and `platform/` comments name nothing fork-only; the spec already
  lives in `docs/specs/` for that reason (`AGENTS.md`, *Overrides*).
- **Rulings:** a departure from this plan is recorded in the slice's handoff as *decision, why, cost if wrong*,
  and the same commit rewrites the plan task text (and, through a clarification, the spec text) it changes.

## Shared interfaces

Every name later slices rely on, with signatures, is in [`interfaces.md`](interfaces.md), one section per module:

- `lib/journal.ts` (slice 1): line types, `parseJournal`, `JournalWriter` (fsync policy, directory fsync on create).
- `lib/rebuild.ts` (slice 1): `Conversation`, `RunView`, `rebuild`, `rebuildText`, `pathTo`, `isBoundary`, `branchOfTip`.
- `lib/anchor.ts` (slice 1): `canonical`, `classify` (readings: ruling 6).
- `lib/export.ts`, `scripts/export-journals.ts` (slice 2): the bundle types, `exportJournals`; the archive's exporter argv.
- `lib/sessions.ts` (slice 3): `Journals`, `shared`, `withSession`, the session API's shapes.
- `lib/recorder.ts` (slice 3): `SessionRecorder`, the six `REFUSAL_MESSAGES`.
- `lib/test-agent.ts` (slice 1), `platform/dev/fake_agent.py` (slice 3): the `echo-input` keyword.
- `write_run.py` (slice 2): `is_compaction`, `render_ignored`, `render_status`, the AG-UI index.

## File structure

| Path | Slice | What |
|---|---|---|
| `CHAT/lib/test-agent.ts`, `lib/feasibility.test.ts`, `lib/journal.ts`, `lib/rebuild.ts` (each with its test) | 1 | `echo-input` and the feasibility check; format, parse, writer; the rebuild |
| `CHAT/lib/anchor.ts`, `lib/anchor.test.ts`; spec `13-conversation-record.md`, `clarifications.md` | 1 | classification; ruling 6 folded into §13 |
| `CHAT/lib/export.ts`, `lib/export.test.ts`, `CHAT/scripts/export-journals.ts`, `CHAT/Dockerfile` | 2 | exporter in the image |
| `platform/dev/tests/fixtures/agui-record/*.jsonl`, `*.bundle.json` | 2 | fixture journals and the bundles exported from them (committed) |
| `ARCHIVE/write_run.py`, `platform/dev/tests/test_write_run_agui.py` | 2 | status, ignored, compaction, AG-UI index |
| `CHAT/lib/sessions.ts`, `lib/sessions.test.ts`, `lib/test-journals.ts`, `lib/api.ts`, `lib/api.test.ts`, `app/api/sessions/**` | 3 | the store on journals |
| `CHAT/lib/recorder.ts`, `lib/recorder.test.ts`, `lib/clone.test.ts`, `lib/shutdown.ts`, `lib/reconcile.ts`, `app/api/copilotkit/[[...slug]]/route.ts` | 3 | the route on journals |
| `platform/ansible/roles/run_archive/tasks/export.yml`, `tasks/write.yml`; `ARCHIVE/write_agui_run.py` (deleted), `platform/dev/tests/test_write_agui_run.py` (deleted or reduced to `write_run.py` cases) | 3 | archive switch (barrier kept) |
| `platform/dev/fake_agent.py`, `CHAT/scripts/check-built-server.mjs`, `scripts/check-shutdown.mjs`, `platform/dev/e2e/sessions.py` | 3 | `echo-input`, checks read journals |
| `CHAT/README.md`, `docs/getting-started.md`, `platform/ansible/README.md`, `platform/coder/README.md`, `docs/knowledge/agui-chat-sessions.md`, `BACKLOG.md` | 3 | storage described |
| `docs/superpowers/plans/2026-11-03-agui-conversation-record/evidence/slice-3/` | 3 | early output samples 1 and 2 |
| `platform/ansible/roles/run_archive/tasks/export.yml`, `playbooks/destroy.yml`, `playbooks/archive.yml`, `inventory/group_vars/all.yml`, `platform/dev/tests/test_archive_export.py` | 4 | live copy, final barrier (`spe_archive_final`) |
| `platform/ansible/README.md`, `CHAT/README.md`, `docs/README.md`, and what slice 4's task 1 grep finds (`platform/coder/README.md`, `docs/getting-started.md`, `docs/knowledge/agui-chat-sessions.md`) | 4 | the live/final archive described; the plan's row |
| `platform/dev/fake_agent.py`, `fake-agent.compose.yml` | 4 | `SPE_FAKE_SLOW_STEP_SECONDS`, so a scripted run outlasts the archive's copy |
| `platform/dev/e2e/sessions.py` | 4 | devtools edit, close tab, restore on tip |
| `platform/ansible/roles/agui/tasks/checks.yml` | 4 | agent key not in the sandbox (17) |
| `threats/TM-007-*.md`, `threats/TM-005-*.md` (related list) | 4 | decision 18 |
| spec `README.md` status, `06-chat-ui.md` (the `GET` one row), `14-archive.md` (as-built paragraph), `clarifications.md` | 3, 4 | built |

`CHAT` is `platform/agui/copilotkit-chat`, `ARCHIVE` `platform/ansible/roles/run_archive/files`.

## PR slices

N = 4. Sequential: slice n+1 starts from `main` after slice n merged. The session merges each PR itself once the
checks in `AGENTS.md`, *Overrides*, pass; the status column then reads `merged #<n>`.

| n/N | Branch | Tasks | Delivers | Est. LOC | Reviewer checks | File | Status |
|---|---|---|---|---|---|---|---|
| 1/4 | `impl/agui-conversation-record-1-history` | 4 | **feasibility check** (decision 5) first; journal format and writer, rebuild, anchor, all unwired | ~1,100 | `npm test`; `npm run build` | [slice-1-history.md](slice-1-history.md) | merged #22 |
| 2/4 | `impl/agui-conversation-record-2-export` | 3 | exporter in the image; `write_run.py` renders AG-UI chats (status, ignored, compaction, columns) | ~800 | `npm test`; `docker build` + exporter run in the image; `pytest platform/dev/tests` | [slice-2-export.md](slice-2-export.md) | merged #23 |
| 3/4 | `impl/agui-conversation-record-3-route` | 5 | the store, the run route and the API on journals; archive exports journals (barrier kept); built-server check; **early output** samples 1 and 2 | ~1,500 | `npm test`; `npm run build`; `check-built-server.mjs`; `check-shutdown.mjs`; `docker build` + exporter run in the image (slice 2's check again: `sessions.ts` rewritten); pytest; `--syntax-check`; e2e `sessions.py` | [slice-3-route.md](slice-3-route.md) | merged #24 |
| 4/4 | `impl/agui-conversation-record-4-live-archive` | 5 | live archive and final barrier (decision 30); Playwright for decisions 6, 13, 24–26; key check (17); TM-007 (18); dev VM acceptance; spec marked built | ~700 | e2e `sessions.py`; `verify.yml` and `archive.yml` on the dev VM; `validate.py` | [slice-4-live-archive.md](slice-4-live-archive.md) | planned |

Slice 1's estimate (~1,100 lines) is past the guide's ~1,000, though most of it is tests, which the guide does not
count; it stays one unit: one test fixture set (journals built line by line, rebuilt and classified) binds the
three modules, and the anchor alone would be an unwired PR whose tests need the other two. Slice 3 is past the
guide's ~5 tasks by size, not count, and stays one unit (ruling 2): split, `main` would hold journals the archive
does not export, or a route that writes what the session API cannot read. It names two
mid-slice handoff points, each after a commit with `npm test` green: **after task 2** (store and route on
journals; API and archive next) and **after task 4** (archive switched; the checks, docs and samples next). A
reviewer looks first at `SessionRecorder.run` and `classify`.

**What the user sees, and when.** Slice 1's PR body carries the feasibility verdict (task 1's test output, and
what the test agent received). Slice 3's PR body carries the spec's two early-output samples, from the built
server with `fake_agent.py` (spec clarification 4): the `curl` with a fabricated assistant turn and a forged
`spe-compaction-` marker, the agent's echo, the journal lines; and the rendered chat files of that session and of
a normal session with tool calls. It asks the user whether the ignored content and run statuses are clear to
someone analysing a run, and whether the browser should also show the ignored content. Slice 4 does not wait for
the answer, but a change it asks for (decisions 2, 6, 16) is rewritten into slice 4's task text by a commit on
`main` before slice 4 starts, never left in a handoff.

## Review Focus

Inputs the spec implies that no acceptance check exercises; each line's test is in the named task.

1. **A client history whose messages arrive out of journal order** (the browser reorders, or devtools moves a
   reply above its question): the anchor is still the client message the journal added last, and every
   reordered message is `edited` only if its compared fields differ, never `fabricated`. Slice 1, task 4
   (`reordered history keeps the anchor and flags nothing`).
2. **A new user message reusing an id the journal holds in another branch** (a tab that resends an old message
   after the other tab ran): it is not a new message; the run has none and is refused, with the id recorded as
   `edited` only if its content differs. Slice 1, task 4 (`a known id after the anchor is not new`).
3. **A journal whose `created` line is torn or missing** (a crash during the first `run_start`): the rebuild
   still yields the runs it can parse, `created_at` falls back to the first parsed line's `at`, and the session
   lists. Slice 1, task 3 (`journal without a created line`).
4. **An event for a run whose `run_start` was never written or was skipped as torn**: the rebuild skips the
   event (logged by run id), never attaches it to another run. Slice 1, task 3 (`orphan event is skipped`).
5. **A title, tag or message with Markdown or HTML in the archive** (`# x`, `<script>`, a pipe in a title): the
   `index.md` table cell escapes `|` and newlines, and chat text renders inside fences or as escaped text, so the
   run directory's structure cannot be forged from a session. Slice 2, task 3 (`title with a pipe and a heading`).

## Proposed spec clarifications

Each is added by the slice that verifies it, with the next free number and status `folded`, and the spec text
updated in the same commit. This plan's PR added clarifications 4 (sample 1 from the built server, ruling 3) and
5 (`spe_agui_source_dir` is `platform/agui`).

- **Slice 1: classification's readings of decision 2** (ruling 6), folded into §13 *The run route*, step 2.
- **Slice 2: the archive's chat file also shows the messages off the active branch** (*Other branches*), folded
  into §14 *Write*.
- **Slice 3: the record is built, every archive still runs the barrier.** §14's "Until the record is built…"
  paragraph and the README's status line are rewritten as built; §6's `GET /api/sessions/{id}` row loses
  `last_run_at` (the browser reads it from the list).
- **Slice 4: the record is built.** The spec README's status line (which holds the "wait for the record"
  sentence, not §6) and §14's barrier sentence for the as-built sessions are rewritten.

## Handoffs

[`handoffs/`](handoffs/): read only the newest (`ls handoffs | tail -1`).
