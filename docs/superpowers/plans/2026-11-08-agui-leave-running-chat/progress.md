# Progress: verdicts and rulings

One entry per verdict or ruling made while building, newest last, each *decision, why, cost if wrong* with the
slice and date. The plan's own rulings are in [README.md](README.md), *Rulings*.

## Verdicts

### Decision 42's rejoin check: **live** (slice 1, 2026-11-08)

CopilotKit 1.84.1, `@ag-ui/client` 1.0.2, the fake agent; script and output in
[`evidence/slice-1/`](evidence/slice-1/) (`rejoin_check.py`; `rejoin-check.txt`, layer off;
`rejoin-check-dedupe.txt`, layer `every` and `wait`, its NOTE first).

- **B, the stop point: PASS.** A private agent shows an ordinary open, a remount and a send each id once, with no
  `connect` request; the gate does not apply.

      PASS B: no connect (open 0, remount 0); ids equal and once: open True, remount True, after send True; journal runs 4

  A (two private agents streaming at once) and D (stop in a rejoined chat journals `cancelled`) PASS too.
- **Without a layer, C1–C3 and E FAIL, on one thing only**: the first id list React commits after the connect is
  empty (`lengths in order: [0, 12, 12, …]`, at ms 0, for 31–51 ms with no layer, 21–53 ms with the `wait` layer). No duplicate, the stream whole, the
  ids equal to `GET`'s at the end:

      FAIL C1: connects 1; duplicates 0; ids missing at some tick 0; committed lists with a duplicate 0, lacking a history id 1 of 14; slow steps shown at the end 10 of 10 (exactly 10: streamed whole, none repeated); equal to GET at the end True; runs ['completed', 'completed', 'completed']
      FAIL E: connects 1; duplicates 0; ids missing at some tick 0; committed lists with a duplicate 0, lacking a history id 1 of 12; slow steps shown at the end 10 of 10 (exactly 10: streamed whole, none repeated); equal to GET at the end True; runs ['completed', 'completed']

  (C2 and C3 alike: `lacking a history id 1 of 12` and `1 of 13`.) The cause: `CopilotKitCore.connectAgent`
  treats every rejoin from a freshly loaded page as a fresh restore and calls `agent.setMessages([])` before
  connecting (`@copilotkit/core/dist/index.mjs:4308`, `:4317`).
- **With the layer in its `every` form, C1–C3 and E PASS** (`rejoin-check-dedupe.txt`, run 1):

      PASS C1: connects 1; duplicates 0; ids missing at some tick 0; committed lists with a duplicate 0, lacking a history id 0 of 13; slow steps shown at the end 10 of 10 (exactly 10: streamed whole, none repeated); equal to GET at the end True; runs ['completed', 'completed', 'completed']
      PASS E: connects 1; duplicates 0; ids missing at some tick 0; committed lists with a duplicate 0, lacking a history id 0 of 13; slow steps shown at the end 10 of 10 (exactly 10: streamed whole, none repeated); equal to GET at the end True; runs ['completed', 'completed']

  (C2 `0 of 12`, C3 `0 of 14`.) Merging only from the replay's first event on (`wait`, run 2) FAILs all four on
  the same empty list (`lacking a history id 1 of 13`, `1 of 14`, `1 of 12`, `1 of 12`).
- **Verdict: live, replayed messages matched by id** (§6 *Opening a session*, decision 42 as written; no
  clarification). The mechanism slice 3 builds, as the page did:
  - **The run in progress** is the set of message ids the replay's events name since the last `RUN_STARTED` the
    subscriber saw: each event's `messageId` and `parentMessageId` (strings), collected in an `onEvent` subscriber
    on the agent, the set emptied on each `RUN_STARTED`. `connect` replays past runs first (compacted), then the
    running run from its own `RUN_STARTED`, whole (`@copilotkit/runtime` `v2/runtime/runner/in-memory.mjs:582`,
    a `ReplaySubject(Infinity)` at :471), so the last `RUN_STARTED` is the run in progress. Slice 3 adds what the
    check did not exercise: the ids of a `MESSAGES_SNAPSHOT`'s messages seen after that `RUN_STARTED`. The chat's
    recorder sends one right after `RUN_STARTED` when the browser's messages were ignored or a command ran
    (`lib/recorder.ts:188`, `:210–212`), and `connect` passes it on, having no `messageId` to filter on
    (`in-memory.mjs:600`).
  - **The rule** (`rejoinedMessages`): keep the history in order; a history message whose id is in that set is
    replaced in place by the agent's copy; append the agent's messages whose id the history lacks; drop every
    other replayed copy.
  - **When it runs: on every message change while `connectAgent` lasts** (an `onMessagesChanged` subscriber,
    subscribed before `connectAgent` is called and from its first change, not from the replay's first event),
    **and once after it resolves**; it sets the messages only when the result differs (otherwise its own
    `setMessages` triggers it again). Why: the event pipeline works on its own clone of the agent's messages,
    taken when it starts (`@ag-ui/client` `apply/default.ts:143`, `structuredClone_(agent.messages)`), and writes
    it back on every event (`agent.ts:548`), so an outside `setMessages` lasts only to the next event; and only a
    merge on `connectAgent`'s own `setMessages([])` refills the history before React commits the empty list.
  - **The risk: an ordering race.** That merge must land after the pipeline's clone. Were it to land before, the
    history's partial copy of the running assistant message would sit in the clone and the replay's
    `TEXT_MESSAGE_START` on the same id would append to it (`default.ts:236–268`): its text repeated. It never
    did here (6 C cases, 2 E, two runs, 10 of 10 steps each), but it rests on how many awaits CopilotKit makes
    between `index.mjs:4317` and the clone, which an upgrade can change. What detects it: the streamed text shows
    each step once and grows through the run, ending on exactly the run's steps (the script's "exactly 10: none
    repeated", `SLOW_STEPS` in `platform/dev/fake_agent.py`); slice 3's Playwright acceptance keeps that check.
- **`connect` cost: one request per rejoin.** Each rejoin made one `GET /api/copilotkit/info` and one
  `POST /api/copilotkit/agent/spe/connect` (`connect requests from the rejoining page: 1` in C1–C3, D and E);
  an ordinary open and a remount made none (`connect requests on open: 0`, `on remount: 0`).

## Rulings while building

- **Slice 3, task 2's *Live* text names the verdict's mechanism** (slice 1, 2026-11-08). It now names the marker
  for the run in progress (a third argument of `rejoinedMessages`, `inProgress`), runs the merge on every
  message change during the connect and once after it resolves, and adds tests for a current run's tool call
  and result and a `MESSAGES_SNAPSHOT` during the replay, and a Playwright check that the streamed text grows
  during the run. *Why:* the check found `connectAgent` clears the messages first and a merge from the replay's
  first event on (`wait`) fails; task 2's review asked for the rest.
  *Cost if wrong:* the ordering race above makes a rejoined message repeat its text; the Playwright check shows it.
- **Slice 3's run-in-progress collector also takes a replayed `MESSAGES_SNAPSHOT`'s ids** (slice 1, 2026-11-08),
  all of them, and is its own tested function (`nextInProgress`). *Why:* task 3's review found the recorder's
  snapshot can sit inside the running run's replay with no `messageId`, so a collector of `messageId` and
  `parentMessageId` alone keeps the history's copy over it; all ids, because the snapshot is the run's own branch
  as the server holds it, never older than the history's, and replacing an equal copy changes nothing. *Cost if
  wrong:* none found: a snapshot id the history holds unchanged is replaced by an equal copy.
- **The collector also takes a `TOOL_CALL_START`'s `toolCallId`, and shares one subscription with the merge**
  (slice 1's review, 2026-11-08). *Why:* `@ag-ui/client` creates the assistant message with id `toolCallId` when the
  event names no parent; one `agent.subscribe` made before `connectAgent` is what the passing page did. *Cost if
  wrong:* an extra id in `inProgress` only swaps a copy for an equal one.
- **`recorder.test.ts` keeps its own `sessionOf`** (slice 1, task 1), against task 1 step 3's "drops its own
  `sessionOf`/`isRunning`": `isRunning` went, but the test's `handleOf` still needs a run key's session id to find a
  handle to cancel, and `sessions.ts` exports no parser for it. *Cost if wrong:* a one-line helper drifts from
  `runKey`'s format; the `running` tests then fail at once.
- **Slice 2 was claimed on its own branch, after a chain started it on slice 1's** (slice 2, 2026-11-09). The
  session was started on `impl/agui-leave-running-chat-1-rejoin-check`, merged as #57; the handoff named slice 2,
  so it claimed `impl/agui-leave-running-chat-2-agents` (#58) and deleted the stray re-claim. *Cost if wrong:* none.
- **Every list fetch is applied in the order it started** (`lib/list-order.ts`; slice 2, task 2's review). *Why:*
  `gone` is sticky (ruling 4), and a list fetch started before a New chat's first run that answers after a newer
  list put the session in `gone`: the open chat was swapped for a new one at its run's end and could not be
  reopened until a reload. So `SessionAgent` and `useRunReconcile` take a `fetchList`, and the page drops a list
  older than the last one it applied. *Cost if wrong:* a list dropped as stale is only a refresh skipped; the next
  one applies.
- **`SessionAgent` also takes `onRecorded` and `useRunReconcile` an `onEnded`** (slice 2, task 2). *Why:* the title
  trigger's "once the run is recorded" path needs the first, and the page must hear a run's end after its list on
  every path, a failed list fetch included, or a holder stays mounted. *Cost if wrong:* none: two callbacks.
- **A run's errors reach the bar through its holder only** (slice 2, task 2): `CopilotChat`'s `onError` skips the run
  error codes, so the open session's errors do not show twice. *Cost if wrong:* an error code the filter misses
  shows twice; the Playwright error checks show it.
- **The row's running spinner keeps turning under `prefers-reduced-motion: reduce`** (slice 2, task 3), reading task
  3's "a CSS rotation, still under `prefers-reduced-motion: reduce`" as "still rotating under it" (the task review
  read the opposite). *Why:* it is the only motion saying a run in another session goes on. *Cost if wrong:* one
  CSS line moved into the `reduce` block.
- **The chat header has no running mark, only the Delete rule** (slice 2, task 3). *Why:* the header's `⋯` is always
  shown and takes the mark's place (§6 *Layout*). *Cost if wrong:* a header mark added later.
- **The mid-run freeze of a reopened chat is fixed in this slice** (slice 2, task 4; `715305f`, `de727a4`). *Why:*
  decision 41 is slice 2's: `@ag-ui/client` copies its subscribers at a run's start, so a chat reopened mid-run
  froze; the holder now forwards message changes, and the page redraws the open chat only while it was mounted
  mid-run. *Cost if wrong:* a missed case freezes again; `leave-running` step 3 catches it.
- **The early-output comment asks a second question, no gate: should the open row show its running spinner?**
  (slice 2, task 4 step 5 names only the first). *Why:* the open row, and every row on a touch screen, shows `⋯`
  in the mark's place (§6 *Layout*), so the user never sees the mark there (#58's review, finding 2). *Cost if
  wrong:* none; a *no* keeps §6 as it is.
- **Only a session's latest run ends it** (`lib/run-watch.ts`, #58's review, finding 1): the watch moves out of
  `use-run-reconcile.ts` into a tested module. *Why:* a run started while the previous run's list was pending was
  dropped from `streaming` when that list came back, and a switch then unmounted its holder mid-run. *Cost if
  wrong:* none found: an older run's end only skips `onEnded`, which the newer one calls.
