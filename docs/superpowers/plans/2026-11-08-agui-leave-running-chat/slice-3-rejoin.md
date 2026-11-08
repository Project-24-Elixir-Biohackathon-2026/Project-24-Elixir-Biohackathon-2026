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
- [ ] **Step 4: Run** `npm test && npm run build` — PASS. **Step 5: Commit** `Chat: fetch the list on focus and poll
  while another tab runs (decision 44)`.

## Task 2: opening a running session (decision 42)

Build the branch the verdict names; delete the other paragraph from this file in the same commit.

**Live (the spec's design).** Acceptance (decision 42): reload during a slow run: the chat keeps streaming, every
message id is shown once, and at the run's end the messages equal `GET`'s; the same from a second tab; stop in the
rejoined chat journals `cancelled`; opening a session not running makes no `connect` request.

- Create: `CHAT/lib/rejoin.ts`, `CHAT/lib/rejoin.test.ts`; modify `CHAT/app/session-agent.tsx`, `app/page.tsx`.
- `export function rejoinedMessages(history: Message[], current: Message[]): Message[]` — `history` is the
  journal's branch; `current` the agent's messages after the replay. Keeps `history` in order, each message
  replaced in place by `current`'s copy of the same id when that copy belongs to the run in progress (after the
  last replayed `RUN_STARTED`, as slice 1's verdict found it marked), and appends `current`'s messages whose id
  `history` lacks; every other replayed copy is dropped. The verdict may name a different marker for "the run in
  progress"; use it.
- Tests: `a past run replayed is shown once`, `the current run's partial message is replaced by its live copy`,
  `a new message of the current run is appended`, `no replay: history unchanged`.
- `SessionAgent` gains `rejoin: boolean` (the `GET` answered `running` and `live.streaming` lacks the id, or an
  open idle session turned `running` in a list fetch): it calls `copilotkit.connectAgent({ agent })` once, applies
  `rejoinedMessages` as slice 1 did, and joins `live.streaming` (`runStarted`) until the run ends.

**Fallback (only if the verdict says so).** Acceptance: its own check (decision 42): a session opened during a run
from a second tab shows its saved part with the running mark, the composer and stop disabled, and at the run's end
its messages equal `GET`'s. `SessionAgent` with `frozen: true` disables the composer (`CopilotChat`'s input slot,
`app/command-input.tsx`) and stop; when `waitNotRunning` (task 1) ends, the page fetches `GET` and remounts the
holder with its messages.

- [ ] **Steps**: failing tests; run (FAIL); implement; `npm test && npm run build` (PASS); commit `Chat: rejoin a
  running session (decision 42)` (or `…: show a running session's saved part (decision 42's fallback)`).

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
