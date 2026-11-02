# Slice 2/3: the early output — sidebar list, open, New chat, URL, row menu; the SIGTERM drain; the archive export and writer

Delivers the first thing the user looks at: the CopilotKit chat gets a left sidebar of sessions (*New chat*, the
list with pinned rows first, opening a row, `?session=<id>` in the URL, a collapse button) and a row menu (rename,
pin, tags, hide, delete with confirmation). The chat UI drains on `SIGTERM` (every run in progress is saved
`cancelled`), which is the barrier `archive.yml`'s new `agui` export relies on: stop `chat-ui`, then `agent`, copy
the session files and the agent's run log, start both again. `write_agui_run.py` renders that bundle in the Open
WebUI run layout, and `write_run.py`'s `fence()` becomes one backtick longer than any run inside. Every text that
says the AG-UI chat keeps no history or is not archived is rewritten. The slice ends with a Playwright run against
`platform/dev/fake_agent.py` that leaves three sessions (tagged and pinned, hidden, deleted), `archive.yml`'s run
directory for them on the dev VM, and a PR body that asks the user to look at both (spec, *Early output*).

Tasks 6–8 were added on 2026-11-02 (spec clarification 4): the sidebar's menu, rename and tags behave as Open
WebUI's do, the sidebar and chat take Open WebUI's look, and slice 3's tasks follow. They run after task 4 and
before task 5.

Not in this slice (slice 3): title search, the tag filter, date groups, *Show hidden* (until then hidden rows are
left out of the list but stay openable by URL), the chat header with title and tags, disabled controls during a
run, and the list reconciliation after a run (for a save that lands late).

**Implements:** spec [`2026-10-29-agui-chat-sessions-design.md`](../../specs/2026-10-29-agui-chat-sessions-design.md)
§3 (layout, row menu, URL, opening, New chat, refresh after a run and after a change, errors; the stale texts),
§4 (export with its barrier, write, the stale texts), §5 *Untrusted text*, §6 *Archive writer* and *End to end*.
Decisions **9** in part (task 1: list, open, New chat, URL; task 2: row menu; search, filter, groups and *Show
hidden* are slice 3), **11** (task 4: the export; task 5: `archive.yml` on the dev VM after the Playwright run; the
slow-run, fresh-instance and removed-`chat-ui` runs are slice 3), **12** (task 4,
`platform/dev/tests/test_write_agui_run.py`), **14** (task 1 and task 5: a title of `<img src=x onerror=…>` shows as
text; task 4: the fence tests, `write_run.py` too), and **4**'s end-to-end check (task 2, `check_close_tab`: closing
the tab mid-run leaves the whole run on disk, `completed`). Review Focus 5 (task 1).

**Branch:** `impl/agui-chat-sessions-2-sidebar`, from `main` after slice 1 merged. Global constraints, shared
interfaces and Review Focus: [plan README](README.md). Paths below are relative to the repository root; `CHAT` is
`platform/agui/copilotkit-chat`.

**Additions to the README's shared interfaces** (slice 3 uses them; no listed signature changes):

- `lib/session-id.ts`: `export function isSessionId(value: unknown): value is string` moves here (no Node
  imports, so the page can use it); `lib/sessions.ts` re-exports it unchanged.
- `lib/session-url.ts`: `sessionFromSearch(search: string): string | null`, `searchWith(search: string, id: string
  | null): string`.
- `lib/client.ts` (browser side of the session API): `type Fetch = (input: string, init?: RequestInit) =>
  Promise<Response>`, `class ApiError extends Error { status: number }`, `fetchSessions(f?: Fetch):
  Promise<SessionMeta[]>`, `fetchSession(id: string, f?: Fetch): Promise<SessionView | null>` (null on 404),
  `updateSession(id: string, patch: MetaPatch, f?: Fetch): Promise<SessionMeta>`, `removeSession(id: string, f?:
  Fetch): Promise<void>`, `listOrder(list: SessionMeta[]): SessionMeta[]` (hidden out, pinned first, newest
  `updated_at` first; slice 3 replaces it with `lib/sidebar-view.ts`), and (task 2) `renamePatch(input: string,
  current: string): MetaPatch | null`, `withTag(tags: string[], input: string): MetaPatch | null`,
  `withoutTag(tags: string[], tag: string): MetaPatch`.
- `app/sidebar.tsx`: `export function Sidebar(props: { sessions: SessionMeta[]; knownTags: string[]; activeId:
  string | null; onNew(): void; onOpen(id: string): void; onChanged(): void; onDeleted(id: string): void;
  onError(message: string): void })`. CSS classes the e2e script and slice 3 use: `.spe-sidebar`, `.spe-row`,
  `.spe-row-active`, `.spe-row-open`, `.spe-row-title`, `.spe-chip`, `.spe-pin`, `.spe-row-menu`, `.spe-menu`,
  `.spe-error`.
- `lib/shutdown.ts`: besides `installShutdown()`, `DRAIN_TIMEOUT_MS = 25_000`, `drain(state: Shared, timeoutMs:
  number, pollMs?: number): Promise<boolean>`, `shutdown(state: Shared, exit: (code: number) => void, timeoutMs?:
  number): Promise<void>`.
- `platform/dev/e2e/sessions.py` (Python Playwright, ruling 1), with `Run.wait_runs(sid, n, seconds=5) -> dict`,
  `check_list(r) -> dict[str, str]`, `check_menu(r, ids)` and `check_close_tab(r, ids)` (a second, `completed` run
  on the hidden session "Read the dataset"); slice 3 adds its checks as further functions, and its `main()` keeps
  calling all three.
- `scripts/check-shutdown.mjs` (`node scripts/check-shutdown.mjs [--image <tag>]`).
- `run_archive/files/write_agui_run.py <bundle dir> <run dir>`, with `main(argv) -> int`; `write_run.py` gains
  `main(argv)` and an import guard so its `slug`, `fence` and `write` can be imported.

### What was checked before this file was written

Read in the packages installed in the main checkout (`CHAT/node_modules`, CopilotKit 1.79.0, `@ag-ui/client` 1.0.2,
Next.js 16.4.1), and run in `/var/tmp/claude-1000/slice2-scratch/` (not committed):

- **CopilotChat and a changed `threadId`.** With an explicit thread (`<CopilotChat threadId=…>`), CopilotChat's
  thread effect (`@copilotkit/react-core/dist/copilotkit-DQvE96lZ.mjs`, `function CopilotChat`, the effect on
  `resolvedThreadId`) calls `copilotkit.connectAgent({agent})`; `RunHandler.connectAgent`
  (`@copilotkit/core/dist/index.mjs`, around line 3744) treats a thread id different from the last connected one as
  a *fresh restore*: after `await agent.detachActiveRun()` it calls `agent.setMessages([])`, then asks the runtime's
  `/connect` (`runtime/dist/v2/runtime/handlers/handle-connect.mjs` → `runner/in-memory.mjs` `connect()`), which
  replays only the threads this server process ran (`historicRuns`) and nothing after a restart. So messages set
  before an explicit-thread mount are wiped, and a restored session would be empty after a restart. Without an
  explicit thread, CopilotChat sets `agent.threadId` to its thread and makes no connect request; it clears the
  agent's messages only when the thread changes *inside one mounted instance* (`clearDiscardedBaseline`), never on
  first mount. **So the page sets the messages on the agent, then mounts a new CopilotChat with `key={id}` inside
  `<CopilotChatConfigurationProvider agentId="spe" threadId={id} hasExplicitThreadId={false}>`.** `useAgent` hands
  out a provisional agent until the runtime's `/info` has answered (`isReady: false`), and messages set on it are
  lost, so nothing is opened before `isReady`.
- **That page in a browser.** This task's `app/page.tsx` and `app/sidebar.tsx` (task 2's version), built with
  `next build` into a copy of the chat UI whose session routes read a fixture file (no recorder), driven by Python
  Playwright against `fake_agent.py`: `?session=<id>` showed the stored messages and the `run_command` card; the next
  run answered "Turn 2" (the agent received the stored history); *New chat* cleared the chat and the next run
  answered "Turn 1"; clicking the row switched back; the row menu showed Rename, Unpin, Tags, Hide, Delete;
  `?session=not-a-uuid` and an unknown UUID started a new session with the parameter dropped and no `.spe-error`. The
  imports of `../lib/*.ts` from `app/` build with `allowImportingTsExtensions`. Note: Next.js's route announcer is
  also `role="alert"`, so the checks look for `.spe-error`, never `[role=alert]`.
- **Next.js and `SIGTERM`.** `next/dist/server/lib/start-server.js` (used by the standalone `server.js`) registers
  its own `SIGTERM` handler unless `NEXT_MANUAL_SIG_HANDLE` is set: it closes the HTTP server (waiting for open
  responses) and then calls `process.exit(143)`. A run whose browser has gone is detached (the in-memory runner)
  and holds no response open, so Next.js would exit in the middle of its save; a run with a browser attached would
  keep `server.close()` waiting until the run ends by itself, possibly past `stop -t 30`. Hence the image sets
  `NEXT_MANUAL_SIG_HANDLE=true` and `lib/shutdown.ts` alone ends the process. `instrumentation.ts`'s `register()`
  runs at server start (`next-server.js`, `prepareImpl` → `runInstrumentationHookIfAvailable`).
- **`lib/shutdown.ts`** (below, against a stub of `shared()`): `node --test` 6/6 pass. `node --test lib/` (a
  directory argument) fails in Node 24.21 with `MODULE_NOT_FOUND`; plain `node --test` (its default patterns
  include `*.test.ts`) or a glob `node --test 'lib/*.test.ts'` works. Slice 1's `npm test` script must use one of
  those.
- **`lib/session-id.ts`, `lib/session-url.ts`, `lib/client.ts`** (below): `node --test` 7/7, 8/8 with task 2's
  helpers (14/14 together with `lib/shutdown.test.ts`), and `tsc --noEmit` with the chat UI's options plus
  `allowImportingTsExtensions` over `lib/`, `app/page.tsx`, both versions of `app/sidebar.tsx` and
  `instrumentation.ts`: no errors.
- **`write_agui_run.py` and `write_run.py`** (below): `pytest platform/dev/tests/test_write_agui_run.py`: 15
  passed; against the unchanged `write_run.py` 14 of them fail (it runs its whole script on import) and the CLI
  regression test passes. The refactored `write_run.py` renders a sample Open WebUI bundle byte for byte as before
  (`diff -r`, only the run directory's name in the `# Run` heading differs).
- **The export** (below), against a throwaway compose project of two `node:24-slim` containers with the same
  service names and volumes: no run log → bundle with `sessions/` only, play green; a run log → `agent-runs.jsonl`
  in the bundle; `chat-ui` removed → the first task fails and nothing is stopped. Docker Compose 5.5.1 facts it
  relies on: `docker compose cp` copies from a **stopped** container; a missing file fails with `Could not find the
  file … in container` (rc 1); `docker compose stop` of a service **without a container exits 0**, hence the
  explicit `ps -a -q chat-ui` check. Then `write.yml` with that bundle: run directory with `agui-sessions/`,
  `chats/01-….md/.json`, `index.md`, staged files removed.
- Not run here: anything needing slice 1's store and recorder (`check-shutdown.mjs`, `sessions.py`, the image build,
  the dev VM). Those are this slice's own checks.

### Rulings (record them in the slice's handoff as *decision, why, cost if wrong*)

1. **The e2e script is Python Playwright** (`platform/dev/e2e/sessions.py`), not Node Playwright: the dev VM has Python
   Playwright 1.64.1 with its Chromium (the `browser-playwright` skill), and no Node Playwright; adding the npm
   package would be a new dependency and a second browser download. Cost if wrong: one file to port.
2. **Opening a session remounts CopilotChat on a non-explicit thread** (above). Cost if wrong: if a later CopilotKit
   makes the first mount clear messages, opening shows an empty chat; the e2e reload check catches it.
3. **The image sets `NEXT_MANUAL_SIG_HANDLE=true`**; `installShutdown()` warns at start when it is unset (`next
   start`, a hand-run `server.js`). Spec §4 *Export*, step 1 (*Barrier*) gains that (clarification 2, task 3).
4. **An absent run log is recognised by `docker compose cp`'s own error** (`Could not find the file`) rather than a
   check before the copy: the agent is stopped by then, so nothing can be checked inside it, and checking before
   stopping it races with its last write. Spec §4 *Export*, step 2 is rewritten to say so (clarification 3, task 3,
   step 7; task 4 implements it).
5. **`archive.yml` for the early output runs from the worktree**, with the main checkout's instance file and output
   (`-e spe_output_root=<main>/platform/ansible/output`): the new `run_archive` code is only in the worktree, and
   `AGENTS.md`'s `-e spe_agui_source_dir` covers the agent and chat-UI sources only.
6. **Hidden rows are left out of the list until slice 3's *Show hidden***; they stay openable by URL, and `Unhide` is
   in the menu for when they are shown.

---

### Task 1: open, New chat, `?session=`, the list

**Files:** Create: `CHAT/lib/session-id.ts`, `CHAT/lib/session-url.ts`, `CHAT/lib/client.ts`, `CHAT/app/sidebar.tsx`,
`platform/dev/e2e/sessions.py`. Modify: `CHAT/lib/sessions.ts` (re-export), `CHAT/app/page.tsx`,
`CHAT/app/globals.css`. Test: `CHAT/lib/session-url.test.ts`, `CHAT/lib/client.test.ts`,
`platform/dev/e2e/sessions.py` (`check_list`).

**Interfaces:** Consumes: `SessionMeta`, `SessionView`, `MetaPatch` (types only) from `lib/sessions.ts`; `GET
/api/sessions`, `GET /api/sessions/{id}` (slice 1); `useAgent`, `CopilotChatConfigurationProvider`, `CopilotChat`
from `@copilotkit/react-core/v2`. Produces: `isSessionId` in `lib/session-id.ts`, `sessionFromSearch`,
`searchWith`, the `lib/client.ts` calls and `listOrder`, `Sidebar` (signature above).

**Decisions:** 9 (list, open, New chat, URL), 14 (titles as text). Review Focus 5:
`sessionFromSearch` unit test and `check_list`'s loop over a malformed, an unknown and an upper-case id.

- [ ] **Step 1: Confirm the CopilotChat behaviour this task relies on** (installed packages, 2 minutes)

```bash
cd platform/agui/copilotkit-chat && npm ci
D=node_modules/@copilotkit/react-core/dist
grep -n "hasExplicitThreadId) {" $D/copilotkit-*.mjs | head -3          # the non-explicit branch: no connect
grep -n "clearDiscardedBaseline();" $D/copilotkit-*.mjs | head -3       # cleared only when threadChanged && previousThread !== null
grep -n "if (isFreshRestore) {" -A2 node_modules/@copilotkit/core/dist/index.mjs | head -4   # explicit: setMessages([])
```

Expected: each grep prints a line (the code read above). If CopilotKit is no longer 1.79.0 or a grep prints nothing,
stop and re-read `function CopilotChat` before going on; record what changed as a ruling.

- [ ] **Step 2: Move the id check to a browser-safe module**

`CHAT/lib/session-id.ts`:

````ts
// The session id check, shared by the server store and the page.
// No Node imports here: the browser bundle includes this file.
const SESSION_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

export function isSessionId(value: unknown): value is string {
  return typeof value === "string" && SESSION_ID.test(value);
}
````

In `CHAT/lib/sessions.ts`, delete slice 1's `isSessionId` function and its `UUID_V4` constant, and put in their
place an import (the store itself calls `isSessionId` in `file()` and `list()`) and a re-export (`api.ts`,
`recorder.ts` and the tests import it from `./sessions.ts`):

````ts
import { isSessionId } from "./session-id.ts";
export { isSessionId };
````

A bare `export { isSessionId } from "./session-id.ts"` would not do: it binds no local name, so `file()` and
`list()` would fail the type check (TS2304) and throw a `ReferenceError` at run time.

Run: `(cd platform/agui/copilotkit-chat && npm test && npm run build)`. Expected: all of slice 1's tests pass (42/42
in a scratch copy of slice 1 with this change) and the build's type check passes.

- [ ] **Step 3: Write the failing tests for the URL helpers and the API client**

`CHAT/lib/session-url.test.ts`:

````ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { isSessionId } from "./session-id.ts";
import { searchWith, sessionFromSearch } from "./session-url.ts";

const ID = "6f1c0d2e-1a2b-4c3d-8e4f-0a1b2c3d4e5f";

test("isSessionId accepts only canonical lower-case UUID v4", () => {
  assert.equal(isSessionId(ID), true);
  for (const bad of [ID.toUpperCase(), "../x", "a/b", "", null, 42, ID.replace("-4c3d-", "-1c3d-"), `${ID}x`]) {
    assert.equal(isSessionId(bad), false, String(bad));
  }
});

test("sessionFromSearch: a valid id, else null (malformed, missing, repeated junk)", () => {
  assert.equal(sessionFromSearch(`?session=${ID}`), ID);
  assert.equal(sessionFromSearch(`?x=1&session=${ID}`), ID);
  assert.equal(sessionFromSearch("?session=../../etc/passwd"), null);
  assert.equal(sessionFromSearch(`?session=${ID.toUpperCase()}`), null);
  assert.equal(sessionFromSearch(""), null);
});

test("searchWith sets or drops the parameter and keeps the others", () => {
  assert.equal(searchWith("", ID), `?session=${ID}`);
  assert.equal(searchWith("?session=bad&x=1", null), "?x=1");
  assert.equal(searchWith("?session=bad", null), "");
  assert.equal(searchWith(`?x=1&session=${ID}`, ID), `?x=1&session=${ID}`);
});
````

`CHAT/lib/client.test.ts`:

````ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { ApiError, fetchSession, fetchSessions, listOrder, removeSession, updateSession } from "./client.ts";
import type { Fetch } from "./client.ts";
import type { SessionMeta } from "./sessions.ts";

const ID = "6f1c0d2e-1a2b-4c3d-8e4f-0a1b2c3d4e5f";

function fake(status: number, body: unknown, seen: { url?: string; init?: RequestInit } = {}): Fetch {
  return async (url, init) => {
    seen.url = url;
    seen.init = init;
    return status === 204 ? new Response(null, { status }) : Response.json(body, { status });
  };
}

function meta(id: string, updated_at: string, extra: Partial<SessionMeta> = {}): SessionMeta {
  return { id, title: id, tags: [], pinned: false, hidden: false, created_at: updated_at, updated_at, ...extra };
}

test("fetchSession: 404 is null, 500 an ApiError with the generic message", async () => {
  assert.equal(await fetchSession(ID, fake(404, { error: "not found" })), null);
  await assert.rejects(fetchSession(ID, fake(500, { error: "internal error" })),
    (e: unknown) => e instanceof ApiError && e.status === 500 && e.message === "Opening the session failed (500): internal error");
});

test("updateSession sends a JSON PATCH and returns the new metadata", async () => {
  const seen: { url?: string; init?: RequestInit } = {};
  const out = await updateSession(ID, { pinned: true }, fake(200, meta(ID, "t", { pinned: true }), seen));
  assert.equal(seen.url, `/api/sessions/${ID}`);
  assert.equal(seen.init?.method, "PATCH");
  assert.equal(seen.init?.body, '{"pinned":true}');
  assert.equal(out.pinned, true);
  await assert.rejects(updateSession(ID, { tags: ["Bad Tag!"] }, fake(400, { error: "invalid tags" })),
    /Saving the change failed \(400\): invalid tags/);
});

test("removeSession: 204 resolves, 404 rejects; fetchSessions returns the list", async () => {
  await removeSession(ID, fake(204, null));
  await assert.rejects(removeSession(ID, fake(404, { error: "not found" })), ApiError);
  assert.deepEqual(await fetchSessions(fake(200, [meta(ID, "t")])), [meta(ID, "t")]);
});

test("listOrder: hidden out, pinned first, then newest first", () => {
  const rows = listOrder([
    meta("old", "2026-10-29T08:00:00.000Z"),
    meta("hid", "2026-10-29T12:00:00.000Z", { hidden: true }),
    meta("new", "2026-10-29T11:00:00.000Z"),
    meta("pin", "2026-10-28T09:00:00.000Z", { pinned: true }),
  ]);
  assert.deepEqual(rows.map((r) => r.id), ["pin", "new", "old"]);
});
````

- [ ] **Step 4: Run them to see them fail**

Run: `(cd platform/agui/copilotkit-chat && node --test lib/session-url.test.ts lib/client.test.ts)`
Expected: FAIL, `ERR_MODULE_NOT_FOUND` for `./session-url.ts` and `./client.ts`.

- [ ] **Step 5: Write `lib/session-url.ts` and `lib/client.ts`**

`CHAT/lib/session-url.ts`:

````ts
// `?session=<id>`: the open session in the page URL.
import { isSessionId } from "./session-id.ts";

export function sessionFromSearch(search: string): string | null {
  const id = new URLSearchParams(search).get("session");
  return isSessionId(id) ? id : null;
}

// The query string with `session` set to `id`, or removed when `id` is null; other parameters kept.
export function searchWith(search: string, id: string | null): string {
  const params = new URLSearchParams(search);
  if (id === null) params.delete("session");
  else params.set("session", id);
  const text = params.toString();
  return text ? `?${text}` : "";
}
````

`CHAT/lib/client.ts`:

````ts
// The page's calls to the session API (lib/api.ts answers them). Browser-safe: types only from sessions.ts.
import type { MetaPatch, SessionMeta, SessionView } from "./sessions.ts";

export type Fetch = (input: string, init?: RequestInit) => Promise<Response>;

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function failure(response: Response, what: string): Promise<ApiError> {
  let detail = "";
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && typeof (body as { error?: unknown }).error === "string") {
      detail = `: ${(body as { error: string }).error}`;
    }
  } catch {
    // not JSON: the status says enough
  }
  return new ApiError(response.status, `${what} failed (${response.status})${detail}`);
}

const call = (f: Fetch | undefined): Fetch => f ?? ((input, init) => fetch(input, init));

export async function fetchSessions(f?: Fetch): Promise<SessionMeta[]> {
  const response = await call(f)("/api/sessions", { cache: "no-store" });
  if (!response.ok) throw await failure(response, "Loading the sessions");
  return (await response.json()) as SessionMeta[];
}

// null: the session does not exist (or was deleted).
export async function fetchSession(id: string, f?: Fetch): Promise<SessionView | null> {
  const response = await call(f)(`/api/sessions/${encodeURIComponent(id)}`, { cache: "no-store" });
  if (response.status === 404) return null;
  if (!response.ok) throw await failure(response, "Opening the session");
  return (await response.json()) as SessionView;
}

export async function updateSession(id: string, patch: MetaPatch, f?: Fetch): Promise<SessionMeta> {
  const response = await call(f)(`/api/sessions/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!response.ok) throw await failure(response, "Saving the change");
  return (await response.json()) as SessionMeta;
}

export async function removeSession(id: string, f?: Fetch): Promise<void> {
  const response = await call(f)(`/api/sessions/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (!response.ok) throw await failure(response, "Deleting the session");
}

// The list as the sidebar shows it: hidden sessions left out, pinned first, then newest updated_at.
export function listOrder(list: SessionMeta[]): SessionMeta[] {
  return list
    .filter((s) => !s.hidden)
    .sort((a, b) => Number(b.pinned) - Number(a.pinned) || b.updated_at.localeCompare(a.updated_at));
}
````

- [ ] **Step 6: Run them to see them pass**

Run: `(cd platform/agui/copilotkit-chat && node --test lib/session-url.test.ts lib/client.test.ts)`
Expected: PASS, 7 tests.

- [ ] **Step 7: Write the failing browser check** `platform/dev/e2e/sessions.py`

````python
#!/usr/bin/env python3
"""Drive the chat UI's session sidebar in a real browser, against the scripted agent (no LLM).

    python3 platform/dev/e2e/sessions.py [--shots DIR] [--sessions DIR]

Run `npm ci && npm run build` in platform/agui/copilotkit-chat first. The script starts
platform/dev/fake_agent.py (with uv, in platform/agui/pydantic-ai-agent) and the standalone chat UI
with its own sessions directory, walks the sidebar (list, open, New chat, ?session=) and
checks the session files after each step. Needs Python Playwright with Chromium (`pip install playwright` and
`playwright install chromium`). Exits nonzero on the first failed check.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "platform" / "agui" / "copilotkit-chat"
AGENT_DIR = ROOT / "platform" / "agui" / "pydantic-ai-agent"
KEY = "e2e-sessions-key"
AGENT_PORT = 18108
UI_PORT = 3108
BASE = f"http://127.0.0.1:{UI_PORT}"
XSS = '<img src=x onerror="window.__speXss=1">'


def wait_http(url: str, what: str, seconds: float = 60) -> None:
    until = time.time() + seconds
    while time.time() < until:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except Exception:
            time.sleep(0.25)
    sys.exit(f"FAIL: {what} did not come up at {url}")


class Run:
    def __init__(self, page: Page, sessions: Path, shots: Path | None):
        self.page, self.sessions, self.shots, self.n = page, sessions, shots, 0

    def shot(self, name: str) -> None:
        if self.shots:
            self.n += 1
            self.page.screenshot(path=str(self.shots / f"{self.n:02d}-{name}.png"), full_page=True)

    def ok(self, what: str) -> None:
        print(f"ok - {what}", flush=True)

    def files(self) -> dict[str, dict]:
        return {p.stem: json.loads(p.read_text()) for p in self.sessions.glob("*.json")}

    def wait_runs(self, sid: str, n: int, seconds: float = 5) -> dict:
        """The session's record once it has n runs: the recorder writes after the answer is shown."""
        until = time.time() + seconds
        while True:
            path = self.sessions / f"{sid}.json"
            rec = json.loads(path.read_text()) if path.exists() else {"runs": []}
            if len(rec["runs"]) >= n or time.time() > until:
                assert len(rec["runs"]) == n, (sid, n, rec["runs"])
                return rec
            time.sleep(0.2)

    def url_session(self) -> str | None:
        from urllib.parse import parse_qs, urlparse
        return (parse_qs(urlparse(self.page.url).query).get("session") or [None])[0]

    def rows(self):
        return self.page.locator(".spe-sidebar .spe-row")

    def row(self, title: str):
        return self.rows().filter(has=self.page.locator(".spe-row-title", has_text=title))

    def send(self, text: str, turn: int) -> None:
        box = self.page.get_by_test_id("copilot-chat-textarea")
        box.fill(text)
        box.press("Enter")
        expect(self.page.get_by_text(f"Turn {turn}: the command ran.")).to_be_visible(timeout=20_000)

    def menu(self, title: str, item: str) -> None:
        self.row(title).locator(".spe-row-menu").click()
        self.page.get_by_role("menuitem", name=item).click()


def check_list(r: Run) -> dict[str, str]:
    page = r.page
    page.goto(BASE + "/")
    expect(page.get_by_role("button", name="New chat")).to_be_visible()
    assert r.url_session() is None, page.url
    r.ok("first load: no session in the URL, New chat shown")

    r.send("List the home directory", 1)
    expect(r.row("List the home directory")).to_have_count(1, timeout=5_000)
    first = r.url_session()
    assert first and first in r.files(), (first, list(r.files()))
    rec = r.files()[first]
    assert [x["status"] for x in rec["runs"]] == ["completed"] and rec["title"] == "List the home directory"
    r.ok("first run: the row appears, the URL names the session, the file has one completed run")

    page.reload()
    expect(page.get_by_text("Turn 1: the command ran.")).to_be_visible(timeout=10_000)
    expect(page.locator(".spe-tool .spe-tool-name", has_text="run_command")).to_have_count(1)
    expect(r.row("List the home directory")).to_have_class("spe-row spe-row-active")
    r.ok("reload reopens the session with its tool card")

    page.get_by_role("button", name="New chat").click()
    expect(page.get_by_text("Turn 1: the command ran.")).to_have_count(0)
    assert r.url_session() is None, page.url
    r.send("Read the dataset", 1)
    expect(r.row("Read the dataset")).to_have_count(1, timeout=5_000)
    second = r.url_session()
    assert second and second != first
    r.ok("New chat: empty history, a second session after its first run")

    page.get_by_role("button", name="New chat").click()
    r.send(XSS, 1)
    expect(r.rows()).to_have_count(3, timeout=5_000)
    third = r.url_session()
    assert third and r.files()[third]["title"] == XSS
    expect(r.row("<img src=x")).to_have_count(1)
    assert page.evaluate("window.__speXss") is None
    r.ok("a title of an HTML tag shows as literal text and runs nothing")
    r.shot("three-sessions")

    r.row("List the home directory").locator(".spe-row-open").click()
    expect(page.get_by_text("Turn 1: the command ran.")).to_be_visible(timeout=10_000)
    assert r.url_session() == first
    r.send("And the hidden files?", 2)
    assert [x["status"] for x in r.wait_runs(first, 2)["runs"]] == ["completed", "completed"]
    r.ok("opening a row restores its history, and a run continues it")

    for bad in ("not-a-uuid", str(uuid.uuid4()), first.upper()):
        page.goto(f"{BASE}/?session={bad}")
        expect(page.get_by_role("button", name="New chat")).to_be_visible()
        expect(page.get_by_test_id("copilot-chat-textarea")).to_be_visible(timeout=10_000)
        expect(page.locator(".spe-error")).to_have_count(0)
        assert r.url_session() is None, page.url
    r.ok("?session= malformed, unknown or upper-case: new session, parameter dropped, no error bar")
    return {"first": first, "second": second, "third": third}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shots", type=Path, help="write numbered screenshots here")
    ap.add_argument("--sessions", type=Path, help="sessions directory to use and keep (default: a temporary one)")
    args = ap.parse_args()
    standalone = APP / ".next" / "standalone"
    if not (standalone / "server.js").exists():
        sys.exit("FAIL: run `npm ci && npm run build` in platform/agui/copilotkit-chat first")
    shutil.copytree(APP / ".next" / "static", standalone / ".next" / "static", dirs_exist_ok=True)
    data = args.sessions or Path(tempfile.mkdtemp(prefix="spe-e2e-")) / "sessions"
    data.mkdir(parents=True, exist_ok=True)
    if args.shots:
        args.shots.mkdir(parents=True, exist_ok=True)
    procs = [subprocess.Popen(["uv", "run", "--group", "dev", "python", "../../dev/fake_agent.py",
                               "--port", str(AGENT_PORT), "--key", KEY], cwd=AGENT_DIR)]
    try:
        wait_http(f"http://127.0.0.1:{AGENT_PORT}/healthz", "the fake agent")
        env = {**os.environ, "AGENT_URL": f"http://127.0.0.1:{AGENT_PORT}/agent", "AGENT_API_KEY": KEY,
               "PORT": str(UI_PORT), "HOSTNAME": "127.0.0.1", "SPE_SESSIONS_DIR": str(data),
               "NEXT_MANUAL_SIG_HANDLE": "true"}
        procs.append(subprocess.Popen(["node", "server.js"], cwd=standalone, env=env))
        wait_http(BASE + "/api/sessions", "the chat UI")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            r = Run(page, data, args.shots)
            check_list(r)
            browser.close()
        print(f"sessions: {data}")
    finally:
        for proc in reversed(procs):
            proc.terminate()
            proc.wait(timeout=35)


if __name__ == "__main__":
    main()
````

- [ ] **Step 8: Run it to see it fail**

```bash
(cd platform/agui/copilotkit-chat && npm run build)
python3 platform/dev/e2e/sessions.py
```

Expected: FAIL at the first check, a Playwright timeout waiting for `get_by_role("button", name="New chat")` (the
page has no sidebar yet). The script stops both servers on the way out (`finally`).

- [ ] **Step 9: Write the sidebar list** `CHAT/app/sidebar.tsx`

````tsx
"use client";
// The sessions sidebar: New chat, the list (pinned first, then newest) and each row's menu.
// Titles and tags are model or participant text: rendered as React text only, never as HTML.
import { useState } from "react";
import type { SessionMeta } from "../lib/sessions.ts";

type SidebarProps = {
  sessions: SessionMeta[];
  knownTags: string[];
  activeId: string | null;
  onNew: () => void;
  onOpen: (id: string) => void;
  onChanged: () => void;
  onDeleted: (id: string) => void;
  onError: (message: string) => void;
};

export function Sidebar({ sessions, activeId, onNew, onOpen }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false);
  if (collapsed) {
    return (
      <nav className="spe-sidebar spe-sidebar-collapsed" aria-label="Sessions">
        <button type="button" className="spe-collapse" aria-label="Show sessions" onClick={() => setCollapsed(false)}>›</button>
      </nav>
    );
  }
  return (
    <nav className="spe-sidebar" aria-label="Sessions">
      <div className="spe-sidebar-top">
        <button type="button" className="spe-new" onClick={onNew}>New chat</button>
        <button type="button" className="spe-collapse" aria-label="Hide sessions" onClick={() => setCollapsed(true)}>‹</button>
      </div>
      <ul className="spe-list">
        {sessions.map((s) => (
          <li key={s.id} className={s.id === activeId ? "spe-row spe-row-active" : "spe-row"}>
            <button type="button" className="spe-row-open" onClick={() => onOpen(s.id)}
              aria-current={s.id === activeId ? "page" : undefined}>
              <span className="spe-row-title">
                {s.pinned && <span className="spe-pin" aria-label="pinned">📌 </span>}
                {s.title}
              </span>
              {s.tags.length > 0 && (
                <span className="spe-row-tags">
                  {s.tags.map((t) => <span key={t} className="spe-chip">{t}</span>)}
                </span>
              )}
            </button>
          </li>
        ))}
      </ul>
      {sessions.length === 0 && <p className="spe-empty">No sessions yet.</p>}
      <p className="spe-note">Deleted sessions are kept in the run archive.</p>
    </nav>
  );
}
````

- [ ] **Step 10: Rewrite the page** `CHAT/app/page.tsx` (the tool card code is unchanged; the header loses "a reload
  starts a new conversation", which is no longer true)

````tsx
"use client";
// Chat with agent `spe`, and a sidebar of sessions. Each tool call is a collapsible card: name,
// status, arguments and the first lines of the result. Everything is rendered as text, never HTML.
// Sessions are recorded on the server (lib/recorder.ts); this page only reads them and changes
// their metadata. The open session is in the URL (`?session=<id>`), so a reload reopens it.
import type { Message } from "@ag-ui/client";
import {
  CopilotChat,
  CopilotChatConfigurationProvider,
  CopilotKitProvider,
  useAgent,
  useDefaultRenderTool,
} from "@copilotkit/react-core/v2";
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchSession, fetchSessions, listOrder } from "../lib/client.ts";
import { searchWith, sessionFromSearch } from "../lib/session-url.ts";
import type { SessionMeta } from "../lib/sessions.ts";
import { Sidebar } from "./sidebar";

const MAX_RESULT_LINES = 40;
const MAX_RESULT_CHARS = 4000;

type ToolProps = {
  name: string;
  parameters: unknown;
  status: "inProgress" | "executing" | "complete";
  result: string | undefined;
};

function preview(result: string): string {
  let text = result;
  try {
    text = JSON.stringify(JSON.parse(result), null, 2);
  } catch {
    // not JSON: show as is
  }
  const lines = text.split("\n");
  let shown = lines.slice(0, MAX_RESULT_LINES).join("\n");
  if (shown.length > MAX_RESULT_CHARS) shown = shown.slice(0, MAX_RESULT_CHARS);
  return shown.length < text.length ? `${shown}\n… (${text.length - shown.length} more characters)` : shown;
}

function brief(name: string, parameters: unknown): string {
  if (parameters && typeof parameters === "object") {
    const p = parameters as Record<string, unknown>;
    for (const key of ["command", "path", "pattern", "query", "process_id"]) {
      if (typeof p[key] === "string" || typeof p[key] === "number") return String(p[key]);
    }
  }
  return "";
}

const STATUS: Record<ToolProps["status"], string> = {
  inProgress: "preparing…",
  executing: "running…",
  complete: "done",
};

function ToolCard({ name, parameters, status, result }: ToolProps) {
  return (
    <details className="spe-tool">
      <summary>
        <span className="spe-tool-name">{name}</span>
        <span className="spe-tool-brief">{brief(name, parameters)}</span>
        <span className="spe-tool-status">{STATUS[status]}</span>
      </summary>
      <div className="spe-tool-label">arguments</div>
      <pre>{JSON.stringify(parameters ?? {}, null, 2)}</pre>
      {result !== undefined && (
        <>
          <div className="spe-tool-label">result</div>
          <pre>{preview(result)}</pre>
        </>
      )}
    </details>
  );
}

function messageOf(error: unknown): string {
  return error instanceof Error && error.message ? error.message : "The request failed.";
}

// Puts `id` into the URL (or drops the parameter), without a navigation or a history entry.
function showInUrl(id: string | null): void {
  const { pathname, search, hash } = window.location;
  window.history.replaceState(null, "", `${pathname}${searchWith(search, id)}${hash}`);
}

function Chat() {
  const [error, setError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const activeRef = useRef<string | null>(null);
  const { agent, isReady } = useAgent({ agentId: "spe" });
  useDefaultRenderTool({ render: (props) => <ToolCard {...props} /> });

  // The history goes onto the agent first, then CopilotChat remounts on the new thread
  // (key={id}): a freshly mounted chat on a non-explicit thread keeps the agent's messages,
  // and makes no connect request that would clear them (README, Sessions).
  const select = useCallback((id: string, messages: Message[]) => {
    agent.setMessages(messages);
    activeRef.current = id;
    setActive(id);
  }, [agent]);

  const refresh = useCallback(async (): Promise<SessionMeta[] | null> => {
    try {
      const list = await fetchSessions();
      setSessions(list);
      return list;
    } catch (e) {
      setError(messageOf(e));
      return null;
    }
  }, []);

  // New chat: a fresh thread id and an empty history; it joins the list once its first run is recorded.
  const startNew = useCallback(() => {
    select(crypto.randomUUID(), []);
    showInUrl(null);
  }, [select]);

  const open = useCallback(async (id: string) => {
    try {
      const session = await fetchSession(id);
      if (!session) {
        // Deleted, or never recorded: a new session, without an error bar.
        startNew();
        void refresh();
        return;
      }
      select(id, session.messages);
      showInUrl(id);
    } catch (e) {
      setError(messageOf(e));
      if (activeRef.current === null) startNew();
    }
  }, [refresh, select, startNew]);

  // First load, once the runtime's agent is there (messages set on the provisional one are lost).
  useEffect(() => {
    if (!isReady || activeRef.current !== null) return;
    void refresh();
    const id = sessionFromSearch(window.location.search);
    if (id) void open(id);
    else startNew(); // no parameter, or a malformed one: dropped
  }, [isReady, open, refresh, startNew]);

  // After each run (finished, failed or stopped) the list again; once the open session is in
  // it (its first run recorded), the URL names it.
  useEffect(() => {
    if (!isReady) return;
    const ended = () => {
      void refresh().then((list) => {
        const id = activeRef.current;
        if (list && id && list.some((s) => s.id === id)) showInUrl(id);
      });
    };
    const subscription = agent.subscribe({ onRunFinalized: ended, onRunFailed: ended });
    return () => subscription.unsubscribe();
  }, [agent, isReady, refresh]);

  const onDeleted = useCallback((id: string) => {
    if (id === activeRef.current) startNew();
    void refresh();
  }, [refresh, startNew]);

  return (
    <div className="spe-layout">
      <Sidebar
        sessions={listOrder(sessions)}
        knownTags={[...new Set(sessions.flatMap((s) => s.tags))].sort()}
        activeId={active}
        onNew={startNew}
        onOpen={(id) => void open(id)}
        onChanged={() => void refresh()}
        onDeleted={onDeleted}
        onError={setError}
      />
      <div className="spe-page">
        <div className="spe-header">SPE agent — every tool call is shown; your sessions are in the sidebar.</div>
        {error && (
          <div className="spe-error" role="alert">
            {error}
            <button type="button" onClick={() => setError(null)}>dismiss</button>
          </div>
        )}
        {active === null ? (
          <div className="spe-loading">Loading…</div>
        ) : (
          <CopilotChatConfigurationProvider agentId="spe" threadId={active} hasExplicitThreadId={false}>
            <CopilotChat
              key={active}
              agentId="spe"
              className="spe-chat"
              onError={(event) => {
                // The prop's type also admits a DOM error event; only CopilotKit's carries `error`.
                if ("error" in event && event.error instanceof Error) setError(event.error.message || "The agent run failed.");
              }}
            />
          </CopilotChatConfigurationProvider>
        )}
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <CopilotKitProvider runtimeUrl="/api/copilotkit" agentId="spe" showDevConsole={false}>
      <Chat />
    </CopilotKitProvider>
  );
}
````

`CHAT/app/globals.css`, whole file (the existing rules kept, `.spe-page` now a column beside the sidebar):

````css
html, body { height: 100%; margin: 0; }
body { font-family: system-ui, sans-serif; }
.spe-layout { display: flex; height: 100vh; }
.spe-page { display: flex; flex-direction: column; flex: 1; min-width: 0; height: 100vh; }
.spe-header { padding: 8px 16px; border-bottom: 1px solid #ddd; font-size: 14px; }
.spe-chat { flex: 1; min-height: 0; }
.spe-loading { padding: 16px; color: #555; font-size: 14px; }
.spe-error { padding: 8px 16px; background: #fdecea; color: #611a15; border-bottom: 1px solid #f5c6cb;
  font-size: 14px; white-space: pre-wrap; overflow-wrap: anywhere; }
.spe-error button { margin-left: 12px; }
.spe-sidebar { width: 260px; flex: none; display: flex; flex-direction: column; gap: 8px; padding: 8px;
  border-right: 1px solid #ddd; background: #fafafa; overflow-y: auto; font-size: 14px; box-sizing: border-box; }
.spe-sidebar-collapsed { width: auto; }
.spe-sidebar-top { display: flex; gap: 4px; }
.spe-new { flex: 1; padding: 6px 10px; font-weight: 600; cursor: pointer; }
.spe-collapse { padding: 4px 8px; cursor: pointer; }
.spe-list { list-style: none; margin: 0; padding: 0; flex: 1; }
.spe-row { display: flex; flex-wrap: wrap; align-items: flex-start; border-radius: 6px; }
.spe-row:hover { background: #f0f0f0; }
.spe-row-active, .spe-row-active:hover { background: #e3ebfb; }
.spe-row-open { flex: 1; min-width: 0; text-align: left; background: none; border: 0; padding: 6px;
  cursor: pointer; font: inherit; color: inherit; }
.spe-row-title { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.spe-row-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 3px; }
.spe-chip { font-size: 11px; padding: 0 6px; border-radius: 8px; background: #e2e2e2; white-space: nowrap; }
.spe-chip button { border: 0; background: none; padding: 0 0 0 4px; cursor: pointer; font-size: 11px; }
.spe-row-menu { background: none; border: 0; cursor: pointer; padding: 6px 8px; font-size: 16px; line-height: 1; }
.spe-menu { flex-basis: 100%; display: flex; flex-direction: column; gap: 4px; margin: 0 6px 6px; padding: 6px;
  border: 1px solid #ccc; border-radius: 6px; background: #fff; }
.spe-menu > button { text-align: left; background: none; border: 0; padding: 4px 6px; cursor: pointer; font: inherit; }
.spe-menu > button:hover { background: #f0f0f0; }
.spe-menu p { margin: 0 0 4px; font-size: 13px; }
.spe-menu input { font: inherit; padding: 3px 6px; }
.spe-rename { flex: 1; min-width: 0; margin: 4px; font: inherit; padding: 3px 6px; }
.spe-empty, .spe-note { color: #555; font-size: 12px; margin: 0; }
.spe-tool { margin: 6px 0; border: 1px solid #ccc; border-radius: 6px; font-size: 13px; max-width: 100%; }
.spe-tool > summary { cursor: pointer; padding: 6px 10px; display: flex; gap: 8px; align-items: baseline; }
.spe-tool-name { font-weight: 600; font-family: ui-monospace, monospace; }
.spe-tool-status { font-size: 12px; color: #555; }
.spe-tool-brief { font-family: ui-monospace, monospace; color: #333; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; min-width: 0; flex: 1; }
.spe-tool pre { margin: 0; padding: 6px 10px; background: #f6f6f6; border-top: 1px solid #ddd;
  white-space: pre-wrap; overflow-wrap: anywhere; max-height: 320px; overflow: auto; }
.spe-tool-label { padding: 4px 10px 0; font-size: 12px; color: #555; border-top: 1px solid #ddd; }
````

- [ ] **Step 11: Run every check**

```bash
(cd platform/agui/copilotkit-chat && npm test && npm run build)
python3 platform/dev/e2e/sessions.py
```

Expected: `npm test` all pass; the build passes (type check); the script prints the seven `ok - …` lines of
`check_list` and `sessions: /tmp/spe-e2e-…/sessions`, exit 0. If the reload check fails with the stored answer
missing, ruling 2 no longer holds: stop and record it.

- [ ] **Step 12: Commit**

```bash
git add platform/agui/copilotkit-chat/lib/session-id.ts platform/agui/copilotkit-chat/lib/sessions.ts \
  platform/agui/copilotkit-chat/lib/session-url.ts platform/agui/copilotkit-chat/lib/session-url.test.ts \
  platform/agui/copilotkit-chat/lib/client.ts platform/agui/copilotkit-chat/lib/client.test.ts \
  platform/agui/copilotkit-chat/app/sidebar.tsx platform/agui/copilotkit-chat/app/page.tsx \
  platform/agui/copilotkit-chat/app/globals.css platform/dev/e2e/sessions.py
git commit -s -m "Chat UI: session sidebar with open, New chat and ?session=" \
  -m "The page sets the stored messages on the agent and remounts CopilotChat on a non-explicit thread: an explicit threadId makes CopilotChat connect, which clears the messages on a new thread."
```

### Task 2: the row menu

**Files:** Modify: `CHAT/app/sidebar.tsx` (whole file below), `CHAT/lib/client.ts` (append),
`platform/dev/e2e/sessions.py` (add `check_menu`, `check_close_tab`). Test: `CHAT/lib/client.test.ts` (append),
`check_menu`, `check_close_tab`.

**Interfaces:** Consumes: `updateSession`, `removeSession` (task 1); `PATCH`/`DELETE /api/sessions/{id}` (slice 1:
400 with `{"error": …}` for an invalid tag, 404 for a missing one). Produces: `renamePatch`, `withTag`,
`withoutTag`; the menu's accessible names (`Menu for <title>`, menu items `Rename`, `Pin`/`Unpin`, `Tags`,
`Hide`/`Unhide`, `Delete`; inputs `Session title`, `Add a tag`; buttons `Remove tag <t>`; the confirmation an
`alertdialog` named `Delete session`).

**Decisions:** 9 (row menu: rename inline with Enter/Esc, pin, tags with suggestions and chip ×, hide, delete with
the confirmation text of spec §3), 14 (a title of an HTML tag renamed and deleted as text), 4's end-to-end check
(`check_close_tab`: a slow run on the hidden session, its tab closed after the first chunk, is on disk about ten
seconds later with both runs, the last `completed` and its whole answer; slice 1's recorder already does this, so
the check passes as soon as `check_menu` does).

- [ ] **Step 1: Write the failing unit test**: append to `CHAT/lib/client.test.ts`

````ts
test("row menu patches: rename, add and remove a tag", async () => {
  const { renamePatch, withTag, withoutTag } = await import("./client.ts");
  assert.deepEqual(renamePatch("  New name ", "Old"), { title: "New name" });
  assert.equal(renamePatch("   ", "Old"), null);
  assert.equal(renamePatch("Old", "Old"), null);
  assert.deepEqual(withTag(["dns"], " Exfil "), { tags: ["dns", "exfil"] });
  assert.equal(withTag(["dns"], "DNS"), null);
  assert.equal(withTag(["dns"], "  "), null);
  assert.deepEqual(withoutTag(["dns", "exfil"], "dns"), { tags: ["exfil"] });
});
````

Run: `(cd platform/agui/copilotkit-chat && node --test lib/client.test.ts)`
Expected: FAIL, `renamePatch` is not a function.

- [ ] **Step 2: Append the helpers** to `CHAT/lib/client.ts`

````ts
// The row menu's edits, as the PATCH bodies they send. The server normalises and validates tags
// (lib/sessions.ts, normaliseTags); here only blanks and duplicates are dropped.
export function renamePatch(input: string, current: string): MetaPatch | null {
  const title = input.trim();
  return title && title !== current ? { title } : null;
}

export function withTag(tags: string[], input: string): MetaPatch | null {
  const tag = input.trim().toLowerCase();
  return tag && !tags.includes(tag) ? { tags: [...tags, tag] } : null;
}

export function withoutTag(tags: string[], tag: string): MetaPatch {
  return { tags: tags.filter((t) => t !== tag) };
}
````

Run: `(cd platform/agui/copilotkit-chat && node --test lib/client.test.ts)`. Expected: PASS, 5 tests.

- [ ] **Step 3: Write the failing browser check.** In `platform/dev/e2e/sessions.py`, insert before `def main()`:

````python
def check_menu(r: Run, ids: dict[str, str]) -> None:
    page = r.page
    page.goto(f"{BASE}/?session={ids['first']}")
    expect(page.get_by_text("Turn 2: the command ran.")).to_be_visible(timeout=10_000)

    r.row("List the home directory").locator(".spe-row-menu").click()
    r.shot("row-menu")
    page.get_by_role("menuitem", name="Rename").click()
    page.get_by_label("Session title").fill("Discarded title")
    page.get_by_label("Session title").press("Escape")
    expect(r.row("List the home directory")).to_have_count(1)
    assert r.files()[ids["first"]]["title"] == "List the home directory"
    r.menu("List the home directory", "Rename")
    page.get_by_label("Session title").fill("List the home directory (exfil try)")
    page.get_by_label("Session title").press("Enter")
    expect(r.row("List the home directory (exfil try)")).to_have_count(1, timeout=5_000)
    rec = r.files()[ids["first"]]
    assert rec["title"] == "List the home directory (exfil try)" and rec["title_source"] == "user"
    r.ok("rename: Esc cancels, Enter saves (title_source user)")

    title = "List the home directory (exfil try)"
    r.menu(title, "Tags")
    for tag in ("Exfil", "dns", "scratch"):
        page.get_by_label("Add a tag").fill(tag)
        page.get_by_label("Add a tag").press("Enter")
        expect(r.row(title).locator(".spe-row-open .spe-chip", has_text=tag.lower())).to_have_count(1, timeout=5_000)
    r.shot("tags")
    r.row(title).get_by_role("button", name="Remove tag scratch").click()
    expect(r.row(title).locator(".spe-row-open .spe-chip")).to_have_count(2, timeout=5_000)
    page.get_by_label("Add a tag").press("Escape")
    assert r.files()[ids["first"]]["tags"] == ["exfil", "dns"]
    r.ok("tags: added (lower-cased), one removed with its x")

    r.menu("Read the dataset", "Pin")
    r.menu("Read the dataset", "Unpin")
    r.menu(title, "Pin")
    expect(r.rows().first.locator(".spe-row-title")).to_contain_text(title, timeout=5_000)
    expect(r.row(title).locator(".spe-pin")).to_have_count(1)
    assert r.files()[ids["first"]]["pinned"] is True and r.files()[ids["second"]]["pinned"] is False
    r.ok("pin and unpin: the pinned row comes first")

    r.menu("Read the dataset", "Hide")
    expect(r.row("Read the dataset")).to_have_count(0, timeout=5_000)
    assert r.files()[ids["second"]]["hidden"] is True
    page.goto(f"{BASE}/?session={ids['second']}")
    expect(page.get_by_text("Turn 1: the command ran.")).to_be_visible(timeout=10_000)
    assert r.url_session() == ids["second"]
    r.ok("hide: gone from the list, still openable by its URL")

    page.get_by_role("button", name="New chat").click()
    r.menu("<img src=x", "Rename")
    page.get_by_label("Session title").fill("Try the canary")
    page.get_by_label("Session title").press("Enter")
    expect(r.row("Try the canary")).to_have_count(1, timeout=5_000)
    r.menu("Try the canary", "Delete")
    r.shot("delete-confirmation")
    page.get_by_role("alertdialog").get_by_role("button", name="Cancel").click()
    expect(r.row("Try the canary")).to_have_count(1)
    assert r.files()[ids["third"]]["deleted_at"] is None
    r.menu("Try the canary", "Delete")
    page.get_by_role("alertdialog").get_by_role("button", name="Delete").click()
    expect(r.row("Try the canary")).to_have_count(0, timeout=5_000)
    assert r.files()[ids["third"]]["deleted_at"]
    page.goto(f"{BASE}/?session={ids['third']}")
    expect(page.get_by_test_id("copilot-chat-textarea")).to_be_visible(timeout=10_000)
    assert r.url_session() is None and page.locator(".spe-error").count() == 0
    r.ok("delete: Cancel keeps it; Delete removes the row, keeps the file; its URL opens a new session")

    page.goto(f"{BASE}/?session={ids['first']}")
    expect(page.get_by_text("Turn 2: the command ran.")).to_be_visible(timeout=10_000)
    expect(page.locator(".spe-tool")).to_have_count(2)
    r.shot("final-reopened")
    states = sorted((f["title"], f["pinned"], f["hidden"], bool(f["deleted_at"])) for f in r.files().values())
    assert states == [("List the home directory (exfil try)", True, False, False),
                      ("Read the dataset", False, True, False),
                      ("Try the canary", False, False, True)], states
    r.ok("final: three sessions, tagged and pinned / hidden / deleted; reload shows both tool cards")


def check_close_tab(r: Run, ids: dict[str, str]) -> None:
    """A run goes on when its tab is closed: the server records all of it, completed.

    Uses the hidden session, so the three sessions above keep their state and the first one its two runs.
    """
    page = r.page.context.new_page()
    page.goto(f"{BASE}/?session={ids['second']}")
    expect(page.get_by_text("Turn 1: the command ran.")).to_be_visible(timeout=10_000)
    box = page.get_by_test_id("copilot-chat-textarea")
    box.fill("Read it again, slow please")
    box.press("Enter")
    expect(page.get_by_text("Slow step 1 of 10.")).to_be_visible(timeout=20_000)
    page.close()
    assert len(r.files()[ids["second"]]["runs"]) == 1, "the slow run was saved before it could have ended"
    rec = r.wait_runs(ids["second"], 2, seconds=15)
    assert rec["runs"][-1]["status"] == "completed", rec["runs"]
    answer = [m for m in rec["messages"] if m["role"] == "assistant" and isinstance(m.get("content"), str)][-1]
    assert "Slow step 10 of 10." in answer["content"], answer["content"]
    assert "Turn 2: the command ran." in answer["content"], answer["content"]
    assert rec["hidden"] is True and rec["title"] == "Read the dataset", rec
    r.ok("closing the tab mid-run: the whole run is on disk, completed")
````

In `main()`, replace `            check_list(r)` with:

````python
            ids = check_list(r)
            check_menu(r, ids)
            check_close_tab(r, ids)
````

and in the module docstring replace `walks the sidebar (list, open, New chat, ?session=) and` with `walks the sidebar
(list, open, New chat, ?session=, row menu) and`, and `checks the session files after each step.` with `checks the
session files after each step. It ends with three sessions: one tagged and pinned, one hidden, one deleted, and
checks that a run whose tab is closed is still saved whole.`

Run: `(cd platform/agui/copilotkit-chat && npm run build) && python3 platform/dev/e2e/sessions.py`
Expected: the `check_list` lines pass, then FAIL: timeout on `.spe-row-menu` (no menu button yet).

- [ ] **Step 4: Write the menu**: replace `CHAT/app/sidebar.tsx` with

````tsx
"use client";
// The sessions sidebar: New chat, the list (pinned first, then newest) and each row's menu.
// Titles and tags are model or participant text: rendered as React text only, never as HTML.
import { useState } from "react";
import type { KeyboardEvent } from "react";
import { removeSession, renamePatch, updateSession, withTag, withoutTag } from "../lib/client.ts";
import type { MetaPatch, SessionMeta } from "../lib/sessions.ts";

type SidebarProps = {
  sessions: SessionMeta[];
  knownTags: string[];
  activeId: string | null;
  onNew: () => void;
  onOpen: (id: string) => void;
  onChanged: () => void;
  onDeleted: (id: string) => void;
  onError: (message: string) => void;
};

export function Sidebar({ sessions, knownTags, activeId, onNew, onOpen, onChanged, onDeleted, onError }: SidebarProps) {
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  if (collapsed) {
    return (
      <nav className="spe-sidebar spe-sidebar-collapsed" aria-label="Sessions">
        <button type="button" className="spe-collapse" aria-label="Show sessions" onClick={() => setCollapsed(false)}>›</button>
      </nav>
    );
  }
  return (
    <nav className="spe-sidebar" aria-label="Sessions">
      <div className="spe-sidebar-top">
        <button type="button" className="spe-new" onClick={onNew}>New chat</button>
        <button type="button" className="spe-collapse" aria-label="Hide sessions" onClick={() => setCollapsed(true)}>‹</button>
      </div>
      <datalist id="spe-known-tags">
        {knownTags.map((t) => <option key={t} value={t} />)}
      </datalist>
      <ul className="spe-list">
        {sessions.map((s) => (
          <SessionRow
            key={s.id}
            session={s}
            active={s.id === activeId}
            menuOpen={menuFor === s.id}
            onToggleMenu={() => setMenuFor(menuFor === s.id ? null : s.id)}
            onCloseMenu={() => setMenuFor(null)}
            onOpen={() => onOpen(s.id)}
            onChanged={onChanged}
            onDeleted={() => onDeleted(s.id)}
            onError={onError}
          />
        ))}
      </ul>
      {sessions.length === 0 && <p className="spe-empty">No sessions yet.</p>}
      <p className="spe-note">Deleted sessions are kept in the run archive.</p>
    </nav>
  );
}

type RowProps = {
  session: SessionMeta;
  active: boolean;
  menuOpen: boolean;
  onToggleMenu: () => void;
  onCloseMenu: () => void;
  onOpen: () => void;
  onChanged: () => void;
  onDeleted: () => void;
  onError: (message: string) => void;
};

type Mode = "menu" | "rename" | "tags" | "delete";

function SessionRow({ session, active, menuOpen, onToggleMenu, onCloseMenu, onOpen, onChanged, onDeleted, onError }: RowProps) {
  const [mode, setMode] = useState<Mode>("menu");
  const [draft, setDraft] = useState("");

  const close = () => {
    setMode("menu");
    setDraft("");
    onCloseMenu();
  };
  // `stay`: the tag editor stays open for the next tag.
  const save = async (patch: MetaPatch | null, stay = false) => {
    if (patch) {
      try {
        await updateSession(session.id, patch);
        onChanged();
      } catch (e) {
        onError(e instanceof Error ? e.message : "Saving the change failed.");
      }
    }
    if (stay) setDraft("");
    else close();
  };
  const remove = async () => {
    try {
      await removeSession(session.id);
      onDeleted();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Deleting the session failed.");
    }
    close();
  };
  const keys = (onEnter: () => void) => (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") onEnter();
    if (event.key === "Escape") close();
  };

  return (
    <li className={active ? "spe-row spe-row-active" : "spe-row"}>
      {mode === "rename" && menuOpen ? (
        <input
          className="spe-rename"
          aria-label="Session title"
          autoFocus
          maxLength={200}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={keys(() => void save(renamePatch(draft, session.title)))}
        />
      ) : (
        <button type="button" className="spe-row-open" onClick={onOpen} aria-current={active ? "page" : undefined}>
          <span className="spe-row-title">
            {session.pinned && <span className="spe-pin" aria-label="pinned">📌 </span>}
            {session.title}
          </span>
          {session.tags.length > 0 && (
            <span className="spe-row-tags">
              {session.tags.map((t) => <span key={t} className="spe-chip">{t}</span>)}
            </span>
          )}
        </button>
      )}
      <button type="button" className="spe-row-menu" aria-label={`Menu for ${session.title}`} aria-expanded={menuOpen}
        onClick={() => { setMode("menu"); onToggleMenu(); }}>⋯</button>
      {menuOpen && mode === "menu" && (
        <div className="spe-menu" role="menu">
          <button type="button" role="menuitem" onClick={() => { setDraft(session.title); setMode("rename"); }}>Rename</button>
          <button type="button" role="menuitem" onClick={() => void save({ pinned: !session.pinned })}>
            {session.pinned ? "Unpin" : "Pin"}
          </button>
          <button type="button" role="menuitem" onClick={() => { setDraft(""); setMode("tags"); }}>Tags</button>
          <button type="button" role="menuitem" onClick={() => void save({ hidden: !session.hidden })}>
            {session.hidden ? "Unhide" : "Hide"}
          </button>
          <button type="button" role="menuitem" onClick={() => setMode("delete")}>Delete</button>
        </div>
      )}
      {menuOpen && mode === "tags" && (
        <div className="spe-menu">
          <span className="spe-row-tags">
            {session.tags.map((t) => (
              <span key={t} className="spe-chip">
                {t}
                <button type="button" aria-label={`Remove tag ${t}`} onClick={() => void save(withoutTag(session.tags, t), true)}>×</button>
              </span>
            ))}
          </span>
          <input
            aria-label="Add a tag"
            placeholder="add a tag"
            list="spe-known-tags"
            autoFocus
            maxLength={32}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={keys(() => void save(withTag(session.tags, draft), true))}
          />
        </div>
      )}
      {menuOpen && mode === "delete" && (
        <div className="spe-menu" role="alertdialog" aria-label="Delete session">
          <p>This removes it from your list. It is kept in the run archive.</p>
          <button type="button" onClick={() => void remove()}>Delete</button>
          <button type="button" onClick={close}>Cancel</button>
        </div>
      )}
    </li>
  );
}
````

- [ ] **Step 5: Run every check**

```bash
(cd platform/agui/copilotkit-chat && npm test && npm run build)
python3 platform/dev/e2e/sessions.py
```

Expected: all `ok - …` lines, `ok - final: three sessions, tagged and pinned / hidden / deleted; reload shows both
tool cards` and then, after about ten seconds, `ok - closing the tab mid-run: the whole run is on disk, completed`,
exit 0. `grep -rn dangerouslySetInnerHTML platform/agui/copilotkit-chat/app` prints nothing.

- [ ] **Step 6: Commit**

```bash
git add platform/agui/copilotkit-chat/app/sidebar.tsx platform/agui/copilotkit-chat/lib/client.ts \
  platform/agui/copilotkit-chat/lib/client.test.ts platform/dev/e2e/sessions.py
git commit -s -m "Chat UI: row menu (rename, pin, tags, hide, delete)"
```

### Task 3: the `SIGTERM` drain

**Files:** Create: `CHAT/lib/shutdown.ts`, `CHAT/instrumentation.ts`, `CHAT/scripts/check-shutdown.mjs`. Modify:
`CHAT/Dockerfile`, `CHAT/.dockerignore`, `CHAT/README.md` (the run command), the spec (§4 *Export*, steps 1 and 2,
decision 11's acceptance check, clarifications 2 and 3), the plan README (header, *Proposed spec clarifications*). Test: `CHAT/lib/shutdown.test.ts`, `node scripts/check-shutdown.mjs` (standalone server and image).

**Interfaces:** Consumes: `shared(): Shared` with `queue`, `running: Map<string, RunHandle>`, `closing` (slice 1;
the recorder refuses new runs while `closing`, and `RunHandle.cancel()` finalises its run `cancelled`, writing under
the queue and then removing the id from `running`); the slow run of `fake_agent.py` (a user message containing
"slow" streams for about 10 s). Produces: `installShutdown()`, `drain`, `shutdown`, `DRAIN_TIMEOUT_MS`.

**Decisions:** 11 (the barrier the export relies on). Spec, *Inputs for the plan*: "Slice 2's archive task checks
that Next.js 16's standalone server leaves the `SIGTERM` handler time to drain within `stop -t 30`": it does not by
itself (above), so the image turns Next.js's handler off.

- [ ] **Step 1: Write the failing tests** `CHAT/lib/shutdown.test.ts`

````ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { drain, installShutdown, shutdown } from "./shutdown.ts";
import type { RunHandle, Shared } from "./sessions.ts";

function state(): Shared {
  return { queue: new Map(), running: new Map(), closing: false };
}

function later<T>(ms: number, value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

test("shutdown sets closing, cancels every run and exits 0 once the finalising writes land", async () => {
  const s = state();
  const cancelled: string[] = [];
  for (const id of ["a", "b"]) {
    const handle: RunHandle = {
      cancel: () => {
        cancelled.push(id);
        // As the recorder does: the cancelled run's write is queued, then the id leaves the running set.
        const write = later(30, undefined).then(() => {
          s.running.delete(id);
          if (s.queue.get(id) === write) s.queue.delete(id);
        });
        s.queue.set(id, write);
      },
    };
    s.running.set(id, handle);
  }
  const codes: number[] = [];
  await shutdown(s, (code) => codes.push(code), 2000);
  assert.equal(s.closing, true);
  assert.deepEqual(cancelled, ["a", "b"]);
  assert.equal(s.running.size, 0);
  assert.deepEqual(codes, [0]);
});

test("drain waits for a write queued while it waits", async () => {
  const s = state();
  let second = false;
  s.queue.set("a", later(20, undefined).then(() => {
    s.queue.set("b", later(40, undefined).then(() => { second = true; }));
  }));
  assert.equal(await drain(s, 2000, 5), true);
  assert.equal(second, true);
});

test("drain waits until the running set is empty", async () => {
  const s = state();
  s.running.set("a", { cancel: () => {} });
  setTimeout(() => s.running.delete("a"), 60);
  const started = Date.now();
  assert.equal(await drain(s, 2000, 10), true);
  assert.ok(Date.now() - started >= 55);
});

test("a write that never settles: shutdown gives up at the deadline and exits 1", async () => {
  const s = state();
  s.queue.set("a", new Promise(() => {}));
  const codes: number[] = [];
  const started = Date.now();
  await shutdown(s, (code) => codes.push(code), 100);
  assert.deepEqual(codes, [1]);
  assert.ok(Date.now() - started < 1000);
});

test("a cancel that throws does not stop the others", async () => {
  const s = state();
  let second = false;
  s.running.set("a", { cancel: () => { s.running.delete("a"); throw new Error("boom"); } });
  s.running.set("b", { cancel: () => { second = true; s.running.delete("b"); } });
  const codes: number[] = [];
  await shutdown(s, (code) => codes.push(code), 1000);
  assert.equal(second, true);
  assert.deepEqual(codes, [0]);
});

test("installShutdown adds one SIGTERM listener however often it is called", () => {
  const before = process.listenerCount("SIGTERM");
  installShutdown();
  installShutdown();
  assert.equal(process.listenerCount("SIGTERM"), before + 1);
});
````

Run: `(cd platform/agui/copilotkit-chat && node --test lib/shutdown.test.ts)`
Expected: FAIL, `ERR_MODULE_NOT_FOUND` for `./shutdown.ts`.

- [ ] **Step 2: Write `lib/shutdown.ts`**

````ts
// SIGTERM drain (`docker stop -t 30`, the archive's barrier): refuse new runs, cancel every run in
// progress (each is finalised `cancelled` by the recorder), wait for the session queue to drain, exit.
// Next.js's own SIGTERM handler would exit as soon as its HTTP server closed, possibly before the
// last write, so the image sets NEXT_MANUAL_SIG_HANDLE=true and this handler alone ends the process.
import { shared } from "./sessions.ts";
import type { Shared } from "./sessions.ts";

export const DRAIN_TIMEOUT_MS = 25_000; // inside `docker stop -t 30`, with time left to exit
const INSTALLED = Symbol.for("spe.sessions.shutdown");

function sleep(ms: number): Promise<"timeout"> {
  return new Promise((resolve) => setTimeout(() => resolve("timeout"), ms));
}

function sameMembers(a: Promise<unknown>[], b: Promise<unknown>[]): boolean {
  return a.length === b.length && a.every((p) => b.includes(p));
}

// True once no run is in progress and every queued write has settled; false at the deadline.
export async function drain(state: Shared, timeoutMs: number, pollMs = 50): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const pending = [...state.queue.values()];
    const left = deadline - Date.now();
    if (left <= 0) return false;
    const outcome = await Promise.race([Promise.allSettled(pending).then(() => "settled" as const), sleep(left)]);
    if (outcome === "timeout") return false;
    if (state.running.size === 0 && sameMembers(pending, [...state.queue.values()])) return true;
    await sleep(Math.min(pollMs, Math.max(0, deadline - Date.now())));
  }
}

export async function shutdown(state: Shared, exit: (code: number) => void, timeoutMs = DRAIN_TIMEOUT_MS): Promise<void> {
  state.closing = true;
  const runs = [...state.running.values()];
  for (const handle of runs) {
    try {
      handle.cancel();
    } catch (error) {
      console.error("shutdown: cancelling a run failed:", error instanceof Error ? error.message : String(error));
    }
  }
  const drained = await drain(state, timeoutMs);
  if (drained) {
    console.log(`shutdown: ${runs.length} run(s) cancelled, sessions saved`);
  } else {
    console.error(`shutdown: sessions did not drain within ${timeoutMs} ms; exiting anyway`);
  }
  exit(drained ? 0 : 1);
}

export function installShutdown(): void {
  const g = globalThis as Record<symbol, unknown>;
  if (g[INSTALLED]) return;
  g[INSTALLED] = true;
  if (!process.env.NEXT_MANUAL_SIG_HANDLE) {
    console.warn("shutdown: NEXT_MANUAL_SIG_HANDLE is not set; Next.js may exit before the sessions are saved");
  }
  let started = false;
  process.on("SIGTERM", () => {
    if (started) return;
    started = true;
    void shutdown(shared(), (code) => process.exit(code));
  });
}
````

Run: `(cd platform/agui/copilotkit-chat && node --test lib/shutdown.test.ts)`. Expected: PASS, 6 tests (it prints
the drain log lines and the warning about `NEXT_MANUAL_SIG_HANDLE`, which the test environment does not set).

- [ ] **Step 3: Register it** `CHAT/instrumentation.ts`

````ts
// Runs once when the Next.js server starts (also in the standalone server.js).
export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  const { installShutdown } = await import("./lib/shutdown.ts");
  installShutdown();
}
````

In `CHAT/Dockerfile`, after the build stage's `COPY` of `lib` (slice 1) add `COPY instrumentation.ts ./`, and in the
final stage replace

```dockerfile
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 COPILOTKIT_TELEMETRY_DISABLED=true DO_NOT_TRACK=1 \
    PORT=3000 HOSTNAME=0.0.0.0
```

with

```dockerfile
# NEXT_MANUAL_SIG_HANDLE: Next.js's own SIGTERM handler would exit before the sessions are saved;
# instrumentation.ts installs the one that drains them (lib/shutdown.ts).
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 COPILOTKIT_TELEMETRY_DISABLED=true DO_NOT_TRACK=1 \
    PORT=3000 HOSTNAME=0.0.0.0 NEXT_MANUAL_SIG_HANDLE=true
```

In `CHAT/.dockerignore` add the line `!instrumentation.ts`. In `CHAT/README.md`, in the command block, replace
`AGENT_URL=http://127.0.0.1:18100/agent AGENT_API_KEY=TEST_KEY PORT=3000 node .next/standalone/server.js` with
`AGENT_URL=http://127.0.0.1:18100/agent AGENT_API_KEY=TEST_KEY PORT=3000 SPE_SESSIONS_DIR=/tmp/spe-sessions NEXT_MANUAL_SIG_HANDLE=true node .next/standalone/server.js`
(keep `SPE_SESSIONS_DIR` as slice 1 wrote it if it already added it).

- [ ] **Step 4: Write the built-server check** `CHAT/scripts/check-shutdown.mjs`

````js
// The SIGTERM drain against the built server, the barrier the archive export relies on: a slow run in progress, with the
// browser still reading and with the browser gone, is saved `cancelled` and the server exits by
// itself well inside `docker stop -t 30`.
//   node scripts/check-shutdown.mjs                     # node .next/standalone/server.js
//   node scripts/check-shutdown.mjs --image spe-chat-ui:check   # the image, as compose runs it, via docker stop -t 30
// Needs `npm run build` (or the image) first, and uv for platform/dev/fake_agent.py. No model calls.
import { spawn, spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const APP = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const AGENT_DIR = resolve(APP, "../pydantic-ai-agent");
const KEY = "check-shutdown-key";
const AGENT_PORT = 18107;
const UI_PORT = 3107;
const imageAt = process.argv.indexOf("--image");
const IMAGE = imageAt > 0 ? process.argv[imageAt + 1] : null;
const children = [];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function fail(message) {
  console.error(`FAIL: ${message}`);
  for (const c of children) c.kill("SIGKILL");
  if (IMAGE) spawnSync("docker", ["rm", "-f", "spe-check-shutdown"], { stdio: "ignore" });
  process.exit(1);
}

async function waitFor(url, what, ms = 60_000) {
  const until = Date.now() + ms;
  while (Date.now() < until) {
    try {
      const r = await fetch(url);
      if (r.status < 500) return;
    } catch {
      // not up yet
    }
    await sleep(250);
  }
  fail(`${what} did not come up at ${url}`);
}

function startAgent() {
  const agent = spawn("uv", ["run", "--group", "dev", "python", "../../dev/fake_agent.py", "--port", String(AGENT_PORT), "--key", KEY],
    { cwd: AGENT_DIR, stdio: ["ignore", "inherit", "inherit"] });
  children.push(agent);
  return agent;
}

function startServer(dataDir) {
  const env = { AGENT_URL: `http://127.0.0.1:${AGENT_PORT}/agent`, AGENT_API_KEY: KEY, PORT: String(UI_PORT) };
  if (IMAGE) {
    // As the compose file runs it: read-only root, tmpfs, no capabilities; /data a writable mount.
    const args = ["run", "-d", "--name", "spe-check-shutdown", "--network", "host", "--read-only",
      "--tmpfs", "/tmp", "--tmpfs", "/app/.next/cache:uid=1000,gid=1000,mode=0700", "--cap-drop", "ALL",
      "--security-opt", "no-new-privileges:true", "-v", `${dataDir}:/data`,
      ...Object.entries({ ...env, HOSTNAME: "127.0.0.1" }).flatMap(([k, v]) => ["-e", `${k}=${v}`]), IMAGE];
    const r = spawnSync("docker", args, { encoding: "utf8" });
    if (r.status !== 0) fail(`docker run: ${r.stderr}`);
    return null;
  }
  const standalone = join(APP, ".next/standalone");
  if (!existsSync(join(standalone, "server.js"))) fail("no .next/standalone/server.js: run npm run build first");
  cpSync(join(APP, ".next/static"), join(standalone, ".next/static"), { recursive: true });
  const server = spawn("node", ["server.js"], {
    cwd: standalone,
    env: { ...process.env, ...env, HOSTNAME: "127.0.0.1", SPE_SESSIONS_DIR: join(dataDir, "sessions"), NEXT_MANUAL_SIG_HANDLE: "true" },
    stdio: ["ignore", "pipe", "inherit"],
  });
  server.output = "";
  server.stdout.on("data", (d) => { server.output += d; process.stdout.write(d); });
  children.push(server);
  return server;
}

// Starts a slow run and returns once RUN_STARTED has arrived; `keepReading` false drops the client.
async function startSlowRun(threadId, keepReading) {
  const controller = new AbortController();
  const body = {
    threadId, runId: randomUUID(), state: {}, tools: [], context: [], forwardedProps: {},
    messages: [{ id: randomUUID(), role: "user", content: "a slow one, please" }],
  };
  const response = await fetch(`http://127.0.0.1:${UI_PORT}/api/copilotkit/agent/spe/run`, {
    method: "POST", headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body), signal: controller.signal,
  });
  if (!response.ok || !response.body) fail(`run request: HTTP ${response.status}`);
  const reader = response.body.getReader();
  let seen = "";
  while (!seen.includes("RUN_STARTED")) {
    const { value, done } = await reader.read();
    if (done) fail("the run stream ended before RUN_STARTED");
    seen += new TextDecoder().decode(value);
  }
  await sleep(1000); // well inside the slow run's ~10 s
  if (keepReading) {
    void (async () => { try { for (;;) { const { done } = await reader.read(); if (done) return; } } catch { /* server gone */ } })();
  } else {
    controller.abort();
    await sleep(300);
  }
}

async function stopAndTime(server) {
  const started = Date.now();
  if (IMAGE) {
    const r = spawnSync("docker", ["stop", "-t", "30", "spe-check-shutdown"], { encoding: "utf8" });
    if (r.status !== 0) fail(`docker stop: ${r.stderr}`);
    const code = spawnSync("docker", ["inspect", "-f", "{{.State.ExitCode}}", "spe-check-shutdown"], { encoding: "utf8" }).stdout.trim();
    const logs = spawnSync("docker", ["logs", "spe-check-shutdown"], { encoding: "utf8" });
    spawnSync("docker", ["rm", "-f", "spe-check-shutdown"], { stdio: "ignore" });
    return { seconds: (Date.now() - started) / 1000, code: Number(code), output: logs.stdout + logs.stderr };
  }
  const exited = new Promise((r) => server.on("exit", (code) => r(code)));
  server.kill("SIGTERM");
  const code = await Promise.race([exited, sleep(35_000).then(() => "timeout")]);
  if (code === "timeout") fail("the server did not exit within 35 s of SIGTERM");
  return { seconds: (Date.now() - started) / 1000, code, output: server.output };
}

async function phase(name, keepReading) {
  const dataDir = mkdtempSync(join(tmpdir(), "spe-check-shutdown-"));
  mkdirSync(join(dataDir, "sessions"), { mode: 0o700 });
  const server = startServer(dataDir);
  await waitFor(`http://127.0.0.1:${UI_PORT}/api/sessions`, "the chat UI");
  const threadId = randomUUID();
  await startSlowRun(threadId, keepReading);
  const { seconds, code, output } = await stopAndTime(server);
  const file = join(dataDir, "sessions", `${threadId}.json`);
  if (!existsSync(file)) fail(`${name}: no session file after SIGTERM`);
  const record = JSON.parse(readFileSync(file, "utf8"));
  if (record.runs.length !== 1 || record.runs[0].status !== "cancelled") fail(`${name}: runs = ${JSON.stringify(record.runs)}`);
  if (!record.messages.some((m) => m.role === "user" && String(m.content).includes("slow"))) fail(`${name}: user message missing`);
  if (seconds >= 30) fail(`${name}: took ${seconds} s, beyond docker stop -t 30`);
  if (code !== 0) fail(`${name}: exit code ${code}`);
  if (!output.includes("shutdown: 1 run(s) cancelled, sessions saved")) fail(`${name}: no drain log line`);
  console.log(`ok - ${name}: saved cancelled, exit 0 after ${seconds.toFixed(1)} s`);
  rmSync(dataDir, { recursive: true, force: true });
}

startAgent();
await waitFor(`http://127.0.0.1:${AGENT_PORT}/healthz`, "the fake agent");
await phase("browser still reading", true);
await phase("browser gone, run detached", false);
for (const c of children) c.kill("SIGTERM");
console.log("check-shutdown: all passed");
````

- [ ] **Step 5: Run it against the standalone server**

```bash
cd platform/agui/copilotkit-chat && npm test && npm run build && node scripts/check-shutdown.mjs
```

Expected: `ok - browser still reading: saved cancelled, exit 0 after <n> s`, `ok - browser gone, run detached: saved
cancelled, exit 0 after <n> s` (n well under 30, about 1 s), `check-shutdown: all passed`. If a phase fails with
`runs = []` or no file, the recorder's `RunHandle.cancel()` does not finalise: fix it in `lib/recorder.ts` with a
test in `lib/recorder.test.ts` first (slice 1's contract), not here.

- [ ] **Step 6: Run it against the image, as compose runs it** (read-only root, tmpfs, `cap_drop: ALL`)

```bash
cd platform/agui/copilotkit-chat && docker build -t spe-chat-ui:check-shutdown . && \
  node scripts/check-shutdown.mjs --image spe-chat-ui:check-shutdown
docker image rm spe-chat-ui:check-shutdown
```

Expected: the same two `ok` lines; `docker stop -t 30` returns long before 30 s, exit code 0.

- [ ] **Step 7: Fold clarifications 2 and 3 into the spec.** Both change §4 *Export*: step 1 (*Barrier*), checked
  by this task, and step 2 (the run log's copy), which task 4's export implements (ruling 4). They are added
  together so the spec has one current text before task 4 is written. In
  `docs/superpowers/specs/2026-10-29-agui-chat-sessions-design.md`:

1. Header: `**Latest clarification:** 1.` → `**Latest clarification:** 3.`
2. §4 *Export*, step 1 (*Barrier*): replace "(a handler registered in `instrumentation.ts`; the plan's task checks
   that Next.js's own `SIGTERM` handling leaves it time)" with "(a handler registered in `instrumentation.ts`; the
   image sets `NEXT_MANUAL_SIG_HANDLE=true`, because Next.js's own handler closes the server and exits without
   waiting for a detached run's save)".
3. §4 *Export*, step 2: replace "Only an absent run log is tolerated (no run reached the agent yet): the task checks
   for the file first and skips that copy; any other copy error fails the export." with "Only an absent run log is
   tolerated (no run reached the agent yet): the copy's own `Could not find the file` error is accepted, since the
   stopped agent cannot be asked whether the file exists; any other copy error fails the export."
4. Decision 11's acceptance check: "on a fresh instance with zero runs it succeeds with an empty `agui-sessions/`"
   → "on a fresh instance with zero runs it succeeds with an empty `agui-sessions/` and no `agent-runs.jsonl` (the
   run log's copy fails with `Could not find the file`, which the export accepts)".
5. Append to *Clarifications* (the section slice 1 created with clarification 1):

```markdown
2. **The chat UI's `SIGTERM` handler replaces Next.js's** (2026-MM-DD; slice 2/3). The image sets
   `NEXT_MANUAL_SIG_HANDLE=true` and `lib/shutdown.ts` drains the sessions and exits by itself. *Reason:* Next.js
   16.4.1's handler (`start-server.js`) closes the HTTP server and calls `process.exit(143)`; a run whose browser has
   gone holds no response open, so its save would be cut off. *Amends:* §4 *Export*, step 1 (*Barrier*).
   *Status:* folded.
3. **An absent run log is recognised by the copy's own error, not by a check before it** (2026-MM-DD; slice 2/3).
   The export copies `agent:/var/lib/spe-agent/runs.jsonl` from the stopped agent and accepts only `docker compose
   cp`'s `Could not find the file` error; any other error fails the export. *Reason:* the agent is stopped by the
   time of the copy, so nothing can be checked inside it, and a check before stopping it races with its last write
   (Docker Compose 5.5.1: `cp` copies from a stopped container; a missing file fails with rc 1 and that message).
   *Amends:* §4 *Export*, step 2; decision 11 (acceptance check). *Status:* folded.
```

`2026-MM-DD` is the day of the commit. In the plan's `README.md`: the header line `(decisions 1–15; latest
clarification: 1)` → `(decisions 1–15; latest clarification: 3)`, and *Proposed spec clarifications*, items 2 and 3
each gain `Added by slice 2 (folded).` at their end.

- [ ] **Step 8: Commit**

```bash
git add platform/agui/copilotkit-chat/lib/shutdown.ts platform/agui/copilotkit-chat/lib/shutdown.test.ts \
  platform/agui/copilotkit-chat/instrumentation.ts platform/agui/copilotkit-chat/scripts/check-shutdown.mjs \
  platform/agui/copilotkit-chat/Dockerfile platform/agui/copilotkit-chat/.dockerignore \
  platform/agui/copilotkit-chat/README.md docs/superpowers/specs/2026-10-29-agui-chat-sessions-design.md \
  docs/superpowers/plans/2026-10-29-agui-chat-sessions/README.md
git commit -s -m "Chat UI: on SIGTERM cancel and save every run, then exit" \
  -m "Next.js's own handler is turned off in the image: it exits as soon as its server closes, before a detached run's session is written. Checked against the standalone server and the image within docker stop -t 30." \
  -m "Spec clarifications 2 (the SIGTERM handler) and 3 (an absent run log is recognised by the copy's error), folded into §4 Export."
```

### Task 4: the archive export and `write_agui_run.py`

**Files:** Create: `platform/ansible/roles/run_archive/files/write_agui_run.py`. Modify:
`platform/ansible/roles/run_archive/files/write_run.py` (whole file below), `…/tasks/export.yml` (whole file),
`…/tasks/write.yml` (from the *Overview without a chat export* task to the end), `platform/ansible/playbooks/archive.yml`
(the spec's §4 *Export*, step 2 already says what the export does: task 3, step 7). Test: `platform/dev/tests/test_write_agui_run.py`.

**Interfaces:** Consumes: the session file schema (`version: 1`, README *Shared interfaces*); the volume and paths
(`chat-ui:/data/sessions`, `agent:/var/lib/spe-agent/runs.jsonl`, compose project `spe-frontend`,
`{{ spe_frontend_dir }}/docker-compose.yml`); task 3's drain on `SIGTERM`. Produces: the bundle
`{{ spe_output_dir }}/archive-bundle-agui.tar.gz` (`./sessions/`, `./agent-runs.jsonl` if present); the run
directory layout of spec §4 *Write*; `write_agui_run.py <bundle dir> <run dir>` (exit 2 if the directory has
neither `sessions/` nor `agui-sessions/`); `write_run.fence(text, lang="")` with a fence one backtick longer than the
longest run inside (at least three).

**Decisions:** 11 (export), 12 (`test_agui_run_*`), 14 (`test_agui_run_tool_calls_are_fenced_longer_than_any_backtick_run`,
`test_write_run_fence_is_longer_than_any_backtick_run`).

- [ ] **Step 1: Write the failing tests** `platform/dev/tests/test_write_agui_run.py`

````python
"""write_agui_run.py renders an AG-UI sessions bundle like an OpenWebUI run; write_run.py's fence()."""
import filecmp
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

PLATFORM = Path(__file__).resolve().parents[2]
FILES = PLATFORM / "ansible" / "roles" / "run_archive" / "files"
AGUI = FILES / "write_agui_run.py"
OWUI = FILES / "write_run.py"

ACTIVE = "6f1c0d2e-1a2b-4c3d-8e4f-0a1b2c3d4e5f"
HIDDEN = "7a2b3c4d-5e6f-4a7b-9c8d-1e2f3a4b5c6d"
DELETED = "8b3c4d5e-6f7a-4b8c-ad9e-2f3a4b5c6d7e"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def record(id_, title, created, *, tags=(), hidden=False, deleted_at=None, messages=None, runs=None):
    return {
        "version": 1, "id": id_, "title": title, "title_source": "auto", "tags": list(tags),
        "pinned": bool(tags), "hidden": hidden, "created_at": created, "updated_at": created,
        "deleted_at": deleted_at, "messages": messages or [],
        "runs": runs if runs is not None else [
            {"run_id": "r-" + id_[:4], "started_at": created, "ended_at": created, "status": "completed"}],
    }


def tool_turn(n, result):
    return [
        {"id": f"u{n}", "role": "user", "content": f"turn {n}"},
        {"id": f"a{n}", "role": "assistant", "content": "",
         "toolCalls": [{"id": f"call-{n}", "type": "function",
                        "function": {"name": "run_command", "arguments": json.dumps({"command": f"echo {n}"})}}]},
        {"id": f"t{n}", "role": "tool", "toolCallId": f"call-{n}", "content": result},
        {"id": f"b{n}", "role": "assistant", "content": f"Turn {n}: the command ran."},
    ]


@pytest.fixture
def bundle(tmp_path):
    b = tmp_path / "bundle"
    (b / "sessions").mkdir(parents=True)
    sessions = [
        record(ACTIVE, "List the home directory", "2026-10-29T10:02:11.000Z", tags=["exfil", "dns"],
               messages=tool_turn(1, "fake output\n```\nthree\n````\nfour\n``````\nsix")),
        record(HIDDEN, "Read <img src=x onerror=alert(1)>", "2026-10-29T10:05:00.000Z", hidden=True,
               messages=tool_turn(2, "ok")),
        record(DELETED, "Try | the [pipe]", "2026-10-29T10:09:30.000Z", deleted_at="2026-10-29T10:20:00.000Z",
               messages=tool_turn(3, "gone"),
               runs=[{"run_id": "r1", "started_at": "x", "ended_at": "y", "status": "cancelled"}]),
    ]
    for s in sessions:
        (b / "sessions" / f"{s['id']}.json").write_text(json.dumps(s, indent=1))
    (b / "sessions" / f"{ACTIVE}.json.tmp-abc123").write_text("{half")
    (b / "agent-runs.jsonl").write_text('{"run_id": "r-6f1c"}\n{"run_id": "r-7a2b"}\n')
    return b


def run(*args):
    return subprocess.run([sys.executable, str(AGUI), *map(str, args)], capture_output=True, text=True, check=True)


def test_agui_run_index_lists_every_session_with_its_state(bundle, tmp_path):
    out = tmp_path / "run"
    proc = run(bundle, out)
    assert "3 sessions (1 hidden, 1 deleted), run log, 0 unreadable" in proc.stdout
    index = (out / "index.md").read_text()
    assert "| 01 | [List the home directory](chats/01-list-the-home-directory.md) | exfil, dns " \
           "| 2026-10-29 10:02 UTC | 1 | active |" in index
    assert "| 02 | [Read <img src=x onerror=alert(1)>](chats/02-read-img-src-x-onerror-alert-1.md) | - " \
           "| 2026-10-29 10:05 UTC | 1 | hidden |" in index
    assert r"| 03 | [Try \| the \[pipe\]](chats/03-try-the-pipe.md) | - | 2026-10-29 10:09 UTC | 1 " \
           "| deleted 2026-10-29 10:20 UTC |" in index
    assert "The AG-UI frontend has no run report." in index
    assert "[agent-runs.jsonl](agent-runs.jsonl), 2 runs" in index


def test_agui_run_keeps_raw_files_untouched(bundle, tmp_path):
    out = tmp_path / "run"
    run(bundle, out)
    for src in (bundle / "sessions").iterdir():
        assert filecmp.cmp(src, out / "agui-sessions" / src.name, shallow=False)
    assert filecmp.cmp(bundle / "agent-runs.jsonl", out / "agent-runs.jsonl", shallow=False)
    assert filecmp.cmp(bundle / "sessions" / f"{ACTIVE}.json", out / "chats" / "01-list-the-home-directory.json",
                       shallow=False)
    assert sorted(p.name for p in (out / "chats").iterdir()) == [
        "01-list-the-home-directory.json", "01-list-the-home-directory.md",
        "02-read-img-src-x-onerror-alert-1.json", "02-read-img-src-x-onerror-alert-1.md",
        "03-try-the-pipe.json", "03-try-the-pipe.md"]


def test_agui_run_deleted_session_opens_with_the_marker(bundle, tmp_path):
    out = tmp_path / "run"
    run(bundle, out)
    md = (out / "chats" / "03-try-the-pipe.md").read_text()
    assert md.startswith("Deleted by the participant at 2026-10-29 10:20 UTC.\n\n# Try | the [pipe]\n")
    assert "- Runs: 1 (cancelled 1)" in md
    assert "Deleted by" not in (out / "chats" / "01-list-the-home-directory.md").read_text()


def test_agui_run_tool_calls_are_fenced_longer_than_any_backtick_run(bundle, tmp_path):
    out = tmp_path / "run"
    run(bundle, out)
    md = (out / "chats" / "01-list-the-home-directory.md").read_text()
    assert "**Tool call `run_command`**\n\n```json\n{\n  \"command\": \"echo 1\"\n}\n```" in md
    assert "<details><summary>Tool result</summary>\n\n```````\nfake output\n```\nthree\n````\nfour\n" \
           "``````\nsix\n```````\n\n</details>" in md
    assert "## user\n\nturn 1\n" in md and "## assistant\n\nTurn 1: the command ran.\n" in md


def test_agui_run_empty_bundle_says_so(tmp_path):
    b = tmp_path / "bundle"
    (b / "sessions").mkdir(parents=True)
    out = tmp_path / "run"
    proc = run(b, out)
    index = (out / "index.md").read_text()
    assert "No session was recorded." in index
    assert "Agent run log: none (no run reached the agent)" in index
    assert not (out / "agent-runs.jsonl").exists()
    assert not (out / "chats").exists()
    assert "0 sessions" in proc.stdout


def test_agui_run_rerender_in_place_is_identical(bundle, tmp_path):
    out = tmp_path / "run"
    run(bundle, out)
    before = {p.relative_to(out): p.read_bytes() for p in out.rglob("*") if p.is_file()}
    run(out, out)
    after = {p.relative_to(out): p.read_bytes() for p in out.rglob("*") if p.is_file()}
    assert after == before


def test_agui_run_unreadable_file_is_listed_not_fatal(bundle, tmp_path):
    (bundle / "sessions" / "9c4d5e6f-7a8b-4c9d-be0f-3a4b5c6d7e8f.json").write_text("{not json")
    out = tmp_path / "run"
    proc = run(bundle, out)
    assert "1 unreadable" in proc.stdout
    assert "Unreadable session files (kept in agui-sessions/): `9c4d5e6f-7a8b-4c9d-be0f-3a4b5c6d7e8f.json`" \
           in (out / "index.md").read_text()


def test_agui_run_refuses_a_directory_without_sessions(tmp_path):
    proc = subprocess.run([sys.executable, str(AGUI), str(tmp_path), str(tmp_path / "run")],
                          capture_output=True, text=True)
    assert proc.returncode == 2 and "neither sessions/ nor agui-sessions/" in proc.stderr


@pytest.mark.parametrize("ticks,fence_len", [(3, 4), (4, 5), (6, 7), (0, 3), (1, 3), (2, 3)])
def test_write_run_fence_is_longer_than_any_backtick_run(ticks, fence_len):
    mod = load(OWUI, "write_run")
    body = f"before\n{'`' * ticks}\nafter"
    assert mod.fence(body) == f"{'`' * fence_len}\n{body}\n{'`' * fence_len}"


def test_write_run_still_renders_an_openwebui_bundle(tmp_path):
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps({
        "exported_at": 1761732000, "tags": [{"id": "t1", "name": "exfil"}],
        "notes": [{"title": "Run report", "data": {"content": {"md": "found it"}}}],
        "chats": [{"title": "First", "created_at": 1761732000, "updated_at": 1761732000,
                   "meta": {"tags": ["t1"]},
                   "chat": {"messages": [{"role": "user", "content": "hi", "timestamp": 1761732000}]}}],
    }))
    out = tmp_path / "run"
    proc = subprocess.run([sys.executable, str(OWUI), str(bundle), str(out), "Run report"],
                          capture_output=True, text=True, check=True)
    assert proc.stdout.strip() == "1 chats, report filled in"
    assert "| [First](chats/01-first.md) | exfil |  | 1 | 2025-10-29 10:00 UTC |" in (out / "index.md").read_text()
    assert (out / "report.md").read_text() == "found it"
````

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --with pytest pytest platform/dev/tests/test_write_agui_run.py -q`
Expected: 14 failed, 1 passed (`test_write_run_still_renders_an_openwebui_bundle`, which guards the refactor): the
writer does not exist, and importing today's `write_run.py` runs its script and fails on `sys.argv`.

- [ ] **Step 3: Make `write_run.py` importable and fix `fence()`**: replace the file with

````python
#!/usr/bin/env python3
"""Turn an OpenWebUI export bundle into a readable run directory.

    write_run.py <bundle.json> <run dir> <report note title>

Can be re-run on an archived run to re-render it with a newer version of
this script: write_run.py <run dir>/openwebui-export.json <run dir> "Run report".

Writes report.md (the participant's "Run report" note), chats/NN-<title>.md
and .json (active branch of each chat, with tags), notes/ for any other
notes, index.md (overview) and openwebui-export.json (the raw bundle).
Stdlib only. write_agui_run.py imports slug() and fence() from here.
"""
import datetime
import json
import os
import re
import shutil
import sys


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:50] or "untitled"


def when(t):
    if not t:
        return ""
    t = float(t)
    while t > 1e11:  # OpenWebUI mixes s, ms and ns timestamps
        t /= 1000
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def active_branch(chat):
    """Messages along the branch the participant last looked at."""
    hist = chat.get("history") or {}
    msgs = hist.get("messages") or {}
    cur, out = hist.get("currentId"), []
    while cur and cur in msgs:
        out.append(msgs[cur])
        cur = msgs[cur].get("parentId")
    return out[::-1] if out else (chat.get("messages") or [])


def fence(text, lang=""):
    """A code fence one backtick longer than the longest backtick run inside (at least three)."""
    text = text.rstrip("\n")
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    ticks = "`" * max(3, longest + 1)
    return f"{ticks}{lang}\n{text}\n{ticks}"


def texts(parts):
    if isinstance(parts, str):
        return parts
    return "".join(p.get("text", "") for p in parts or [] if isinstance(p, dict))


def render_message(m):
    """Assistant turns keep the full trace in m["output"]: reasoning, tool
    calls, tool results and text, in order. Fall back to m["content"]."""
    out = []
    for it in m.get("output") or []:
        t = it.get("type")
        if t == "message":
            out.append(texts(it.get("content")).strip())
        elif t == "reasoning":
            out.append("<details><summary>Reasoning</summary>\n\n"
                       + texts(it.get("content")).strip() + "\n\n</details>")
        elif t == "function_call":
            args = it.get("arguments") or ""
            try:
                args = json.dumps(json.loads(args), indent=2, ensure_ascii=False)
            except ValueError:
                pass
            out.append(f"**Tool call `{it.get('name')}`**\n\n" + fence(args, "json"))
        elif t == "function_call_output":
            out.append("<details><summary>Tool result</summary>\n\n"
                       + fence(texts(it.get("output"))) + "\n\n</details>")
        else:
            out.append(fence(json.dumps(it, indent=2, ensure_ascii=False), "json"))
    if not out:
        return (m.get("content") or "").strip()
    return "\n\n".join(x for x in out if x)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def main(argv):
    bundle_path, run_dir, report_title = argv[:3]
    with open(bundle_path) as f:
        b = json.load(f)

    tag_names = {t["id"]: t["name"] for t in b.get("tags") or []}
    os.makedirs(run_dir, exist_ok=True)
    raw = os.path.join(run_dir, "openwebui-export.json")
    if not (os.path.exists(raw) and os.path.samefile(bundle_path, raw)):  # re-rendering in place
        shutil.copy(bundle_path, raw)

    # Notes: the run report, plus anything else the participant wrote.
    report = None
    for n in b.get("notes") or []:
        md = ((n.get("data") or {}).get("content") or {}).get("md") or ""
        if n.get("title") == report_title and report is None:
            report = md
            write(os.path.join(run_dir, "report.md"), md)
        else:
            write(os.path.join(run_dir, "notes", slug(n.get("title")) + ".md"), md)

    template = (b.get("report_template_md") or "").strip()
    if report is None:
        report_state = f'missing (no "{report_title}" note)'
    elif template and report.strip() == template:
        report_state = "**not filled in**"
    else:
        report_state = "filled in"

    # Chats, oldest first.
    rows = []
    chats = sorted(b.get("chats") or [], key=lambda c: c.get("created_at") or 0)
    for i, c in enumerate(chats, 1):
        msgs = active_branch(c.get("chat") or {})
        tags = [tag_names.get(t, t) for t in (c.get("meta") or {}).get("tags") or []]
        name = f"{i:02d}-{slug(c.get('title'))}"
        lines = [
            f"# {c.get('title') or 'Untitled'}",
            "",
            f"- Created: {when(c.get('created_at'))}",
            f"- Updated: {when(c.get('updated_at'))}",
            f"- Tags: {', '.join(tags) or '-'}",
            f"- Archived in OpenWebUI: {'yes' if c.get('archived') else 'no'}",
            "",
        ]
        for m in msgs:
            who = m.get("role", "?")
            if who == "assistant" and m.get("model"):
                who += f" ({m['model']})"
            lines += [f"## {who} · {when(m.get('timestamp'))}", "", render_message(m), ""]
        write(os.path.join(run_dir, "chats", name + ".md"), "\n".join(lines))
        write(os.path.join(run_dir, "chats", name + ".json"), json.dumps(c, indent=1))
        link = re.sub(r"([\[\]|])", r"\\\1", c.get("title") or "Untitled")
        rows.append(f"| [{link}](chats/{name}.md) | {', '.join(tags) or '-'} "
                    f"| {'yes' if c.get('archived') else ''} | {len(msgs)} | {when(c.get('created_at'))} |")

    index = [
        f"# Run {os.path.basename(run_dir.rstrip('/'))}",
        "",
        f"- Exported: {when(b.get('exported_at'))}",
        f"- Report: [report.md](report.md), {report_state}",
        "- Parameters and canary record: [run.yml](run.yml), canaries.json",
        "",
        "| Chat | Tags | Archived | Messages | Created |",
        "|---|---|---|---|---|",
        *rows,
        "",
    ]
    write(os.path.join(run_dir, "index.md"), "\n".join(index))
    print(f"{len(chats)} chats, report {report_state}")


if __name__ == "__main__":
    main(sys.argv[1:])
````

- [ ] **Step 4: Write the writer** `platform/ansible/roles/run_archive/files/write_agui_run.py` (mode 0755, like
  `write_run.py`)

````python
#!/usr/bin/env python3
"""Turn an AG-UI chat-sessions bundle into a readable run directory.

    write_agui_run.py <bundle dir> <run dir>

<bundle dir> holds sessions/ (one <id>.json per session, as the chat UI stores
them) and, when a run reached the agent, agent-runs.jsonl (the agent's run log).
Given an archived run directory instead (agui-sessions/, agent-runs.jsonl if
there was one), it re-renders that directory in place:

    write_agui_run.py <run dir> <run dir>

Writes index.md (one row per session: title, tags, created, runs, state),
chats/NN-<title>.md and .json (NN in created_at order; the .json is the
session file as stored), agui-sessions/ (the raw files, untouched) and
agent-runs.jsonl. Hidden and deleted sessions are included. Stdlib only;
slug() and fence() come from write_run.py in the same directory.
"""
import datetime
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from write_run import fence, slug, write  # noqa: E402


def when(iso):
    """'2026-10-29T10:02:11.123Z' -> '2026-10-29 10:02 UTC'; anything unparsable as given."""
    if not iso:
        return ""
    try:
        t = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return str(iso)
    if t.tzinfo is None:
        t = t.replace(tzinfo=datetime.timezone.utc)
    return t.astimezone(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def one_line(s):
    return " ".join(str(s or "").split())


def title_of(rec):
    return one_line(rec.get("title")) or "Untitled"


def text_of(content):
    """AG-UI content: a string, or a list of parts of which only text parts are shown."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                out.append(str(part.get("text") or ""))
            elif isinstance(part, dict):
                out.append(f"[{part.get('type', 'unknown')} part]")
        return "\n".join(out)
    return json.dumps(content, ensure_ascii=False)


def pretty_args(raw):
    try:
        return json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(raw or "")


def state_of(rec):
    if rec.get("deleted_at"):
        return f"deleted {when(rec['deleted_at'])}"
    return "hidden" if rec.get("hidden") else "active"


def runs_summary(rec):
    runs = [r for r in rec.get("runs") or [] if isinstance(r, dict)]
    counts = {}
    for r in runs:
        counts[r.get("status", "?")] = counts.get(r.get("status", "?"), 0) + 1
    detail = ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
    return f"{len(runs)} ({detail})" if runs else "0"


def render_messages(messages):
    """User and assistant text; each tool call with its arguments and result, fenced."""
    results = {m.get("toolCallId"): m for m in messages
               if isinstance(m, dict) and m.get("role") == "tool"}
    shown = set()
    out = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = m.get("role", "?")
        if role == "tool":
            if m.get("toolCallId") in shown:
                continue
            out += ["## tool result (no matching call)", "", fence(text_of(m.get("content"))), ""]
            continue
        if role in ("user", "assistant", "system", "developer"):
            out += [f"## {role}", ""]
            text = text_of(m.get("content")).strip()
            if text:
                out += [text, ""]
            for call in m.get("toolCalls") or []:
                fn = call.get("function") or {}
                out += [f"**Tool call `{one_line(fn.get('name')) or '?'}`**", "",
                        fence(pretty_args(fn.get("arguments")), "json"), ""]
                result = results.get(call.get("id"))
                if result is not None:
                    shown.add(call.get("id"))
                    label = "Tool error" if result.get("error") else "Tool result"
                    body = text_of(result.get("content"))
                    if result.get("error"):
                        body = (body + "\n" if body else "") + str(result.get("error"))
                    out += [f"<details><summary>{label}</summary>", "", fence(body), "", "</details>", ""]
                else:
                    out += ["(no result recorded)", ""]
            continue
        out += [f"## {one_line(role)}", "", fence(json.dumps(m, indent=2, ensure_ascii=False), "json"), ""]
    return out


def render_session(rec):
    lines = []
    if rec.get("deleted_at"):
        lines += [f"Deleted by the participant at {when(rec['deleted_at'])}.", ""]
    tags = [one_line(t) for t in rec.get("tags") or []]
    lines += [
        f"# {title_of(rec)}",
        "",
        f"- Session: `{one_line(rec.get('id'))}`",
        f"- Created: {when(rec.get('created_at'))}",
        f"- Updated: {when(rec.get('updated_at'))}",
        f"- Tags: {', '.join(tags) or '-'}",
        f"- State: {state_of(rec)}",
        f"- Runs: {runs_summary(rec)}",
        "",
    ]
    lines += render_messages(rec.get("messages") or [])
    return "\n".join(lines)


def load_sessions(sessions_dir):
    """[(file name, record)] for every readable <id>.json, and the names of unreadable ones."""
    records, unreadable = [], []
    for name in sorted(os.listdir(sessions_dir)):
        path = os.path.join(sessions_dir, name)
        if not name.endswith(".json") or not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                rec = json.load(f)
        except (OSError, ValueError):
            unreadable.append(name)
            continue
        if not isinstance(rec, dict) or not isinstance(rec.get("messages", []), list):
            unreadable.append(name)
            continue
        records.append((name, rec))
    records.sort(key=lambda nr: (str(nr[1].get("created_at") or ""), str(nr[1].get("id") or ""), nr[0]))
    return records, unreadable


def count_lines(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return sum(1 for line in f if line.strip())


def same(a, b):
    return os.path.exists(a) and os.path.exists(b) and os.path.samefile(a, b)


def main(argv):
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    bundle, run_dir = argv
    if os.path.isdir(os.path.join(bundle, "sessions")):
        src = os.path.join(bundle, "sessions")
    elif os.path.isdir(os.path.join(bundle, "agui-sessions")):
        src = os.path.join(bundle, "agui-sessions")
    else:
        print(f"{bundle}: neither sessions/ nor agui-sessions/", file=sys.stderr)
        return 2
    os.makedirs(run_dir, exist_ok=True)
    raw_dir = os.path.join(run_dir, "agui-sessions")
    if not same(src, raw_dir):
        os.makedirs(raw_dir, exist_ok=True)
        for name in sorted(os.listdir(src)):
            if os.path.isfile(os.path.join(src, name)):
                shutil.copyfile(os.path.join(src, name), os.path.join(raw_dir, name))
    log_src = os.path.join(bundle, "agent-runs.jsonl")
    log_dst = os.path.join(run_dir, "agent-runs.jsonl")
    has_log = os.path.isfile(log_src)
    if has_log and not same(log_src, log_dst):
        shutil.copyfile(log_src, log_dst)

    records, unreadable = load_sessions(raw_dir)
    rows = []
    for i, (name, rec) in enumerate(records, 1):
        stem = f"{i:02d}-{slug(rec.get('title'))}"
        write(os.path.join(run_dir, "chats", stem + ".md"), render_session(rec))
        shutil.copyfile(os.path.join(raw_dir, name), os.path.join(run_dir, "chats", stem + ".json"))
        link = re.sub(r"([\[\]|\\])", r"\\\1", title_of(rec))
        tags = ", ".join(one_line(t) for t in rec.get("tags") or []) or "-"
        rows.append(f"| {i:02d} | [{link}](chats/{stem}.md) | {tags} | {when(rec.get('created_at'))} "
                    f"| {len(rec.get('runs') or [])} | {state_of(rec)} |")

    index = [
        f"# Run {os.path.basename(os.path.abspath(run_dir))}",
        "",
        "- Frontend: agui (CopilotKit chat). The AG-UI frontend has no run report.",
        "- Parameters and canary record: [run.yml](run.yml), canaries.json",
        "- Session files as stored (hidden and deleted included): [agui-sessions/](agui-sessions/)",
    ]
    if has_log:
        index.append(f"- Agent run log: [agent-runs.jsonl](agent-runs.jsonl), {count_lines(log_src)} runs")
    else:
        index.append("- Agent run log: none (no run reached the agent)")
    index.append("")
    if rows:
        index += ["| # | Session | Tags | Created | Runs | State |", "|---|---|---|---|---|---|", *rows, ""]
    else:
        index += ["No session was recorded.", ""]
    if unreadable:
        index += ["Unreadable session files (kept in agui-sessions/): "
                  + ", ".join(f"`{n}`" for n in unreadable), ""]
    write(os.path.join(run_dir, "index.md"), "\n".join(index))
    hidden = sum(1 for _, r in records if r.get("hidden") and not r.get("deleted_at"))
    deleted = sum(1 for _, r in records if r.get("deleted_at"))
    print(f"{len(records)} sessions ({hidden} hidden, {deleted} deleted), "
          f"{'run log' if has_log else 'no run log'}, {len(unreadable)} unreadable")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
````

- [ ] **Step 5: Run the tests to see them pass**

Run: `chmod 0755 platform/ansible/roles/run_archive/files/write_agui_run.py && uv run --with pytest pytest platform/dev/tests -q`
Expected: all pass (15 new). `uv run --with pytest pytest platform/dev/tests -k agui_run -q`: 8 passed.

- [ ] **Step 6: Write the export**: replace `platform/ansible/roles/run_archive/tasks/export.yml` with

````yaml
---
# On the SPE VM: export the frontend's chats and fetch them to the controller.
# openwebui: chats, notes and tags as {{ spe_output_dir }}/archive-bundle.json.
# agui: every session file (hidden and deleted included) and the agent's run log
# as {{ spe_output_dir }}/archive-bundle-agui.tar.gz, after stopping chat-ui and
# then the agent so that no run is in progress or unsaved; both are started again.
- name: Export OpenWebUI
  when: spe_frontend == 'openwebui'
  block:
    - name: Exporter script
      ansible.builtin.copy:
        src: export_openwebui.py
        dest: /tmp/spe-export-openwebui.py
        mode: "0700"

    - name: Export OpenWebUI
      ansible.builtin.command:
        argv:
          - python3
          - /tmp/spe-export-openwebui.py
          - "http://127.0.0.1:{{ spe_webui_local_port }}"
          - /tmp/spe-openwebui-export.json
          - "{{ spe_frontend_dir }}/run_report.md"
      environment:
        WEBUI_EMAIL: "{{ spe_webui_admin_email if spe_webui_auth else '' }}"
        WEBUI_PASSWORD: "{{ spe_webui_admin_password if spe_webui_auth else '' }}"
      register: export_out
      changed_when: false

    - name: Fetch the export
      ansible.builtin.fetch:
        src: /tmp/spe-openwebui-export.json
        dest: "{{ spe_output_dir }}/archive-bundle.json"
        flat: true

    - name: Remove the export from the VM
      ansible.builtin.file:
        path: "{{ item }}"
        state: absent
      loop: [/tmp/spe-export-openwebui.py, /tmp/spe-openwebui-export.json]

- name: Export the AG-UI chat sessions and the agent's run log
  when: spe_frontend == 'agui'
  vars:
    agui_compose: [docker, compose, -p, spe-frontend, -f, "{{ spe_frontend_dir }}/docker-compose.yml"]
  block:
    - name: The chat-ui container exists (stopping a missing one would succeed silently)
      ansible.builtin.command:
        argv: "{{ agui_compose + ['ps', '-a', '-q', 'chat-ui'] }}"
      register: agui_chat_ui
      changed_when: false
      failed_when: agui_chat_ui.rc != 0 or agui_chat_ui.stdout | trim | length == 0

    - name: Export directory on the VM
      ansible.builtin.tempfile:
        state: directory
        prefix: spe-agui-export-
      register: agui_export_dir

    - name: Barrier, copy and pack; the containers are started again whatever happens
      block:
        - name: Stop the chat UI first (on SIGTERM it cancels, saves every run in progress and exits)
          ansible.builtin.command:
            argv: "{{ agui_compose + ['stop', '-t', '30', 'chat-ui'] }}"
          changed_when: true

        - name: Then stop the agent (it has seen its last request and closed its run log)
          ansible.builtin.command:
            argv: "{{ agui_compose + ['stop', '-t', '30', 'agent'] }}"
          changed_when: true

        - name: Copy the session files (hidden and deleted included)
          ansible.builtin.command:
            argv: "{{ agui_compose + ['cp', 'chat-ui:/data/sessions', agui_export_dir.path ~ '/sessions'] }}"
          changed_when: false

        - name: Copy the agent's run log (absent until a run has reached the agent)
          ansible.builtin.command:
            argv: "{{ agui_compose + ['cp', 'agent:/var/lib/spe-agent/runs.jsonl', agui_export_dir.path ~ '/agent-runs.jsonl'] }}"
          register: agui_run_log
          changed_when: false
          failed_when: agui_run_log.rc != 0 and 'Could not find the file' not in agui_run_log.stderr

        - name: Pack the bundle
          ansible.builtin.command:
            argv: [tar, -czf, /tmp/spe-agui-export.tar.gz, -C, "{{ agui_export_dir.path }}", .]
          changed_when: true
      always:
        - name: Start the agent and the chat UI again
          ansible.builtin.command:
            argv: "{{ agui_compose + ['start', 'agent', 'chat-ui'] }}"
          changed_when: true

    - name: Fetch the bundle
      ansible.builtin.fetch:
        src: /tmp/spe-agui-export.tar.gz
        dest: "{{ spe_output_dir }}/archive-bundle-agui.tar.gz"
        flat: true

    - name: Remove the export from the VM
      ansible.builtin.file:
        path: "{{ item }}"
        state: absent
      loop: ["{{ agui_export_dir.path }}", /tmp/spe-agui-export.tar.gz]
````

- [ ] **Step 7: Write the run directory**: in `platform/ansible/roles/run_archive/tasks/write.yml`, replace
  everything from `- name: Overview without a chat export (agui frontend, or no frontend)` to the end with

````yaml
- name: AG-UI chat sessions bundle
  ansible.builtin.stat:
    path: "{{ spe_output_dir }}/archive-bundle-agui.tar.gz"
  register: agui_bundle

- name: Unpack the AG-UI bundle
  when: agui_bundle.stat.exists
  block:
    - name: Bundle directory
      ansible.builtin.file:
        path: "{{ spe_output_dir }}/archive-bundle-agui"
        state: directory
        mode: "0700"

    - name: Unpack
      ansible.builtin.command:
        argv: [tar, -xzf, "{{ spe_output_dir }}/archive-bundle-agui.tar.gz", -C, "{{ spe_output_dir }}/archive-bundle-agui"]
      changed_when: true

- name: AG-UI sessions and the agent's run log
  ansible.builtin.command:
    argv:
      - "{{ ansible_playbook_python }}"
      - "{{ role_path }}/files/write_agui_run.py"
      - "{{ spe_output_dir }}/archive-bundle-agui"
      - "{{ spe_run_dir }}"
  when: agui_bundle.stat.exists
  register: write_agui_out
  changed_when: true

- name: Overview without a chat export (no frontend)
  ansible.builtin.copy:
    dest: "{{ spe_run_dir }}/index.md"
    mode: "0644"
    content: |
      # Run {{ spe_run_dir | basename }}

      - Archived: {{ spe_archive_time }}
      - Frontend: {{ spe_frontend }}; no chat export (no frontend ran on this instance)
      - Parameters and canary record: [run.yml](run.yml), canaries.json
  when: not ((spe_output_dir ~ '/archive-bundle.json') is file) and not agui_bundle.stat.exists

- name: Remove the staged exports
  ansible.builtin.file:
    path: "{{ item }}"
    state: absent
  loop:
    - "{{ spe_output_dir }}/archive-bundle.json"
    - "{{ spe_output_dir }}/archive-bundle-agui.tar.gz"
    - "{{ spe_output_dir }}/archive-bundle-agui"

- name: Archived
  ansible.builtin.debug:
    msg: "Run saved to {{ spe_run_dir }} ({{ write_out.stdout | default(write_agui_out.stdout | default('no chat export')) }})"
````

- [ ] **Step 8: The playbook.** In `platform/ansible/playbooks/archive.yml`: the header comment's first lines become

```yaml
# Save one instance's run to <spe_runs_root>/<UTC time>_<instance>/: parameters,
# canary record and the frontend's chats: with openwebui chats and notes (incl.
# the run report), with agui every chat session (hidden and deleted included)
# and the agent's run log. Works for OpenStack and existing-VM instances.
```

the play `- name: Export OpenWebUI from the instance` becomes `- name: Export the frontend's chats`, and its include's
`when: spe_frontend == 'openwebui'` becomes `when: spe_frontend in ['openwebui', 'agui']`.

- [ ] **Step 9: Check the playbook and exercise the export against a throwaway compose project** (never against
  `spe-frontend`: that is the dev VM's live stack)

```bash
cd platform/ansible && ansible-playbook playbooks/archive.yml --syntax-check -e spe_instance=x </dev/null
T=$(mktemp -d /var/tmp/agui-export-XXXX); mkdir -p $T/frontend $T/out
cat > $T/frontend/docker-compose.yml <<'EOF'
name: spe-frontend-scratch
services:
  chat-ui:
    image: node:24-slim
    init: true
    command: ["sh", "-c", "mkdir -p /data/sessions && echo '{}' > /data/sessions/6f1c0d2e-1a2b-4c3d-8e4f-0a1b2c3d4e5f.json && exec sleep 600"]
    volumes: [chat-sessions:/data]
  agent:
    image: node:24-slim
    init: true
    command: ["sh", "-c", "mkdir -p /var/lib/spe-agent && exec sleep 600"]
    volumes: [agent-runs:/var/lib/spe-agent]
volumes: {chat-sessions: {}, agent-runs: {}}
EOF
cat > $T/play.yml <<'EOF'
- hosts: localhost
  connection: local
  gather_facts: false
  tasks:
    - ansible.builtin.include_role: {name: run_archive, tasks_from: export}
EOF
C="-p spe-frontend-scratch -f $T/frontend/docker-compose.yml"
run() { ANSIBLE_ROLES_PATH=$PWD/roles ansible-playbook -i localhost, $T/play.yml -e spe_frontend=agui \
  -e spe_frontend_dir=$T/frontend -e spe_output_dir=$T/out \
  -e "{\"agui_compose\": [\"docker\",\"compose\",\"-p\",\"spe-frontend-scratch\",\"-f\",\"$T/frontend/docker-compose.yml\"]}" </dev/null; }
docker compose $C up -d && sleep 2
run && tar -tzf $T/out/archive-bundle-agui.tar.gz                       # ./sessions/<id>.json, no run log
docker compose $C exec -T agent sh -c 'echo "{}" > /var/lib/spe-agent/runs.jsonl'
run && tar -tzf $T/out/archive-bundle-agui.tar.gz | grep agent-runs.jsonl  # now with the run log
docker compose $C ps --format '{{.Service}} {{.State}}'                   # both running again
docker compose $C rm -sf chat-ui && ! run                                 # fails at "The chat-ui container exists"
docker compose $C down -v; rm -rf $T
```

Expected: syntax check passes; the first two runs end `failed=0` with the bundle contents shown; both services
`running` afterwards; the third run fails at its first task, so nothing is stopped.

- [ ] **Step 10: Commit**

```bash
git add platform/ansible/roles/run_archive/files/write_run.py platform/ansible/roles/run_archive/files/write_agui_run.py \
  platform/ansible/roles/run_archive/tasks/export.yml platform/ansible/roles/run_archive/tasks/write.yml \
  platform/ansible/playbooks/archive.yml platform/dev/tests/test_write_agui_run.py
git commit -s -m "run_archive: export and render the AG-UI chat sessions" \
  -m "Stop chat-ui (it saves every run in progress), then the agent; copy the session files and the run log; start both again. write_agui_run.py renders them like an Open WebUI run; fence() is now one backtick longer than any run inside, which also fixes write_run.py."
```

### Task 5: stale docs, the early output on the dev VM, the PR and the handoff

**Files:** Modify: `README.md`, `docs/getting-started.md`, `docs/specs/2026-10-15-agui-frontend-design.md`,
`CHAT/README.md`, `CHAT/app/page.tsx` (comment only if still stale), `platform/coder/README.md`,
`platform/coder/template/testbeds/agui.yml`, `platform/coder/template/main.tf`,
`platform/ansible/inventory/group_vars/all.yml`, `platform/ansible/README.md`, `AGENTS.md`, `docs/knowledge/README.md`,
the plan README's slices table. Create: `docs/knowledge/agui-chat-sessions.md`,
`docs/superpowers/plans/2026-10-29-agui-chat-sessions/evidence/slice-2/` (screenshots, `index.md`, one chat),
`docs/superpowers/plans/2026-10-29-agui-chat-sessions/handoffs/<UTC>-slice-2-done.md`.

**Interfaces:** Consumes: everything above. Produces: the early output for the user.

**Decisions:** spec §3 and §4 *every current text* lists; 9, 11, 12 and 14 shown to the user.

- [ ] **Step 1: Find every stale text** (the list should match the edits below; anything else it prints is
  rewritten too)

```bash
git grep -n -i -E "reload starts a new|not archived|no persistence|server-side sessions|Exports OpenWebUI|no notes or tags|Chats are not archived|archiving its chats|chats \+ report|archived on stop\)|OpenWebUI chats and notes|keeps no history" -- . ':!docs/superpowers' ':!.methodology'
```

- [ ] **Step 2: Rewrite them** (upstream-clean: none of these names a fork-only file)

- `README.md`, the paragraph ending "A reload starts a new conversation.": replace that sentence with "Each
  conversation is a session in the left sidebar; a reload reopens the one in the URL."
- `docs/getting-started.md`: "card; a reload starts a new conversation." → "card. Conversations are kept as
  sessions in the left sidebar (rename, pin, tag, hide, delete) and archived with the run." In §2 *Private
  configuration*, after the *Run log* row add:

  ```markdown
  | **Chat sessions** | Every AG-UI conversation: messages, tool calls and results, titles and tags | Written by the chat UI | On the VM, volume `spe-frontend_chat-sessions`; in the run directory `agui-sessions/`, `chats/` and `agent-runs.jsonl` | **No**: contain canaries |
  ```

- `docs/specs/2026-10-15-agui-frontend-design.md`: in §2 drop ", server-side sessions" from the non-goals and add
  the sentence "Chat sessions were added later: `platform/agui/copilotkit-chat/README.md`, *Sessions*."; in §6
  replace "no persistence (a reload starts a new chat)" with "sessions are kept on the server
  (`platform/agui/copilotkit-chat/README.md`, *Sessions*)".
- `CHAT/README.md`: the `app/page.tsx` bullet's "No persistence: a reload starts a new conversation." becomes "A
  sidebar (`app/sidebar.tsx`) lists the sessions; the open one is in the URL (`?session=<id>`)." Append to slice 1's
  *Sessions* section:

```markdown
**Sidebar.** `app/sidebar.tsx`: *New chat*, the sessions (pinned first, then newest; hidden ones are left out),
and a `⋯` menu per row: rename (Enter saves, Esc cancels), pin, tags (suggests the tags in use; × removes one), hide,
delete (after a confirmation; the file is kept and archived). Titles and tags are rendered as text. The page only
reads sessions and changes metadata (`lib/client.ts`); it never writes messages.

**Opening a session** sets its messages on the agent and then mounts a new `CopilotChat` (`key={id}`) inside
`CopilotChatConfigurationProvider` with `threadId={id}` and `hasExplicitThreadId={false}`. With an explicit
`threadId`, CopilotChat 1.79 asks the runtime to *connect* to the thread and first clears the agent's messages on a
thread it has not connected to; the runtime's in-memory runner only knows threads this process ran. A malformed,
unknown or deleted `?session=` starts a new session and drops the parameter.

**Shutdown.** `instrumentation.ts` installs `lib/shutdown.ts` on `SIGTERM`: new runs are refused, every run in
progress is cancelled and saved as `cancelled`, the session queue drains (at most 25 s) and the process exits. The
image sets `NEXT_MANUAL_SIG_HANDLE=true` so that Next.js's own handler does not exit first; `node
scripts/check-shutdown.mjs [--image <tag>]` checks it. `archive.yml` relies on it: it stops `chat-ui`, then `agent`,
before copying the sessions.
```

- `platform/coder/README.md`: the `run_archive` row → "Exports the frontend's chats (Open WebUI, or the AG-UI chat
  sessions and the agent's run log) and writes the run directory"; step 4 → "Document as you go (the run report is
  Open WebUI only; in the AG-UI chat, tag sessions in the sidebar's `⋯` menu):"; after the table's
  `openwebui-export.json` row add

  ```markdown
  | `chats/NN-<title>.md`, `.json` (agui) | Each AG-UI session, readable, and as stored; a deleted one opens with "Deleted by the participant at …" |
  | `agui-sessions/` (agui) | Every session file as stored, hidden and deleted included (re-render with `write_agui_run.py`) |
  | `agent-runs.jsonl` (agui) | The agent's run log: every run, tool calls and results |
  ```

  The *Re-render an
  old run* row gains "; AG-UI: `platform/ansible/roles/run_archive/files/write_agui_run.py <run> <run>`"; the
  *Known limitations* entry "The `agui` frontend is not archived. …" becomes "**The `agui` frontend has no run
  report.** Its sessions (with tags) and the agent's run log are archived; there is no "Run report" note as in
  Open WebUI."
- `platform/coder/template/testbeds/agui.yml`: "Chats are not archived yet." → "Its chat sessions and run log are
  archived on stop."
- `platform/coder/template/main.tf`, the `frontend` parameter's description: "openwebui: Open WebUI runs the agent
  loop (chats and the run report are archived on stop). agui: our own Pydantic AI agent with a CopilotKit chat
  (platform/agui; its chat sessions and run log are archived on stop)."
- `platform/ansible/inventory/group_vars/all.yml`, *Run archive* comment: "saves the OpenWebUI chats and notes" →
  "saves the frontend's chats (OpenWebUI chats and notes, or the AG-UI chat sessions and the agent's run log)".
- `platform/ansible/README.md`: the `archive.yml` command comment "save chats + report now" stays; in *Run archive*
  replace "For the `agui` frontend the chat UI keeps no history and the agent's run log stays in its volume, so only
  the parameters and the canary record are archived today." with "For the `agui` frontend it stops `chat-ui` (which
  saves every run in progress) and then the agent, copies every session file (hidden and deleted included) and the
  agent's run log, starts both again, and renders the sessions like Open WebUI chats (`write_agui_run.py`)."
- `AGENTS.md`, *AG-UI agent frontend*: "Not done yet: archiving its chats on stop (the run archive exports Open WebUI
  only) and a run-report equivalent in the CopilotKit chat." → "Chat sessions (sidebar, archive) are being added by
  the *AG-UI chat sessions* track. Not done yet: a run-report equivalent in the CopilotKit chat."

Run the grep of step 1 again. Expected: no line except history (handoffs, clarifications) and the spec's own
problem statement.

- [ ] **Step 3: Knowledge note.** `docs/knowledge/agui-chat-sessions.md`, with the symptom and the fix for: (1)
  CopilotChat with an explicit `threadId` clears messages set before the mount (fix: ruling 2's provider); (2)
  `[role=alert]` also matches Next.js's route announcer (use `.spe-error`); (3) `node --test lib/` fails with
  `MODULE_NOT_FOUND` in Node 24 (use `node --test` or a glob); (4) `docker compose stop <service>` exits 0 when the
  service has no container (check `ps -a -q` first); (5) Next.js's `SIGTERM` handler exits before a detached run is
  saved (`NEXT_MANUAL_SIG_HANDLE=true`). One index line in `docs/knowledge/README.md`:

  ```markdown
  - [agui-chat-sessions.md](agui-chat-sessions.md) — CopilotChat explicit threadId clears restored messages; `[role=alert]` matches Next's route announcer; `node --test lib/` MODULE_NOT_FOUND; `docker compose stop` of a missing service exits 0; Next's SIGTERM handler vs a detached run.
  ```

- [ ] **Step 4: The full Playwright run with screenshots**

```bash
E=docs/superpowers/plans/2026-10-29-agui-chat-sessions/evidence/slice-2
rm -rf /var/tmp/spe-e2e-sessions && mkdir -p $E
(cd platform/agui/copilotkit-chat && npm ci && npm test && npm run build)
python3 platform/dev/e2e/sessions.py --shots $E --sessions /var/tmp/spe-e2e-sessions
ls /var/tmp/spe-e2e-sessions $E
```

Expected: every `ok - …` line; three files in `/var/tmp/spe-e2e-sessions`; `$E` holds `01-three-sessions.png`,
`02-row-menu.png`, `03-tags.png`, `04-delete-confirmation.png`, `05-final-reopened.png`. Look at each screenshot
(Read tool) before going on; a layout problem is fixed in `globals.css` and the run repeated.

- [ ] **Step 5: Put the slice on the dev VM** (no cloud instance created or destroyed, no model call:
  `spe_agui_smoke` is false in `dev-local.yml`). `M` is the main checkout, `W` this worktree.

```bash
M=/workspace/biohackathon/biohackathon/elixir-biohackathon-2026-test; W=$(git rev-parse --show-toplevel)
git -C $M status --short && git -C $M log --oneline -1          # clean, on main, slice 1 merged
cd $M/platform/ansible && ansible-playbook playbooks/create.yml -e @instances/dev-local.yml \
  -e spe_agui_source_dir=$W/platform/agui </dev/null
docker exec spe-frontend-chat-ui-1 ls -la /data/sessions          # the new volume, owned by node, empty
docker cp -a /var/tmp/spe-e2e-sessions/. spe-frontend-chat-ui-1:/data/sessions/   # -a: keep uid 1000 (node)
curl -s http://127.0.0.1:3000/api/sessions                         # two entries: the pinned one and the hidden one
```

Then load `http://127.0.0.1:3000/` once with Playwright (`page.goto`, `page.screenshot(path=$E/06-dev-vm.png)`,
full page, viewport 1280×800; no message sent, so no model call) and look at it.

- [ ] **Step 6: `archive.yml` on the dev VM** (ruling 5: from the worktree, with the main checkout's instance file
  and output)

```bash
cd $W/platform/ansible && ansible-playbook playbooks/archive.yml \
  -e @$M/platform/ansible/instances/dev-local.yml -e spe_output_root=$M/platform/ansible/output </dev/null
R=$(ls -d /data-share/runs/*_dev-local | tail -1); ls -R $R | head -30; cat $R/index.md
docker compose -p spe-frontend ps --format '{{.Service}} {{.State}}'; curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3000/api/sessions
```

Expected: the play ends `failed=0`; `$R` has `run.yml`, `index.md` (three rows: active pinned with `exfil, dns`,
hidden, deleted with its time), `chats/01-…` to `03-…` (`.md` and `.json`), `agui-sessions/` with three files
(`ls $R/agui-sessions | wc -l` equals `ls /var/tmp/spe-e2e-sessions | wc -l`); all three services `running`; the
session API answers 200. **This step checks the sessions only.** No run reaches the dev VM's agent here (the
sessions were copied in, and a run would be a paid model call), so whether `$R` has `agent-runs.jsonl` depends only
on the VM's history and is not checked. The run log's copy is checked in slice 3, task 4, against the fake agent in
the compose stack (`fake-agent.compose.yml`, no model calls); here it was exercised only against task 4's
throwaway compose project (step 9).
Copy `$R/index.md` and `$R/chats/01-*.md` into `$E/` (fake-agent content only; never copy `agent-runs.jsonl`,
`run.yml` or anything else from `$R`: they hold the instance's canaries).

- [ ] **Step 7: Tests, commit, push, PR**

```bash
(cd platform/agui/copilotkit-chat && npm ci && npm test && npm run build)
uv run --with pytest pytest platform/dev/tests -q
python3 .methodology/shared/sync-agents.py --check
git fetch origin && git diff -U0 origin/main...HEAD -- platform/agui/copilotkit-chat platform/ansible platform/dev \
  ':!*.md' | grep '^+' | grep -v '^+++' \
  | grep -E 'spec §|[Dd]ecision [0-9]|Review Focus|slice [0-9]|clarification [0-9]'
```

Expected: the suites pass, `sync-agents.py --check` is clean, and the last command prints nothing: no line this
slice added to code (`lib/`, `app/`, `scripts/`, `instrumentation.ts`, the Dockerfile, Ansible, Python) cites the
spec, a decision, a Review Focus item, a slice or a clarification; such files are upstream-bound, so a comment
states the behaviour instead. A hit is rewritten and committed before the PR is marked ready.

Update the plan README's slices table: row 2/3's *Status* → `merged #<this PR>` (set in the PR's last commit, so it
is true once the PR is merged; the number is known from the draft claim); and the `AGENTS.md` *Current work* line of
the track: its `**Next: …**` part → `**Next: slice 3/3** \`impl/agui-chat-sessions-3-complete\``, the handoff pointer
(`ls docs/superpowers/plans/2026-10-29-agui-chat-sessions/handoffs | tail -1`) unchanged. Neither names the PR as
open or in review. Write the handoff
`handoffs/<YYYY-MM-DDTHHMMZ>-slice-2-done.md`: what was built, the commands run and their results, the six
rulings above as *decision, why, cost if wrong* plus any made while implementing, links to `evidence/slice-2/`, the
run directory's path, a line saying that the dev-VM `archive.yml` run checked `sessions/` (`agui-sessions/`, the
chats, `index.md`) only and that the run log's copy is checked in slice 3, task 4 (the fake-agent compose run), and
slice 3's start (`ls handoffs | tail -1`, then `slice-3-complete.md`).

```bash
git add README.md docs/getting-started.md docs/specs/2026-10-15-agui-frontend-design.md \
  platform/agui/copilotkit-chat/README.md platform/coder/README.md platform/coder/template/testbeds/agui.yml \
  platform/coder/template/main.tf platform/ansible/inventory/group_vars/all.yml platform/ansible/README.md AGENTS.md \
  docs/knowledge/agui-chat-sessions.md docs/knowledge/README.md \
  docs/superpowers/plans/2026-10-29-agui-chat-sessions/README.md \
  docs/superpowers/plans/2026-10-29-agui-chat-sessions/evidence/slice-2 \
  docs/superpowers/plans/2026-10-29-agui-chat-sessions/handoffs
git commit -s -m "AG-UI chat sessions: docs, early output evidence, slice 2 handoff"
git push origin impl/agui-chat-sessions-2-sidebar
```

The PR (`gh pr create --repo thodkatz/elixir-biohackathon-2026-test --base main`, title "AG-UI chat sessions:
sidebar, row menu, archive export (2/3)"; or `gh pr ready` if the draft claim exists) has this body, with the
`blob/<branch>/…?raw=true` links to the committed screenshots:

```markdown
**Early output: please look at both before slice 3 builds on them** (spec, *Early output*).

1. **The sidebar** (decision 9): is this the Open WebUI subset you want? [three sessions](…01-three-sessions.png),
   [row menu](…02-row-menu.png), [tags](…03-tags.png), [delete confirmation](…04-delete-confirmation.png),
   [reopened after reload](…05-final-reopened.png), [on the dev VM](…06-dev-vm.png).
   Search, tag filter, date groups, *Show hidden*, the chat header and disabled controls during a run come in slice 3.
2. **The run directory** (decision 12): is this what you would read when analysing what participants tried?
   `archive.yml` on the dev VM gave `<run dir>`; its `index.md`:
   <paste $E/index.md in a fenced block>
   and `chats/01-….md`:
   <paste it in a fenced block>

Either can change the layout, the row menu or what the archive renders; slice 3 does not wait for this look.

**Ran:** `npm test`, `npm run build`, `node scripts/check-shutdown.mjs` (standalone and image), `pytest
platform/dev/tests`, `python3 platform/dev/e2e/sessions.py`, `archive.yml` on the dev VM, `sync-agents.py --check`.
DCO: every commit signed off. Rulings: in the handoff.
```

Then the local review round (`AGENTS.md`, *Reviewers*), the findings addressed, and stop: the user merges.

### Task 6: the row menu's behaviour, Open WebUI's way (clarification 4)

Added 2026-11-02 at the user's request, run after task 4 and before task 5 (task 5's screenshots, docs and PR show
the result). Implements spec §3 *Row menu* and the row bullets of *Layout* as amended by clarification 4. The
first sidebar left the menu and the rename or tag editor open after a click elsewhere, ignored Escape outside an
input, never returned focus, and rendered the menu inline in the list.

**Files:** Modify `CHAT/app/sidebar.tsx`, `CHAT/app/page.tsx`, `CHAT/app/globals.css` (structure only; task 7
does the look), `platform/dev/e2e/sessions.py` (`check_menu`). Create, if it helps testing, small pure helpers in
`CHAT/lib/` (e.g. tag suggestions) with `node --test` cases beside them. No new dependencies.

- [ ] **Step 1: One owner for menu state.** `Sidebar` holds which row has the menu open and what that row is
  doing (`menu`, `rename`, `tags`, `delete`); rows do not keep their own mode. Opening a session (any row),
  *New chat*, collapsing the sidebar, or opening another row's menu ends whatever is open. At most one row is
  ever in a non-idle state.
- [ ] **Step 2: The popover.** The menu floats over the list, anchored under the row's `⋯` (flip upward when
  it would leave the viewport), and does not move other rows. It closes on a `pointerdown` outside the menu and
  its trigger, on Escape (wherever focus is inside the sidebar or menu), and on choosing an item. Closing
  returns focus to the `⋯` that opened it. `role="menu"` items are reachable with ArrowUp/ArrowDown/Home/End;
  the first item is focused when the menu opens from the keyboard. Item order: *Rename*, *Pin*/*Unpin*,
  *Tags*, *Hide*/*Unhide*, separator, *Delete*.
- [ ] **Step 3: Rename** replaces the row's title in place (same height, no layout shift), focused with the text
  selected; also started by double-clicking the row's title. Enter saves if changed, Escape cancels, and a
  click outside the row saves if changed and ends the edit (Open WebUI's blur rule). The `⋯` is not clickable
  while renaming. IME composition (`isComposing`) never saves or cancels. An empty or unchanged title saves
  nothing.
- [ ] **Step 4: Tags** opens Open WebUI's tag editor inside the popover: the session's tags as pills, each with
  a ×; below them an input with placeholder "Add a tag…". Typing shows up to 8 suggestions from the tags in use
  on other sessions (case-insensitive substring, excluding tags already on this session); a click on a
  suggestion or Enter adds the tag. Invalid input (spec §1 rules) shows the server's 400 as a one-line error
  under the input and keeps the text. Escape closes the suggestions first, then the editor. A click outside
  closes the editor without adding the typed text (Open WebUI's tag blur rule).
- [ ] **Step 5: Delete** opens a modal dialog (centred, backdrop, `role="alertdialog"`, focus on *Cancel*):
  title "Delete chat?", text "This removes it from your list. It is kept in the run archive.", buttons
  *Cancel* and *Delete*. Escape or the backdrop cancels; focus returns to the row's `⋯` (or, if the deleted
  row was open, the page behaves as today after a delete).
- [ ] **Step 6: Browser checks** in `platform/dev/e2e/sessions.py`, extending `check_menu` (or a new
  `check_focus` run after it), against `fake_agent.py` as the existing checks do. Each of these, asserted on
  the DOM: (a) Rename → click another row: the edit ends, the new title is saved (a reload shows it), the other
  session opens; (b) Rename → Escape: unchanged; (c) menu open → click empty sidebar space: closed; (d) menu
  open → Escape: closed and `document.activeElement` is that row's `⋯`; (e) menu open on row A → click row B's
  `⋯`: exactly one menu, row B's; (f) menu open → *New chat*: closed; (g) Tags → type a prefix of an existing
  tag → its suggestion shows; Enter adds it; × removes it; click outside with typed text: nothing added;
  (h) Delete → Escape: dialog closed, row still listed; (i) ArrowDown moves focus through the items.
- [ ] **Step 7: Tests and commit.** `npm test` and `npm run build` in `CHAT`, the e2e script as the README says.
  Commit.

### Task 7: the look — Open WebUI's sidebar, a polished chat (clarification 4)

Run after task 6. Implements spec §3 *Look* and *Chat header* as amended by clarification 4. The reference is
Open WebUI's sidebar (the controller hands the implementer a design reference with its tokens and icon paths);
the bar is claude.ai and chatgpt.com: calm, dense, no stray borders, one accent at most.

**Files:** Modify `CHAT/app/globals.css`, `CHAT/app/sidebar.tsx`, `CHAT/app/page.tsx`, `CHAT/app/layout.tsx`;
add an icons module (inline SVG React components) under `CHAT/app/`; `CHAT/next.config.*` only to turn off the
dev-only indicator if it overlaps the sidebar. No new dependencies and no web fonts fetched at runtime (the
instance may have no internet): a system font stack.

- [ ] **Step 1: Tokens.** CSS custom properties on `:root` for Open WebUI's gray scale, text, border, hover,
  selected, menu, dialog and focus-ring colours, radii, shadows and the 200 ms menu transition; a
  `@media (prefers-color-scheme: dark)` block redefines them. No hex colour outside the token block.
- [ ] **Step 2: Sidebar.** Open WebUI's geometry: about 260 px, its background, *New chat* as a full-width
  row with a pencil-square icon, the collapse control as an icon button, a search-shaped area left for slice 3,
  rows of title only (single line, ellipsis, `⋯` on hover/focus/open row/menu open, selected and hover
  backgrounds, rounded), pinned rows under a small muted *Pinned* label, the bottom note muted and small. The
  popover menu, tag pills (Open WebUI's: the whole pill, with its always-visible ×, removes the tag on a click),
  suggestion list and dialog in Open WebUI's style, each menu item with its icon
  (pencil, pin/pin-slash, tag, eye-slash/eye, trash); *Delete* in a muted red. Visible `:focus-visible` rings.
- [ ] **Step 3: Header and composer.** Drop the banner sentence. A quiet header row (no border; a fade under it
  when the chat scrolls is fine) with the open session's title, *New chat* before the first run, truncated.
  Set CopilotKit's `labels`: `chatDisclaimerText` "SPE agent · runs inside the secure processing environment ·
  every tool call is shown" and `chatInputPlaceholder` "Message the SPE agent". (Renaming from the header and its
  `⋯` are slice 3.)
- [ ] **Step 4: The CopilotKit chat** in the same palette, light and dark: message bubbles, composer, tool
  cards (`run_command` and the others) and buttons, targeted through `data-testid`/stable classes the audit
  lists rather than generated `cpk:` utility strings where possible. The chat column stays centred and
  readable (about 768 px).
- [ ] **Step 5: Screenshots** at 1280×800, light and dark (Playwright `color_scheme`): the page with four
  sessions (one pinned), the open menu, a rename, the tag editor with a suggestion, the delete dialog. Save
  them under the plan's `evidence/` directory, named `ui-<mode>-<what>.png`, and compare them yourself against
  the reference before reporting; say in the report what still differs from Open WebUI and why.
- [ ] **Step 6: Tests and commit.** `npm test`, `npm run build`, the e2e script (task 6's checks must still
  pass: class names they use stay). Commit.

### Task 8: slice 3's tasks follow clarification 4

Docs only, run after task 7. Rewrite the task text of [slice 3](slice-3-complete.md) task 1 (search, tag filter)
and task 2 (chat header) so they implement spec §3 as amended by clarification 4: the tag filter is Open WebUI's
`tag:<name>` search syntax with a suggestion list when `tag:` is typed (several terms must all match; the rest
of the query filters titles), not tag chips; the header is task 7's title row made renamable in place with the
same `⋯` menu as the rows; rows carry no tags; the class names and components slice 2 now has (from task 6 and
7's code) replace the ones the old text assumed. Keep the tasks' structure, steps and acceptance checks
otherwise. Commit.
