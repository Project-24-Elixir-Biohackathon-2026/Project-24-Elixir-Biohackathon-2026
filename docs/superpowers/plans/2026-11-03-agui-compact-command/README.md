# AG-UI `/compact`: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` (`AGENTS.md`,
> *Working Conventions*) to implement one slice per session and PR. Steps use checkbox (`- [ ]`) syntax.

**Goal:** the participant types `/compact` or `/compact <focus>` in the AG-UI chat and the conversation is
compacted now: `chat-ui` journals the run as a command, never as a message, and sends the agent the path with
`forwardedProps.spe_command`; the agent makes one summary request and returns the same marker an automatic
compaction does; the archive says the participant asked for it.

**Spec:** the living AG-UI spec [`docs/specs/2026-10-15-agui-frontend-design/`](../../../specs/2026-10-15-agui-frontend-design/README.md):
§15 ([`15-compact-command.md`](../../../specs/2026-10-15-agui-frontend-design/15-compact-command.md)), decisions
31–39 in its README, *Early output* (`/compact`), clarification 12, and
[`inputs-for-plan.md`](../../../specs/2026-10-15-agui-frontend-design/inputs-for-plan.md), *`/compact`*. The
compaction design it cites as "compaction decision N" is
[`docs/superpowers/specs/2026-11-03-agui-compaction-design.md`](../../specs/2026-11-03-agui-compaction-design.md).
Latest clarification when this plan was written: 12. Each slice file names the decisions it implements.

**Architecture.** Two sides, one slice each:

- **The agent** (`platform/agui/pydantic-ai-agent/`): `compaction.py` gains `summarise()`, the summary request
  split out of `Compaction._compact` (usage limits, the retry, the usage accumulator), which both the capability
  and the new command path call; a manual prompt, frame and marker id. `app.py` answers a run whose
  `forwardedProps.spe_command` is `compact` without the model loop (`Service._command_events`). `fake_agent.py`
  answers a command with a fixed summary.
- **`chat-ui` and the archive** (`platform/agui/copilotkit-chat/`, `write_run.py`): a new `lib/command.ts` parses
  the command; `recorder.ts` journals it (`run_start.command`, empty `messages`), refuses the two cases, strips and
  sets `spe_command`, and always snapshots the path after `RUN_STARTED`; `rebuild.ts` keeps the command ids
  (known, never on the path) and drops a marker cut short; `anchor.ts` compares a resent command; `export.ts`
  sets `spe_command`; `write_run.py` renders it.

**Tech stack:** pydantic-ai 2.56.0 (`AGUIAdapter`), ag-ui-protocol 0.1.22, FastAPI, pytest with
`FunctionModel` (agent); Next.js 16.4.1, CopilotKit 1.79.0, `@ag-ui/client` 1.0.2, Node 24 `node --test`
(chat); Python standard library (`write_run.py`); Playwright (Python, `platform/dev/e2e/`).

## Rulings

Each is *decision, why, cost if wrong*; a slice that departs from this plan adds one to its handoff and rewrites
the task text it changes.

1. **A manual marker's id is `spe-compaction-manual-<uuid4>`.** The agent is stateless, so the next run can
   only tell a manual marker (whose frame says the participant asked) from an automatic one by what the chat
   sends back; every reader matches the prefix `spe-compaction-` (`isCompactionMarker`, `is_compaction`,
   `_is_marker_message`), so nothing else changes. `markers_to_activities` carries the id onto the
   `CompactionPart` (`id=`), and `build_sent` picks the frame from it. Slice 1 folds this into §15 *The agent*
   and compaction decision 7 with clarification 15. *Cost if wrong:* a marker written before slice 1 is
   automatic, which it was; a reader that parses the id after the prefix as a UUID breaks (none does).
2. **Every compaction record gains `focus`** (null for `threshold` and `overflow`), so decision 11's records keep
   one shape. *Cost if wrong:* one more null field per record.
3. **A resent command message is unchanged when its role is `user` and its content parses to the same command
   and focus** (`parseCommand`), since `run_start.command` keeps the parsed command, not the raw text: `/compact`
   resent as `  /compact ` is not `edited`. *Cost if wrong:* an analyst cannot see a whitespace-only edit of a
   command bubble.
4. **`forwardedProps` that is not a plain object** (absent, `null`, a list) **is sent as `{}` plus the command on a
   command run, and as sent on a plain run** (there is no `spe_command` in it to remove). *Cost if wrong:* none
   seen: the agent reads nothing else from it (conversation record plan, ruling 5).
5. **Two inputs-for-plan defects are not on `main`** (read 2026-11-03): `fake_agent.py`'s `summarise` already
   guards its request type with `RuntimeError` (the bare `assert` is in the test helper `Script.function` of
   `tests/test_app.py`, a test's assertion, kept), and `app/compaction-divider.tsx` narrows with the
   `isCompactionMarker` type guard, with no `as string` cast. Nothing to fix; the third defect (`fake_agent.py`'s
   "compacted anywhere" check) is slice 1, task 3. *Cost if wrong:* none.
6. **The focus's length is counted in code points** (`[...focus].length` in TypeScript; `len()` in Python), so
   1000 emoji are allowed as 1000 letters are. *Cost if wrong:* none against the 1000-character rule as written.

## Global Constraints

Every task's requirements include these.

- **Tests, before every commit**, the suites a slice touches (`AGENTS.md`, *Running things*):
  `(cd platform/agui/pydantic-ai-agent && uv run --group dev pytest -q)` (slice 1);
  `(cd platform/agui/copilotkit-chat && npm ci && npm test && npm run build)`,
  `uv run --with pytest pytest platform/dev/tests -q` (slice 2).
- **No new dependencies.** The agent uses pydantic-ai, ag-ui and the standard library; the chat `@ag-ui/client`,
  `@copilotkit/runtime`, `rxjs` and Node's standard library; Python under `platform/dev/` and `write_run.py`
  stays standard library.
- **Slice boundaries:** slice 1 changes only `platform/agui/pydantic-ai-agent/` and `platform/dev/` (plus the
  spec and this plan); slice 2 does not change `platform/agui/pydantic-ai-agent/`.
- **Names fixed by the spec:** the command `/compact`, case-sensitive; `run_start.command` =
  `{name: "compact", focus: string | null, message_id: string}`; `forwardedProps.spe_command` =
  `{name: "compact", focus}`; the bundle field `spe_command`; the run log's `trigger: "manual"` and `focus`; the
  refusal and error texts `Nothing to compact yet.`, `The focus after /compact is too long (1000 characters at
  most).`, `Compaction is turned off on this instance.`, `Unknown command.`; the archive line *Requested by the
  participant (`/compact`)*; the focus section heading `The participant's instructions for this summary`.
- **The journal stays append-only** and `JournalWriter` its only writer (conversation record, decision 10).
- **Model text is text:** the focus and the summary are fenced with a fence one backtick longer than the longest
  backtick run inside (at least three): `fence()` in `write_run.py`, `fence()` added to `compaction.py`.
- **Never stored:** request headers and the agent key; the run log is redacted as every record is.
- **Model calls:** every check uses `lib/test-agent.ts`, `FunctionModel` or `platform/dev/fake_agent.py`, except
  decision 39 (slice 2, task 5): **a paid run on de.NBI `qwen3.8-27b`; ask the user before it** (`AGENTS.md`,
  *Setup*), with one PR comment and `next-session.sh --end --blocked <PR>` if no answer comes.
- **Upstream-clean:** code, READMEs and `platform/` comments name nothing fork-only (§15 *Upstream*: `/compact`
  goes upstream with the AG-UI compaction or after it).
- **Rulings:** a departure from this plan is recorded in the slice's handoff as *decision, why, cost if wrong*,
  and the same commit rewrites the plan task text (and, through a clarification, the spec text) it changes.

## File structure

| Path | Slice | What |
|---|---|---|
| `AGENT/src/spe_agent/compaction.py`, `compaction_prompt.md`, `tests/test_compaction.py` | 1 | `summarise()`, `fence()`, manual prompt, frame and marker id (rulings 1, 2) |
| `AGENT/src/spe_agent/app.py`, `runlog.py`, `tests/test_app.py` | 1 | the command path, its run log record |
| `platform/dev/fake_agent.py` | 1 | a command's fixed summary; the "compacted anywhere" fix |
| spec `15-compact-command.md`, `clarifications.md`; compaction design decisions 7 and 11 | 1 | clarification 15 (ruling 1, 2) |
| `CHAT/lib/command.ts`, `lib/command.test.ts`, `lib/journal.ts`, `lib/rebuild.ts`, `lib/anchor.ts`, `lib/recorder.ts`, `lib/test-agent.ts`, `lib/recorder.test.ts`, `lib/rebuild.test.ts`, `lib/anchor.test.ts` | 2 | the command run in the route (31–34, 37) |
| `platform/dev/e2e/sessions.py`; `docs/superpowers/plans/2026-11-03-agui-compact-command/evidence/slice-2/` | 2 | Playwright (33); the early output |
| `CHAT/lib/export.ts`, `lib/export.test.ts`, `platform/dev/tests/fixtures/agui-record/`, `ARCHIVE/write_run.py`, `platform/dev/tests/test_write_run_agui.py` | 2 | the archive (38) |
| `CHAT/README.md`, `docs/getting-started.md`, spec `README.md` (status), `clarifications.md` | 2 | `/compact` described; the spec marked built |

`AGENT` is `platform/agui/pydantic-ai-agent`, `CHAT` `platform/agui/copilotkit-chat`, `ARCHIVE`
`platform/ansible/roles/run_archive/files`.

## PR slices

N = 2. Sequential: slice 2 starts from `main` after slice 1 merged **and** after the conversation record's slice
4/4 (#25) merged, since both change `platform/dev/e2e/sessions.py` and the chat's README (and #25 `fake_agent.py`,
which slice 1 also changes: whichever merges second merges the other's lines in). The session merges each PR
itself once the checks in `AGENTS.md`, *Overrides*, pass; the status column then reads `merged #<n>`.

| n/N | Branch | Tasks | Delivers | Est. LOC | Reviewer checks | File | Status |
|---|---|---|---|---|---|---|---|
| 1/2 | `impl/agui-compact-command-1-agent` | 3 | `summarise()` shared by both paths; the agent answers `spe_command: compact` (35); its run log record (36); `fake_agent.py` answers a command | ~450 | agent `pytest`; `fake_agent.py` answered with `curl` (task 3) | [slice-1-agent.md](slice-1-agent.md) | merged #28 |
| 2/2 | `impl/agui-compact-command-2-chat` | 5 | **early output** first (31–33, Playwright, sample); refusals (34); a marker cut short (37); archive (38); docs; de.NBI check (39, paid: ask first); spec built | ~750 | `npm test`; `npm run build`; pytest; e2e `sessions.py --scenario compact-command`; the early output sample | [slice-2-chat.md](slice-2-chat.md) | merged #30 |

**What the user sees, and when.** Slice 2's task 3 posts the spec's early output on its PR (screenshots of the
divider live and after a reload after `/compact keep the canary paths`, and the journal's `run_start` with its
`command`) and asks whether a command that leaves no bubble reads clearly. Tasks 4 and 5 do not wait for the
answer; a "no" changes decision 33 (a "Compaction requested" line instead): a clarification, and the change in
the same PR before it merges. Task 5 asks before decision 39's paid run.

## Review Focus

Inputs the spec implies that no acceptance check exercises; each line's test is in the named task.

1. **A focus holding backticks or a fence** (```` ``` ```` or a run of four): the agent's focus section and the
   archive's line stay fenced around all of it, so the focus cannot end the fence and pose as the transcript or
   the archive's structure. Slice 1, task 1 (`focus with a fence inside stays fenced`); the archive half is
   decision 38's check (slice 2, task 5).
2. **Several refused `/compact` bubbles kept by the browser, then a third `/compact` or a plain message**: the
   kept ones are known commands, neither new nor `fabricated`; only the last typed message counts. Slice 2,
   task 2 (`kept command bubbles are known, not new`).
3. **The focus at the limit** (exactly 1000 code points, and 1001; 1000 emoji): 1000 is accepted, 1001 refused
   (ruling 6). Slice 2, task 4 (`focus length is counted in code points`).
4. **`/compact` right after a stopped or failed run** (the path ends in a partial reply or a dangling tool
   call): the anchor moves back to a boundary as for any run, and the command compacts that path; the agent is
   never sent a dangling tool call. Slice 2, task 2 (`compact after a stopped run`).
5. **A second `/compact` in a session already compacted manually**, with one exchange since: the transcript
   pins the earlier summary (framed as manual) as a record and the latest real request, not the earlier summary
   as the request. Slice 1, task 1 (`second manual compaction pins the real request`).

## Proposed spec clarifications

Each is added by the slice that verifies it, with the next free number and status `folded`, and the spec text
updated in the same commit.

- **Slice 1, task 1: a manual marker's id and the record's `focus`** (rulings 1, 2): §15 *The agent*, item 4, and
  the compaction design's decisions 7 and 11.
- **Slice 2, task 5: `/compact` is built** — the spec README's status line, and what implementation verified
  or changed (ruling 3 into §15 *The run route*, step 2; ruling 4 into step 5).

## Handoffs

[`handoffs/`](handoffs/): read only the newest (`ls handoffs | tail -1`).
