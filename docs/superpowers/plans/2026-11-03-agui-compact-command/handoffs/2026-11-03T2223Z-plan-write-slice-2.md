# 2026-11-03: plan written up to slice 1; write slice 2, then the review round

**State.** Branch `plan/agui-compact-command`, draft PR #27 (claimed, label `plan`). Committed: the plan's
`README.md` (rulings 1–6, Global Constraints, file structure, `## PR slices`, Review Focus 1–5, proposed
clarifications) and `slice-1-agent.md` (3 tasks). Missing: **`slice-2-chat.md`**, which the README already links
and describes (5 tasks, ~750 LOC). Context for it: the README, §15, decisions 31–34 and 37–39, *Early output*.
Don't re-read the agent code: slice 1's file states its contract (task 2, *Interfaces*).

**Slice 2's design, worked out from the code on `main` `3bdc37b`** (write it into the slice file as tasks):

- **Task 1 (31, 33's `npm test`).** New `CHAT/lib/command.ts`: `parseCommand(content: unknown): {name:
  "compact", focus: string | null} | null` (string only; trimmed; `/^\/compact(?:\s+([\s\S]*))?$/`, focus = rest
  trimmed or null; case-sensitive) and `commandOf(newMessages: Message[])` (exactly one user message that parses,
  else null). `journal.ts`: `RunStartLine.command?: {name, focus, message_id}`, checked in `isLine`.
  `recorder.ts` `admit` (after `classify`): `command = commandOf(classification.newMessages)`; `run_start` gets
  `messages: command ? [] : newMessages` and `command: {..., message_id}`; the `NO_NEW_MESSAGE` refusal applies
  only without a command. `run`: `messages = [...path, ...(command ? [] : newMessages)]`; forwardedProps: strip
  any client `spe_command`, set ours on a command run (ruling 4: non-object → `{}`+command on a command run, as
  sent otherwise); `run_start.request.forwardedProps` stays as sent; `snapshotDue = ignored.length > 0 ||
  command !== null`. `test-agent.ts`: answer `forwardedProps.spe_command` with RUN_STARTED, a
  `spe-compaction-manual-<runId>` marker (focus in its text), RUN_FINISHED; focus `hang` hangs after RUN_STARTED,
  `boom` gives RUN_ERROR. Note: test-agent's `compact` keyword is a substring match, so `/compact` as a *plain*
  message would trigger it: tests of non-command texts (`/compacted`) must expect that.
- **Task 2 (32; Playwright 33; early output).** `rebuild.ts`: `Conversation.commands: Map<string, {run_id,
  name, focus}>` from `run_start.command`; `RunView.command`. `anchor.ts` `classify`: a client message whose id is
  in `commands` (not in `nodes`) is known: never anchor, never new, never on the path; `edited` unless role
  `user` and `parseCommand(content)` equals the stored name/focus (ruling 3); `seen.add`. Tests: Review Focus 2
  (`kept command bubbles are known, not new`) and 4 (`compact after a stopped run`). Then a `compact-command`
  scenario in `platform/dev/e2e/sessions.py` (after #25's changes to it): type `/compact keep the canary paths`
  after two turns; bubble gone, `.spe-compaction` divider present, live and after reload; screenshots with
  `--shots`; the journal's `run_start.command`. Put the screenshots and the `run_start` line in
  `evidence/slice-2/`, post them on the PR, ask the yes/no question on decision 33. Continue without waiting.
- **Task 3 → README calls this task 4? Check numbering:** the README says tasks 1–3 early output, 4 refusals and
  marker cut short, 5 archive+docs+39. Make the slice file match the README: task 3 = Playwright + early output
  (split out of task 2 above), task 4 = 34 + 37, task 5 = 38 + docs + 39 + spec built. 5 tasks but README row
  says archive is in task 4's Review Focus line ("decision 38's check (slice 2, task 4)") — reconcile: either put
  38 in task 4 or fix that README line.
- **34.** In `admit`, on a command, after `run_start`: path empty or its last message `isCompactionMarker` →
  `endHere("refused", "Nothing to compact yet.")`; `[...focus].length > 1000` → the too-long text (ruling 6;
  Review Focus 3: 1000 ok, 1001 refused, 1000 emoji ok). `sessions.ts` `fold` already lists only runs with
  `messages.length > 0`, so a session of only `/compact` stays unlisted and `GET` 404s: test it.
- **37.** `rebuild.ts` `applyEvents`: record message ids of `TEXT_MESSAGE_START` events with the marker prefix
  and those with a `TEXT_MESSAGE_END`; after applying, drop marker messages with no END (any status, incl.
  incomplete). Test: journal cut between START and END, with and without `run_end`.
- **38.** `export.ts`: per-run message gets `spe_command: {name, focus}` from `RunView.command` for every command
  run (refused/failed too); regenerate fixtures with `UPDATE_FIXTURES=1 npm test` after adding a command run to a
  fixture journal (`platform/dev/tests/fixtures/agui-record/`). `write_run.py` `render_output`'s Compacted
  section: add "*Requested by the participant (`/compact`)*" and the focus via `fence()` when the message has
  `spe_command`; a refused/failed command run shows the command beside its status; `compactions` count already
  counts by prefix (check manual ids match). Tests in `platform/dev/tests/test_write_run_agui.py` (focus with
  four backticks).
- **Docs:** `CHAT/README.md` and `docs/getting-started.md` gain `/compact` (after #25's README edit).
  `inputs-for-plan` defects: none on `main` (ruling 5).
- **39** (task 5): de.NBI `qwen3.8-27b` instance from the slice worktree; **paid: ask first** (PR comment,
  `--end --blocked`). Then spec README status built, clarification (rulings 3, 4).

**Then:** self-review (spec coverage, placeholders, names: `MANUAL_MARKER_PREFIX`, `FOCUS_HEADING`,
`spe_command`), update `AGENTS.md`'s `/compact` track line (plan PR #27; next slice 1/2) and BACKLOG's *Next*
`/compact` item, mark #27 ready, local review round (correctness + methodology subagents, one PR comment),
address, merge (DCO, `python3 .methodology/shared/sync-agents.py --check`), clean up, move the pin in
`biohackathon`, write slice 1's start handoff, `next-session.sh --next impl/agui-compact-command-1-agent <handoff>`.

**Gotcha seen:** `docs/handoffs/2026-11-03T2350Z-compact-plan-start.md` is named ahead of the clock (it was
22:16Z when this session started), so `ls docs/handoffs | tail -1` will show it over any handoff written there
before 23:50Z today.
