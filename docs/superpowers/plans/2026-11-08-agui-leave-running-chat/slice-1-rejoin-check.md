# Slice 1/3: `running` and the rejoin check

Branch `impl/agui-leave-running-chat-1-rejoin-check`. Implements decision 43 and runs decision 42's check (spec
README, *Early output*, leaving a running chat, first part); the verdict decides slice 3, task 2. Global
constraints and rulings: [README.md](README.md). `CHAT` is `platform/agui/copilotkit-chat`.

## Task 1: `running` in the session API (decision 43)

Spec: [§6 *Session API*](../../../specs/2026-10-15-agui-frontend-design/06-chat-ui.md#session-api). Acceptance:
`npm test` (`api`): `running` true between a run's `run_start` and `run_end`, false before and after, also for a
cancelled and a failed run; the answer-shape tests gain the key.

**Files:**
- Modify: `CHAT/lib/sessions.ts` (`SessionMeta`, `toMeta`, new exports), `CHAT/lib/recorder.ts` (import `runKey`)
- Test: `CHAT/lib/recorder.test.ts`, `CHAT/lib/api.test.ts`, `CHAT/lib/sessions.test.ts`

**Interfaces:**
- Produces: `SessionMeta.running: boolean` (so `SessionView` has it too, ruling 3);
  `export function runKey(threadId: string, runId: string): string` (moved from `recorder.ts`, same body);
  `export function isRunning(id: string): boolean` (some key of `shared().running` names session `id`).

- [ ] **Step 1: Write the failing tests.** In `recorder.test.ts` (it already drives runs through the runtime
  against `lib/test-agent.ts`, and has a local `isRunning`, which the test now imports from `sessions.ts`):

  ```ts
  test("running: true in the list and GET between run_start and run_end, false before and after", ...)
  // before the run: list lacks the id; during a "hang" run: list item and GET one have running === true;
  // after the client aborts (cancelled), after an "error" run (failed), after a plain run (completed):
  // running === false in both answers
  ```

  In `api.test.ts` and `sessions.test.ts`, every expected key set of a list item, `GET` one and `PATCH` answer
  gains `running` (false for seeded journals: nothing runs).

- [ ] **Step 2: Run** `cd CHAT && npm test` — expected: the new test and the shape tests FAIL (no `running`).
- [ ] **Step 3: Implement.** Move `runKey` to `sessions.ts`; `isRunning(id)` parses each key of
  `shared().running` (`JSON.parse(key)[0] === id`); `toMeta` sets `running: isRunning(e.id)`. `recorder.ts`
  imports `runKey`; `recorder.test.ts` drops its own `sessionOf`/`isRunning`.
- [ ] **Step 4: Run** `npm test && npm run build` — expected: PASS.
- [ ] **Step 5: Commit** `Chat: answer running in the session API (decision 43)`.

## Task 2: the rejoin check (decision 42; Review Focus 3)

Throwaway (ruling 2). Spec: [§6 *A session's agent*, *Opening a session*](../../../specs/2026-10-15-agui-frontend-design/06-chat-ui.md#the-sidebar),
inputs-for-plan *Leaving a running chat*.

**Files:**
- Create (removed in task 3): `CHAT/app/rejoin-check/page.tsx`
- Create (kept): `docs/superpowers/plans/2026-11-08-agui-leave-running-chat/evidence/slice-1/rejoin_check.py`,
  its output `evidence/slice-1/rejoin-check.txt` and screenshots

**Interfaces:**
- Consumes: task 1's `running` in `GET /api/sessions/{id}`.
- The page reads `?a=<id>&b=<id>&mode=stream|open|rejoin`. For each id it mounts a holder: thread-scoped
  `useAgent({ agentId: "spe-" + id, runtimeAgentId: "spe", threadId: id })`. In 1.84.1 that hook first returns a
  provisional agent (`isReady: false`) and registers the real one in an effect, returning it on a later render
  (`react-core` `useAgent`); messages set on the provisional one are lost (`page.tsx`'s comment at the first-load
  effect). So `mode=open` and `mode=rejoin` call `agent.setMessages(GET.messages)` once `isReady` is true, in an
  effect keyed on the agent object; `mode=rejoin` then calls `useCopilotKit().copilotkit.connectAgent({ agent })`
  when `GET` answers `running`. Each holder renders, only once `isReady` is true (`CopilotChat` looks its agent up
  by `agentId` and throws "Agent … not found after runtime sync" before it is registered),
  `<CopilotChatConfigurationProvider agentId={"spe-"+id} threadId={id} hasExplicitThreadId={false}><CopilotChat
  key={id} agentId={"spe-"+id} /></…>` and a
  `<pre data-testid="ids-<id>">` with `agent.messages.map(m => m.id)` as JSON, updated on change. A button per
  holder unmounts and remounts it (check B's re-registration).

- [ ] **Step 1: Write the page** as above (`"use client"`, inside `CopilotKitProvider runtimeUrl="/api/copilotkit"`).
- [ ] **Step 2: Write `rejoin_check.py`** on `sessions.py`'s harness (its `Run`, `wait_http` and `KEY`, and
  the way its `main` starts the fake agent and the standalone server, on its ports): it starts the fake agent and the built server, logs every request to `/api/copilotkit/**`
  (method, path: `…/agent/spe/run`, `…/agent/spe/connect`, `…/agent/spe/stop`), and for each check prints
  `PASS`/`FAIL` and the ids shown vs the journal's (`GET /api/sessions/{id}`'s `messages` ids):
  - **A. Two private agents at once:** sessions A and B, a "slow" message sent in each via its chat; both show
    growing text at once; both journals end `run_end` `completed`.
  - **B. Ordinary open (the stop point):** a session with three completed runs, `mode=open`: no `connect`
    request; ids shown equal `GET`'s, each once; the same after unmount and remount (no "already registered"
    error in the console); sending a message there runs and the journal gains one run.
  - **C. Rejoin after a reload:** a "slow" run in A, reload mid-run with `mode=rejoin`: one `connect` request;
    record every id shown more than once, and every journal id not shown, at 1 s intervals until the run ends;
    at the end compare with `GET`'s ids. Run it once on a session with earlier runs (the runtime's replay of past
    runs) and once on a fresh one. The earlier runs are sent through the same server process, by the script,
    before the slow run: `InMemoryAgentRunner` replays only runs made since the server started, so a session
    seeded from journal files alone would have nothing to replay and C would not exercise duplicates.
  - **D. Stop in the rejoined chat:** as C, then CopilotChat's stop button; the journal's last `run_end` is
    `cancelled`.
  - **E. Second tab:** as C, with the reload replaced by a second browser context opening A with `mode=rejoin`.
- [ ] **Step 3: Run it**: `cd CHAT && npm run build && python3 ../../../docs/superpowers/plans/2026-11-08-agui-leave-running-chat/evidence/slice-1/rejoin_check.py | tee …/rejoin-check.txt`
  — expected: A, B, D, E PASS; C's output is the data the verdict reads.
- [ ] **Step 4: If C shows duplicates or gaps**, try the layer §6 allows (inputs-for-plan, *What "made to"
  allows*): after `connectAgent` resolves and on each message change during it, set the agent's messages to
  `rejoinedMessages(history, agent.messages)` (slice 3's `lib/rejoin.ts` rule, inlined here: keep the history,
  drop a later message whose id the history already holds unless it belongs to the current run, whose copy
  replaces the history's partial one in place). Re-run C and E; record both runs.
- [ ] **Step 5: Commit** the page, the script and its output: `Rejoin check: page, script and first run (decision 42)`.

## Task 3: the verdict, and the stop point

- [ ] **Step 1: Write the verdict** in [`progress.md`](progress.md), *Verdicts*: B's result (the stop point);
  **live** (C and E show each id once with the layer, or without it) or **fallback**; the mechanism slice 3
  builds (no layer, the layer of task 2 step 4, or another found here); what `connect` requests cost (one per
  rejoin). Quote the lines of `rejoin-check.txt` it rests on.
- [ ] **Step 2: If B failed** (an ordinary open loses or repeats messages, the holder's `isReady` handling of
  task 2 in place): stop, as `development-workflow.md`, *Gates*, says: write the handoff (`methodology handoff new
  docs/superpowers/plans/2026-11-08-agui-leave-running-chat/handoffs <slug>`), commit and push; write one comment
  file with the evidence and what it puts at risk (decisions 40 and 41); `methodology gate open <PR> <comment
  file>`, then `methodology gate wait <PR>` in the background, and end the session. Do not merge.
- [ ] **Step 3: If the verdict changes the spec** (fallback, or a mechanism other than "matched by id"): add
  clarification 28 (`folded`), rewrite decision 42's line and §6 *Opening a session*, and rewrite slice 3,
  task 2's text to the branch it builds. Otherwise only `progress.md` changes.
- [ ] **Step 4: Remove `CHAT/app/rejoin-check/`**; `npm run build` passes.
- [ ] **Step 5: Commit** `Rejoin check: verdict <live|fallback>, page removed`; the PR body quotes the verdict
  and asks nothing (not a gate, unless step 2).
