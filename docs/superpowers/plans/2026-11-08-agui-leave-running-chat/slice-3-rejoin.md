# Slice 3/3: rejoin, refresh and errors

Branch `impl/agui-leave-running-chat-3-rejoin`. Implements decision 42 (live, or its fallback, as
[`progress.md`](progress.md)'s verdict says), the rest of decision 44 (refresh, polling, errors), the docs and the
spec's built status. Global constraints and rulings: [README.md](README.md). `CHAT` is
`platform/agui/copilotkit-chat`.

Spec: [§6 *Opening a session*, *Refresh*, *Errors*](../../../specs/2026-10-15-agui-frontend-design/06-chat-ui.md#the-sidebar).

## Task 1: refresh on focus, polling, and a rejoined run's reconcile (decision 44; Review Focus 4)

Acceptance (decision 44, Playwright, task 3): a run started from a second tab shows its mark in the first within
3 s of the first regaining focus, and the polling stops once it ends (no list request for 5 s).

**Files:**
- Create: `CHAT/lib/refresh.ts`, `CHAT/lib/refresh.test.ts`
- Modify: `CHAT/lib/reconcile.ts`, `CHAT/lib/reconcile.test.ts`, `CHAT/app/page.tsx`

**Interfaces:**
- Consumes: `runningIds`, `Live` (slice 2, task 1).
- Produces:

  ```ts
  export const POLL_MS = 2000;
  /** True while the list shows a session running that no holder in the page streams. */
  export function needsPoll(list: readonly SessionMeta[], live: Live): boolean;
  // lib/reconcile.ts: a rejoined run's end, whose start the page does not know
  export async function waitNotRunning(fetchList: FetchList, id: string, sleep?): Promise<{ list: SessionMeta[]; saved: boolean }>;
  //   fetch, then up to RECONCILE_RETRIES more RECONCILE_DELAY_MS apart, until the list shows `id` with running false
  ```

- [ ] **Step 1: Failing tests**: `needsPoll`: `polls while a running session is not streamed, stops when every
  running one is` (list A running, B running, live streams A → true; streams both → false; none running → false);
  `waitNotRunning`: `ends once the list shows the session not running`, `saved false after 5 retries`.
- [ ] **Step 2: Run** `npm test` — FAIL. **Step 3: Implement**; in `page.tsx`, `refresh()` on
  `visibilitychange` (visible) and `focus`, and an interval of `POLL_MS` while `needsPoll` holds (cleared when
  not). A holder that rejoined (task 2) reconciles its run's end with `waitNotRunning`, not `reconcile`.
  While here (#58's review, finding 5): a runtime connection that drops from `Connected` re-disables the
  buttons and re-arms the first-load timer (`page.tsx`, the `connected` effects); the refresh must not start
  from, or be stopped by, that drop: keep the first load once only, and leave the buttons enabled.
- [ ] **Step 4: Run** `npm test && npm run build` — PASS. **Step 5: Commit** `Chat: fetch the list on focus and poll
  while another tab runs (decision 44)`.

## Task 2: opening a running session (decision 42)

**Live (the spec's design; slice 1's verdict).** Acceptance (decision 42): reload during a slow run: the chat keeps
streaming, every message id is shown once, and at the run's end the messages equal `GET`'s; the same from a second
tab; stop in the rejoined chat journals `cancelled`; opening a session not running makes no `connect` request.

- Create: `CHAT/lib/rejoin.ts`, `CHAT/lib/rejoin.test.ts`; modify `CHAT/app/session-agent.tsx`, `app/page.tsx`,
  `CHAT/lib/run-watch.ts` (+ its test) and `app/use-run-reconcile.ts` (progress.md, *Rulings while building*: the
  connect's run ends through `waitNotRunning`).
- `export async function rejoinAgent(agent, connect)` (lib/rejoin.ts): the subscribe-merge-connect loop below, apart
  from React, tested on a fake agent; its last merge runs however the connect ends.
- `export function rejoinedMessages(history: Message[], current: Message[], inProgress: ReadonlySet<string>): Message[]`
  — `history` is the journal's branch; `current` the agent's messages; `inProgress` the ids of the run in
  progress. Keeps `history` in order, each message replaced in place by `current`'s copy of the same id when
  `inProgress` holds that id, and appends `current`'s messages whose id `history` lacks; every other replayed copy
  is dropped. The marker slice 1's verdict found: `inProgress` holds, for the replayed events since the last
  `RUN_STARTED`, each event's `messageId` and `parentMessageId` (strings), the `toolCallId` of a `TOOL_CALL_START` (`@ag-ui/client`
  creates the assistant message with that id when the event names no parent; pydantic-ai always names one) and the ids of every message of a
  `MESSAGES_SNAPSHOT` (the recorder sends one right after `RUN_STARTED`, `lib/recorder.ts:210–212`; all its ids,
  because it is the run's own branch as the server holds it, never older than the history's copy).
- `export function nextInProgress(ids: ReadonlySet<string>, event: BaseEvent): ReadonlySet<string>` — the
  collector, called from an `onEvent` handler in the same `agent.subscribe` as the `onMessagesChanged` one below, made before
  `connectAgent` (as slice 1's passing page did): an empty set on `RUN_STARTED`, else `ids` plus the
  event's ids as above.
- Tests: `a past run replayed is shown once`, `the current run's partial message is replaced by its live copy`,
  `a new message of the current run is appended`, `no replay: history unchanged`, `a tool call and its result of
  the current run keep each id once`, `a MESSAGES_SNAPSHOT during the replay keeps each id once`; and the
  collector itself, fed a replayed event sequence (a past run's events, `RUN_STARTED`, a `MESSAGES_SNAPSHOT`
  with a changed copy of a history message, text and tool-call events): `nextInProgress marks the current run's
  ids, a snapshot's included, and no past run's`, and `rejoinedMessages` over its result shows the snapshot's
  copy, each id once.
- `SessionAgent` gains `rejoin: boolean` (the `GET` answered `running` and `live.streaming` lacks the id, or an
  open idle session turned `running` in a list fetch): it calls `copilotkit.connectAgent({ agent })` once and
  applies `rejoinedMessages` **on every message change while the connect lasts** (an `onMessagesChanged`
  subscriber made before `connectAgent` is called, so it also catches `connectAgent`'s own `setMessages([])`; not
  only from the replay's first event, which slice 1 found fails) **and once after it resolves**, setting the
  messages only when the result differs; then it joins `live.streaming` (`runStarted`) until the run ends. Why,
  and the ordering race this rests on: [`progress.md`](progress.md), *Verdicts*. At the run's end, once the list
  shows it saved, the holder sets the agent's messages to `GET /api/sessions/{id}`'s when they differ (the replay
  can bring past runs of a branch the journal's tip has left), unless a newer run has started; a failed `GET`
  keeps the chat, with no error bar (`lib/run-watch.ts`; progress.md, *Rulings while building*).
- Task 3's `check_rejoin` checks the streamed text grows during the run (the slow-step count rises between ticks),
  not only its final count, which shows each step once (the race's symptom is repeated text).

- [ ] **Steps**: failing tests; run (FAIL); implement; `npm test && npm run build` (PASS); commit `Chat: rejoin a
  running session (decision 42)`.

## Task 3: run errors with their title; Playwright (decisions 42, 44; Review Focus 5)

**Files:**
- Modify: `CHAT/lib/reconcile.ts` (or a new `lib/run-error.ts`), its test, `CHAT/app/page.tsx`,
  `platform/dev/fake_agent.py`, `platform/dev/e2e/sessions.py`

**Interfaces:**
- `export function runErrorText(title: string | null, message: string, open: boolean): string` — `message` when
  open; else `“<title>”: <message>`, `“New chat”: <message>` when `title` is null or `""`.
- `fake_agent.py`: a message containing `slow-fail` streams the slow steps, then raises (docstring updated);
  checked before the `fail` branch, which would otherwise raise at once.

- [ ] **Step 1: Failing tests**: `runErrorText: the open session's error is bare`, `…: a left session's error
  names it`, `…: a session without a title is New chat`. Run (FAIL), implement, wire `SessionAgent.onError`
  through it with the list's title, run (PASS).
- [ ] **Step 2: Playwright** in `sessions.py`: `check_rejoin` (scenario `rejoin`: decision 42's checks, the live
  or the fallback ones), and `check_running_marks` (scenario `running-marks`: decision 44's remaining checks: a
  second context starts "slow X", the first page gets focus (`page.bring_to_front()` and a `focus` event) and
  shows X's mark within 3 s; after X ends, no `GET /api/sessions` for 5 s; "slow-fail Y" left for another
  session shows `“<Y's title>”: …` in the bar). Both in `LOCAL` and `all`.
- [ ] **Step 3: Run** `--scenario rejoin`, `--scenario running-marks`, `--scenario all` — PASS.
- [ ] **Step 4: Commit** `Chat: run errors name their session; e2e for rejoin and marks (decisions 42, 44)`.

## Task 4: docs and the spec's status

- [ ] **Step 1:** the chat's `README.md` (*Sessions*): running marks, rejoin (or the fallback), polling;
  `docs/getting-started.md` where it says a run holds the chat (grep `New chat`, `during a run`, `disabled`).
- [ ] **Step 2:** spec README: decisions 26 and 40–44 built (the status line); §12 gains what implementation
  verified or changed, with any `progress.md` rulings that touch the spec; a clarification (`folded`) for each spec text
  that changes.
- [ ] **Step 3:** `AGENTS.md`, *Current work*: remove the track's line (the last slice); this plan's README:
  status column; `docs/README.md`: the plan's row says done. Anything still open on the track (an answer to
  slice 2's screenshot question not acted on, a ruling's follow-up) goes to `BACKLOG.md` with its pointer, so the
  track closes with nothing pending.
- [ ] **Step 4:** grep the repo for the locked-page wording (`switching is disabled`, `disabled during a run`,
  `agent.isRunning`) and rewrite each current-design text left (history stays).
- [ ] **Step 5: Commit** `Docs: leaving a running chat is built`.
