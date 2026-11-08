# Slice 2/3: an agent per session

Branch `impl/agui-leave-running-chat-2-agents`. Implements decisions 26, 40 and 41, and of 44 the running mark
and the Delete rule; builds the spec's early-output screenshot (task 4). Read the verdict in
[`progress.md`](progress.md) first: if slice 1 found a mechanism this slice's holder needs (e.g. how an agent is
dropped), it applies here. Global constraints and rulings: [README.md](README.md). `CHAT` is
`platform/agui/copilotkit-chat`.

Spec: [§6 *The sidebar*](../../../specs/2026-10-15-agui-frontend-design/06-chat-ui.md#the-sidebar) (*Layout*, *A
session's agent*, *Opening a session*, *Leaving a running chat*).

## Task 1: the owner of the page's live sessions (decision 40; Review Focus 2)

Acceptance (decision 40, `npm test`): the page's set of live sessions keeps a running one after a switch and
drops it at its run's end unless it is open.

**Files:**
- Create: `CHAT/lib/live-sessions.ts`, `CHAT/lib/live-sessions.test.ts`

**Interfaces:**
- Produces, all pure (a React state value, transitions return a new one):

  ```ts
  export type Live = { open: string | null; streaming: ReadonlySet<string>; seen: ReadonlySet<string>; gone: ReadonlySet<string> };
  export const EMPTY: Live;
  export function openSession(live: Live, id: string): Live;          // open := id
  export function runStarted(live: Live, id: string): Live;           // streaming += id
  export function runEnded(live: Live, id: string): { live: Live; startNew: boolean };
  //   streaming -= id; startNew: id was open and is in `gone` (it left the list while streaming)
  export function listed(live: Live, ids: ReadonlySet<string>): { live: Live; startNew: boolean };
  //   seen += ids; gone += each seen id missing from ids; startNew: the open id is gone and not streaming
  export function held(live: Live): string[];                         // open (if not gone) ∪ streaming, open first
  export function isHeld(live: Live, id: string): boolean;
  export function runningIds(list: readonly { id: string; running: boolean }[], live: Live): Set<string>;
  //   list ids with running ∪ streaming — the one set the mark, Delete and (slice 3) polling read
  ```

- [ ] **Step 1: Write the failing tests** in `live-sessions.test.ts`:
  - `keeps a running session held after a switch, drops it at its run's end`: open A, runStarted A, open B →
    `held` = [B, A]; runEnded A → [B], startNew false.
  - `the open session stays held after its run ends`: open A, run A, end A → [A].
  - `a streaming session that leaves the list keeps its holder until its run ends`: open A, listed {A}, run A,
    listed {} → held [A], startNew false; runEnded A → held [], startNew true.
  - `an open session deleted elsewhere while idle starts a new one`: open A, listed {A}, listed {} → startNew true.
  - `a streaming session never listed is not dropped by a list without it` (ruling 4): open A, run A, open B,
    listed {} → held [B, A].
  - `runningIds joins the list's running and the page's streaming`.
- [ ] **Step 2: Run** `npm test` — FAIL (module missing).
- [ ] **Step 3: Implement** `lib/live-sessions.ts` (no React import: it is tested under `node --test`).
- [ ] **Step 4: Run** `npm test` — PASS.
- [ ] **Step 5: Commit** `Chat: one owner of the page's live sessions (decision 40)`.

## Task 2: a holder and a private agent per live session; switching enabled (decisions 26, 40, 41; Review Focus 1, 3)

Acceptance: decision 26's and 41's Playwright checks, and decision 40's first half (runs in two sessions stream
at once), in `check_leave_running` (task 4 writes it; this task runs the unit tests and the build).

**Files:**
- Create: `CHAT/app/session-agent.tsx`
- Modify: `CHAT/app/page.tsx`, `CHAT/app/use-run-reconcile.ts`, `CHAT/README.md` (*Sessions*)

**Interfaces:**
- Consumes: task 1's `Live` transitions; `TitleTrigger`, `waitListed`, `reconcile` (`lib/reconcile.ts`, unchanged).
- Produces:

  ```tsx
  // app/session-agent.tsx: renders nothing itself; the page mounts one per held(live) id, keyed by id.
  export function SessionAgent(props: {
    id: string;
    initialMessages: Message[];            // set once the agent is ready (the GET's messages, or [] for a New chat)
    onReady: (id: string) => void;         // its registered agent exists: the page may draw CopilotChat on it
    onRunStarted: (id: string) => void;    // → runStarted, the title trigger
    onRunEnded: (id: string) => void;      // → runEnded (after the reconcile below has its list)
    onList: (list: SessionMeta[]) => void;
    onError: (id: string, message: string) => void;
  }): null;
  export const agentIdOf = (id: string) => `spe-${id}`;
  // app/use-run-reconcile.ts: takes the agent instead of looking up "spe"
  export function useRunReconcile(agent: AbstractAgent, opts: { id: string; onList; onError; onStarted; onRecorded }):
    { noteRunError: (message: string) => void };
  ```

- [ ] **Step 1: `SessionAgent`**: `useAgent({ agentId: agentIdOf(id), runtimeAgentId: "spe", threadId: id,
  updates: [UseAgentUpdate.OnRunStatusChanged] })`. The hook first returns a provisional agent (`isReady: false`)
  and the registered one on a later render; messages set on the provisional one are lost. So, in an effect keyed
  on the agent object, once `isReady`: `agent.setMessages(initialMessages)` (once per holder) and `onReady(id)`.
  `useRunReconcile(agent, …)` with `id` fixed (a run's session is the holder's, no longer "the open one when it
  started"); it and `agent.subscribe({ onRunErrorEvent })` (errors to `onError(id, …)` and `noteRunError`)
  re-subscribe when the agent object changes.
- [ ] **Step 2: `page.tsx`**: drop the page-level `useAgent({ agentId: "spe" })` and `busy`; keep `live` in state
  and a `Map<string, Message[]>` ref of initial messages. `open(id)`: if `isHeld(live, id)`, `openSession` with
  no fetch and bump `requestRef` (decision 41; a late `GET` for an earlier click is ignored as today); else
  `fetchSession`, store its messages, `openSession`. `startNew()`: a fresh UUID, `[]`, `openSession`. Render
  `held(live).map(id => <SessionAgent key={id} …/>)`; keep a `ready: Set<string>` from `onReady` (an id leaves it
  when its holder unmounts). Draw `CopilotChat` with `agentId={agentIdOf(active)}`, `key={active}`, inside
  `CopilotChatConfigurationProvider agentId={agentIdOf(active)} threadId={active} hasExplicitThreadId={false}`,
  only once `ready.has(active)`: `CopilotChat` looks its agent up by `agentId` and throws "Agent … not found after
  runtime sync" before the holder's effect has registered it; until then the chat area shows the loading state.
  The first-load effect and the 15 s "runtime unreachable" message, which waited on the page-level agent's
  `isReady`, wait on `useCopilotKit().copilotkit.runtimeConnectionStatus` instead (a holder's agent is registered
  while the runtime is still pending, so its `isReady` does not say the runtime answered).
  Every list fetch goes through `listed()`; a `startNew` it returns starts a new session.
- [ ] **Step 3: Enable switching**: the sidebar's `onNew`/`onOpen` lose their `agent.isRunning` guards;
  `running` no longer disables *New chat* or the rows. Remove the comments in `app/sidebar.tsx`,
  `app/use-run-reconcile.ts` and `app/page.tsx` that assume a locked page (inputs-for-plan). The chat's README,
  *Sessions*, says switching and New chat stay enabled during a run and the run goes on.
- [ ] **Step 4: Run** `npm test && npm run build` — PASS; then by hand against the fake agent (as
  `sessions.py` starts it): a "slow" run in A, open B, open A: A still streams.
- [ ] **Step 5: Commit** `Chat: an agent per session; leave a running chat (decisions 26, 40, 41)`.

## Task 3: the running mark and the Delete rule (decision 44, part)

Acceptance (decision 44, Playwright, in task 4): two running sessions both show the mark, which goes at each run's
end; their Delete items are disabled.

**Files:**
- Modify: `CHAT/app/sidebar.tsx`, `CHAT/app/chat-header.tsx`, `CHAT/app/row-menu.tsx`, `CHAT/app/icons.tsx`,
  `CHAT/app/globals.css`, `CHAT/app/page.tsx`

**Interfaces:**
- Consumes: `runningIds(list, live)` (task 1).
- Produces: `Sidebar` and `ChatHeader` take `runningIds: ReadonlySet<string>` in place of `running: boolean`; a
  row with its id in the set renders `<span className="spe-row-running"><Spinner /><span
  className="spe-sr-only">Running</span></span>` at its right end, replaced by `⋯` where `⋯` is shown (§6
  *Layout*); `deleteDisabled={runningIds.has(id)}` for the row menu and the header.

- [ ] **Step 1: Implement** the props, the spinner (`Spinner` in `icons.tsx`, a CSS rotation, still under
  `prefers-reduced-motion: reduce`) and the CSS, in Open WebUI's gray scale.
- [ ] **Step 2: Run** `npm run build` — PASS.
- [ ] **Step 3: Commit** `Chat: mark running sessions; no Delete while one runs (decision 44)`.

## Task 4: Playwright, and the screenshot (decisions 26, 40, 41, 44 part; early output)

**Files:**
- Modify: `platform/dev/e2e/sessions.py`
- Create: `docs/superpowers/plans/2026-11-08-agui-leave-running-chat/evidence/slice-2/*.png`

- [ ] **Step 1: Replace the locked-page expectations**: `check_stop` (around lines 693–711) no longer expects
  *New chat* and the rows disabled during the run; it expects the open row's mark instead. The waits at
  `two_turn` (around 1168) and `slow_loop` (around 1240) wait for a run's end with a helper
  `wait_run(r, session_id)`: the open row (found by the session id, not its title, which a model-written title
  can replace mid-wait) has no `.spe-row-running`; seeing the mark first is not required, since a quick run can
  end before the first check (timeouts as today).
- [ ] **Step 2: Add `check_leave_running(r)`** and scenario `leave-running` (in `LOCAL` and `all`):
  1. New chat A, send "slow A"; at once *New chat* and A's sibling rows are enabled (26).
  2. New chat B, send "slow B"; both rows show the mark; their Delete items (row and header) are disabled (44).
  3. Open A with no `GET /api/sessions/{A}` request (route logging): A's last assistant message keeps growing
     (two readings 1.5 s apart) (41); toggle A → B → A within 300 ms: A shows A's messages (Review Focus 1).
  4. Both runs end: both journals end `run_end` `completed`, A's with one run and no `cancelled` (26, 40); each
     mark goes; A's messages equal `GET`'s ids (41).
  5. Stop: "slow C" in a New chat, stop in C's own chat → C's journal `cancelled` (26).
  6. A New chat's row appears also with the journal's append delayed (`--save-delay-ms`, as `check_stop` does) (26).
  7. Open B after its holder was dropped: opens from the journal, no console error (Review Focus 3).
- [ ] **Step 3: The early output**: a screenshot with A and B marked running and A reopened mid-stream, light and
  dark (`--color-scheme`), into `evidence/slice-2/`.
- [ ] **Step 4: Run** `python3 platform/dev/e2e/sessions.py --scenario leave-running`, `--scenario stop`, then
  `--scenario all` — PASS.
- [ ] **Step 5: Commit** `E2E: leave a running chat (decisions 26, 40, 41, 44)`; after the PR opens, one comment
  with the screenshots asking, with no gate: "Does a reply that finished while you were away need a mark of its
  own? (yes/no)" (spec *inputs-for-plan*: a "yes" is a new slice-3 task and a clarification).
