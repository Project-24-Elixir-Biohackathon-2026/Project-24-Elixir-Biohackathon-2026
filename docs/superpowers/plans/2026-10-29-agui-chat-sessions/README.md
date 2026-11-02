# AG-UI chat sessions: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` (`AGENTS.md`,
> *Working Conventions*) to implement one slice per session and PR. Steps use checkbox (`- [ ]`) syntax.

**Goal:** the CopilotKit chat gets an Open WebUI-style sidebar of sessions, recorded on the server from the
agent's AG-UI stream, kept on a `chat-sessions` volume and exported by `archive.yml` like an Open WebUI run.

**Spec:** [`docs/superpowers/specs/2026-10-29-agui-chat-sessions-design.md`](../../specs/2026-10-29-agui-chat-sessions-design.md)
(decisions 1–15; latest clarification: 5). Each slice file links the sections it implements.

**Architecture.** All new chat-UI logic lives in `platform/agui/copilotkit-chat/lib/` as plain TypeScript that
`node --test` runs without Next.js: the store (`sessions.ts`), the recorder middleware (`recorder.ts`) and the
session API's handlers (`api.ts`). The Next.js routes are thin wrappers around them. The recorder is AG-UI
`Middleware` attached with `agent.use()` to the `spe` `HttpAgent` in the CopilotKit route. The page
(`app/page.tsx` plus `app/sidebar.tsx`) only reads sessions and changes metadata. On the Ansible side,
`run_archive` gains an `agui` export (barrier, copy, restart) and `files/write_agui_run.py`.

**Tech stack:** Next.js 16.4.1, CopilotKit 1.79.0 (v2), `@ag-ui/client` 1.0.2, rxjs 7.8.1, Node 24
(`node --test`, type stripping), TypeScript 6.0.3, Python ≥ 3.12 standard library (pytest for tests),
Playwright (the `browser-playwright` skill), Ansible from the system package, Docker Compose on the VM.

## Global Constraints

Every task's requirements include these.

- **Tests, before every commit**, the suites a slice touches:
  `(cd platform/agui/copilotkit-chat && npm ci && npm test && npm run build)` (build = type check),
  `uv run --with pytest pytest platform/dev/tests -q`,
  `(cd platform/agui/pydantic-ai-agent && uv run --group dev pytest -q)` when `fake_agent.py` changes.
- **No new runtime dependencies** (spec §6). `rxjs` is already installed (7.8.1, a dependency of
  `@ag-ui/client`); slice 1 lists it in `package.json` at exactly that version, because `lib/recorder.ts`
  imports it directly. No test framework: `node --test` with Node 24's type stripping.
- **`npm test` is `node --test 'lib/*.test.ts'`**: `node --test lib/` fails on Node 24.
- **TypeScript that type stripping accepts:** in `lib/`, relative imports carry the `.ts` extension
  (`tsconfig.json` gets `"allowImportingTsExtensions": true`), types are imported with `import type`, and no
  enums, namespaces or constructor parameter properties.
- **Session ids are validated before any path is built** (decision 2). Only `lib/sessions.ts` touches
  the filesystem.
- **Nothing from request headers or the runtime configuration reaches a session file** (decision 13). Message
  content is stored unchanged.
- **All session data is rendered as React text**, never HTML (decision 14). No `dangerouslySetInnerHTML`.
- **Error bodies are `{"error": "<generic message>"}`**; details go to `console.error`, without message content.
- **No model calls without the user's OK.** Everything runs against `platform/dev/fake_agent.py`, except the one
  paid check of slice 3 (about $0.01, `claude-haiku-5-5` on the dev VM).
- **The dev VM's instance** is redeployed in place with `create.yml` from the main checkout and
  `-e spe_agui_source_dir=<worktree>` (`AGENTS.md`, *Worktrees and deploying*). No cloud instance is
  created or destroyed. `destroy.yml` is not run, except in slice 3, task 4, step 7, and only if the user agrees
  at that step.
- **Upstream-clean:** code, READMEs and Ansible comments name nothing fork-only (spec, *Out of scope*).
- **Rulings:** a departure from this plan is recorded in the slice's handoff, as *decision, why, cost if wrong*.

## Shared interfaces

Later slices use these names exactly. Paths are relative to `platform/agui/copilotkit-chat/`.

**`lib/sessions.ts`** (slice 1, task 2)

```ts
export type RunStatus = "completed" | "failed" | "cancelled";
export type RunEntry = { run_id: string; started_at: string; ended_at: string; status: RunStatus };
export type SessionRecord = {
  version: 1; id: string; title: string; title_source: "auto" | "user"; tags: string[];
  pinned: boolean; hidden: boolean; created_at: string; updated_at: string; deleted_at: string | null;
  messages: Message[]; runs: RunEntry[];               // Message: `import type { Message } from "@ag-ui/client"`
};
export type SessionMeta = Pick<SessionRecord, "id" | "title" | "tags" | "pinned" | "hidden" | "created_at" | "updated_at">;
export type SessionView = Omit<SessionRecord, "deleted_at" | "runs">;          // GET /api/sessions/{id}
export type MetaPatch = Partial<Pick<SessionRecord, "title" | "tags" | "pinned" | "hidden">>;
export class ValidationError extends Error {}
export function isSessionId(value: unknown): value is string;  // canonical lower-case UUID v4
export function normaliseTags(value: unknown): string[];        // throws ValidationError
export function parsePatch(body: unknown): MetaPatch;           // throws ValidationError
export function autoTitle(messages: Message[]): string;         // ≤ 60 code points, "Untitled" if no text
export type RunHandle = { cancel: () => void };
export type Shared = { queue: Map<string, Promise<unknown>>; running: Map<string, RunHandle>; closing: boolean };
export function shared(): Shared;  // globalThis[Symbol.for("spe.sessions.queue")], one per process
export function withSession<T>(id: string, fn: () => Promise<T>): Promise<T>;  // per-id serialisation
export class SessionStore {
  constructor(dir: string);
  read(id: string): Promise<SessionRecord | null>;            // null: no file (deleted ones are returned)
  write(record: SessionRecord): Promise<void>;                // atomic: tmp file + rename; caller holds the queue
  list(): Promise<SessionMeta[]>;                             // not deleted, newest updated_at first, ≤ 1000
  patch(id: string, patch: MetaPatch, now: Date): Promise<SessionMeta | null>;   // null: missing or deleted
  softDelete(id: string, now: Date): Promise<boolean>;        // false: missing or already deleted
  recordRun(id: string, messages: Message[], run: RunEntry, now: Date): Promise<void>;  // §2 Finalise
}
export function defaultStore(): SessionStore;  // dir from SPE_SESSIONS_DIR, default "/data/sessions"
```

`patch`, `softDelete` and `recordRun` take the queue themselves (`withSession`); `read` and `list` do not.

**`lib/recorder.ts`** (slice 1, task 3): `export class SessionRecorder extends Middleware` with
`constructor(store: () => SessionStore, now?: () => Date)` and `run(input: RunAgentInput, next: AbstractAgent):
Observable<BaseEvent>`; `export const SAVE_FAILED = "spe.session_save_failed"`. A running session's
`RunHandle.cancel()` ends that run as `cancelled`, emitting `RUN_ERROR` `code: "cancelled"` (slice 2's
shutdown uses it). The save-failed event is a `CUSTOM` event named `SAVE_FAILED` with `value: { session: id }`.
A run leaves `shared().running` when its write is queued (only if its own handle is still there), not after the
write. `SPE_SESSIONS_TEST_SAVE_DELAY_MS` is read inside `recordRun`, under the queue. `cancel()` and an early
unsubscribe also abort the request to the agent, so a cancelled run does not keep running there: the `next` a
middleware gets is a wrapper without `abortRun()`, so the recorder has a `readonly fetch` (signature in slice 1), and the
route builds the `HttpAgent` with `fetch: recorder.fetch`. `export const REFUSAL_MESSAGES: readonly string[]`
holds the five refusal messages; slice 3's browser code mirrors them and its test compares against this export.

**`lib/test-agent.ts`** (slice 1, test-only, not in the image): `startTestAgent(delayMs?: number):
Promise<TestAgent>`, `TestAgent = { url: string; requests: { headers, body, closed }[]; close(): Promise<void> }` (`closed`: the
client closed the connection), an
in-test AG-UI SSE server.

**`lib/api.ts`** (slice 1, task 4): `listSessions(store)`, `getSession(store, id)`,
`patchSession(store, id, request)`, `deleteSession(store, id)`, each `Promise<Response>`.

**Slice 2's browser-side names** (slice 2, tasks 1–2; signatures in
[slice-2-sidebar.md](slice-2-sidebar.md), *Additions to the README's shared interfaces*): `lib/session-id.ts`
(`isSessionId` moves here, without Node imports; `lib/sessions.ts` re-exports it), `lib/session-url.ts`
(`sessionFromSearch`, `searchWith`), `lib/client.ts` (`Fetch`, `ApiError`, `fetchSessions`, `fetchSession`,
`updateSession`, `removeSession`, `listOrder`, `renamePatch`, `withTag`, `withoutTag`), and `app/sidebar.tsx`
`Sidebar({ sessions, knownTags, activeId, onNew, onOpen, onChanged, onDeleted, onError })` with the CSS classes
`.spe-sidebar`, `.spe-row`, `.spe-row-active`, `.spe-row-open`, `.spe-row-title`, `.spe-chip`, `.spe-pin`,
`.spe-row-menu`, `.spe-menu`, `.spe-error`.

**`lib/shutdown.ts`** (slice 2, task 3): `export function installShutdown(): void`, called from
`instrumentation.ts`'s `register()`; on `SIGTERM` sets `shared().closing`, cancels every running handle, waits
until `running` is empty and then until `queue` is, then exits. Also `DRAIN_TIMEOUT_MS = 25_000`, `drain(state, timeoutMs, pollMs?)` and
`shutdown(state, exit, timeoutMs?)`. The image sets `NEXT_MANUAL_SIG_HANDLE=true`, since Next.js's own `SIGTERM`
handler exits before the drain (proposed clarification 2).

**Files on the instance:** volume `chat-sessions` (compose project `spe-frontend`, so
`spe-frontend_chat-sessions`) at `/data` in `chat-ui`; sessions at `/data/sessions/<id>.json`. Archive bundle:
`/tmp/spe-agui-export.tar.gz` on the VM → `{{ spe_output_dir }}/archive-bundle-agui.tar.gz`, holding
`sessions/` and, if present, `agent-runs.jsonl`.

**`lib/reconcile.ts`** (slice 3, task 2): `SAVE_FAILED_EVENT` (equal to slice 1's `SAVE_FAILED`) and
`isSaveFailed(event, id)`, so the page shows the save-failed error as soon as the event arrives. The e2e
(`platform/dev/e2e/sessions.py`) runs, in order, slice 2's `check_list`, `check_menu`, `check_close_tab` (a tab
closed mid-run still records `completed`) and slice 3's checks, among them `check_save_failed`.

## File structure

| Path | Slice | What |
|---|---|---|
| `copilotkit-chat/lib/sessions.ts`, `lib/sessions.test.ts` | 1 | store, validation, queue |
| `copilotkit-chat/lib/recorder.ts`, `lib/recorder.test.ts`, `lib/clone.test.ts`, `lib/test-agent.ts` | 1 | recorder middleware; the clone gate |
| `copilotkit-chat/lib/api.ts`, `lib/api.test.ts`, `app/api/sessions/route.ts`, `app/api/sessions/[id]/route.ts` | 1 | session API |
| `copilotkit-chat/app/api/copilotkit/[[...slug]]/route.ts` | 1 | `agent.use(recorder)` on an `HttpAgent` built with `fetch: recorder.fetch` |
| `copilotkit-chat/package.json`, `tsconfig.json`, `Dockerfile`, `.dockerignore`, `README.md` | 1 | `npm test`, `rxjs`, `lib/` in the image, `/data/sessions` |
| `copilotkit-chat/scripts/check-built-server.mjs` | 1 | the built-server checks (decision 3, the clone) |
| `ansible/roles/agui/templates/docker-compose.yml.j2` | 1 | volume `chat-sessions` at `/data` |
| `platform/dev/fake_agent.py` | 1 | the slow run ("slow": about 10 s) |
| `copilotkit-chat/app/page.tsx`, `app/sidebar.tsx`, `app/globals.css` | 2, 3 | sidebar, URL, row menu; then search, tags, groups, header |
| `copilotkit-chat/lib/session-id.ts`, `lib/session-url.ts`, `lib/client.ts` (+ tests) | 2 | browser side: id check, URL, session API client |
| `copilotkit-chat/instrumentation.ts`, `lib/shutdown.ts`, `scripts/check-shutdown.mjs` | 2 | the `SIGTERM` drain (§4, *Barrier*) |
| `ansible/roles/run_archive/tasks/export.yml`, `tasks/write.yml`, `files/write_agui_run.py`, `files/write_run.py`, `ansible/playbooks/archive.yml` | 2 | agui export and writer; `fence()` |
| `platform/dev/tests/test_write_agui_run.py` | 2 | writer tests |
| `platform/dev/e2e/sessions.py` | 2, 3 | Playwright (Python, the only Playwright on the dev VM) run against `fake_agent.py` |
| `copilotkit-chat/lib/sidebar-view.ts`, `lib/reconcile.ts` (+ tests), `app/session-filters.tsx`, `app/chat-header.tsx`, `app/use-run-reconcile.ts` | 3 | view helpers, reconciliation, filters, header |
| `platform/dev/fake_agent.py` (`--run-log`), `platform/dev/fake-agent.compose.yml` | 3 | the fake agent on the dev VM for the archive checks, no model calls |
| `ansible/roles/agui/tasks/checks.yml` | 3 | "Session API answers"; chat-ui hardening (`docker inspect`); key scan over the volume |
| docs (§3 and §4 lists) | 2, 3 | each in the slice that changes the behaviour |
| `docs/superpowers/plans/2026-10-29-agui-chat-sessions/evidence/slice-N/` | 2, 3 | screenshots of the slice's Playwright run; history, never updated after the slice merges |

## PR slices

N = 3. Sequential: slice n+1 starts from `main` after slice n merged. The user merges every PR
(`AGENTS.md`, *Overrides*).

| n/N | Branch | Tasks | Delivers | Est. LOC | Reviewer checks | File | Status |
|---|---|---|---|---|---|---|---|
| 1/3 | `impl/agui-chat-sessions-1-store` | 5 | store, recorder, session API, volume, image, slow fake run; no visible change | ~950 | `npm test`; `node scripts/check-built-server.mjs`; `docker build` | [slice-1-store.md](slice-1-store.md) | merged #9 |
| 2/3 | `impl/agui-chat-sessions-2-sidebar` | 5 | **early output**: sidebar list, open, New chat, URL, row menu; archive export and writer; docs | ~1,070 | Playwright run (three sessions) with screenshots; `archive.yml` run directory; pytest | [slice-2-sidebar.md](slice-2-sidebar.md) | merged #10 |
| 3/3 | `impl/agui-chat-sessions-3-complete` | 6 | search, tag filter, groups, *Show hidden*, header, disabled controls, reconciliation; instance checks; dev-VM archive checks; paid check; action buttons disabled until the page is ready | ~700 | full Playwright run; `verify.yml`; four `archive.yml` runs | [slice-3-complete.md](slice-3-complete.md) | merged #11 |

The early output (spec, *Early output*) is slice 2: it needs slice 1's store and recorder, and nothing that
depends on decisions 9 and 12 comes before it. Its PR body carries the screenshots and the run directory's
`index.md` and one `chats/NN-*.md`, and asks the user to look; slice 3 does not wait for that look.

Slice 2 is about 1,070 code lines, a little over the ~1,000 target, and stays one unit: the early output is
the sidebar *and* an archived run, so splitting the archive off would leave the early output split over two PRs
with the user's look waiting for both. A reviewer looks first at `lib/shutdown.ts` and `tasks/export.yml`.

## Review Focus

Input classes the spec implies but its acceptance checks do not exercise; each line's test is in the named task.

1. **A session file that does not parse** (hand-edited, or from a future `version`): the list skips it and
   logs, `GET` gives the generic 500, nothing crashes the list. Slice 1, task 2.
2. **Leftover `<id>.json.tmp-*` files** after a crash: never listed, never read as sessions. Slice 1, task 2.
3. **Titles cut at 60 characters by code point**: an emoji or other astral character at the boundary is kept
   whole, never half a surrogate pair. Slice 1, task 2.
4. **A `PATCH` body that is not a JSON object** (invalid JSON, an array, `null`, a string): 400, nothing
   changed. Slice 1, task 4.
5. **`?session=` with a malformed or deleted id**: the page starts a new session and drops the parameter, with
   no error bar. Slice 2, task 1.

## Proposed spec clarifications

Each is added by the slice that verifies it, with status `folded`, and §2's text updated in the same commit.

1. **The stop button arrives as `RUN_ERROR` with `code: "abort"`, recorded `cancelled`.** Read in
   `@ag-ui/client` 1.0.2: the runner's `stop` calls `HttpAgent.abortRun()`, which aborts the fetch, and the
   HTTP transform turns the `AbortError` into a `RUN_ERROR` event `{code: "abort"}` instead of ending the
   stream. §2's table gains that row; unsubscription stays `cancelled`. Slice 1, task 1 pins it with a test.
   Added by slice 1 (folded).
2. **Next.js's own `SIGTERM` handler exits before the drain**, so the image sets `NEXT_MANUAL_SIG_HANDLE=true`
   and `instrumentation.ts` installs the only handler. §4 *Export*, step 1 (*Barrier*) gains that. Slice 2, task 3.
   Added by slice 2 (folded).
3. **An absent run log is recognised from `docker compose cp`'s own error** (`Could not find the file`), not by a
   check before the copy. §4 *Export*, step 2 and decision 11's acceptance check are rewritten to match. Slice 2,
   task 4. Added by slice 2 (folded).

## Handoffs

[`handoffs/`](handoffs/): read only the newest (`ls handoffs | tail -1`).
