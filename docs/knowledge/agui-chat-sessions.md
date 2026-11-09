# AG-UI chat sessions: five gotchas from slice 2

## 1. CopilotChat with an explicit `threadId` clears messages set before the mount

**Symptom.** `<CopilotChat threadId={id}>` right after `agent.setMessages([...])`: the chat opens empty
instead of showing the restored history.

**Cause.** CopilotChat's thread effect (`@copilotkit/react-core/dist/copilotkit-DQvE96lZ.mjs`, `function
CopilotChat`, the effect on `resolvedThreadId`) treats a different thread id as a *fresh restore*: it calls
`copilotkit.connectAgent({agent})`, which (`RunHandler.connectAgent`, `@copilotkit/core/dist/index.mjs`
~line 3744) does `await agent.detachActiveRun()` then `agent.setMessages([])`, then asks the runtime's
`/connect` (`runtime/dist/v2/runtime/handlers/handle-connect.mjs` → `runner/in-memory.mjs` `connect()`). That
in-memory runner only replays threads this server process itself ran (`historicRuns`); nothing survives a
restart, so an explicit `threadId` would also make a restored session go empty after a redeploy.

**Fix.** Set the messages on the agent, then mount a *new* `CopilotChat` (`key={id}` forces the remount) inside
`<CopilotChatConfigurationProvider agentId="spe" threadId={id} hasExplicitThreadId={false}>`. Without an
explicit thread, CopilotChat sets `agent.threadId` directly and makes no connect request; it only clears
messages on a thread change *inside one already-mounted instance*, never on first mount. `app/page.tsx`'s
`open()` does this.

## 2. `[role=alert]` also matches Next.js's route announcer

**Symptom.** A Playwright check for an error banner with `page.locator('[role=alert]')` finds an element on
every page load, even with no error on screen.

**Cause.** Next.js injects its own route announcer (for accessibility, to announce client-side navigations)
with `role="alert"`; it is present on every page, not just error states.

**Fix.** Give the error banner its own class and check that instead: `.spe-error`. `platform/dev/e2e/sessions.py`
and `app/page.tsx` do this.

## 3. `node --test lib/` fails with `MODULE_NOT_FOUND` on Node 24

Already recorded in [node-test-directory.md](node-test-directory.md): a directory argument makes Node try to
load `lib` as one module. Pass a quoted glob instead, `node --test 'lib/*.test.ts'` (what `npm test` runs).
Confirmed again against this slice's `lib/shutdown.test.ts`, `lib/client.test.ts`, `lib/session-url.test.ts`.

## 4. `docker compose stop <service>` exits 0 when that service has no container

**Symptom.** `run_archive`'s export task stops `chat-ui` and `agent` in turn; if one of them was never
started (no container for that service in the compose project), `docker compose stop <service>` still
returns rc 0 — a missing service is silently not an error, so a later step that assumes the stop worked (e.g.
expecting the container to exist for `docker compose cp`) fails confusingly instead.

**Fix.** Check `docker compose ps -a -q <service>` is non-empty before relying on the stop, or before trying
to copy from the container. `docker compose cp` itself does fail clearly on a missing *file* inside a stopped
container (`Could not find the file … in container`, rc 1) — that part needs no extra check — but a missing
*container* needs the explicit `ps -a -q` check first. `run_archive`'s export task (`tasks/export.yml`)
does this for `chat-ui`.

**It also exits 0 when the container did not stop cleanly.** A process that exits 1 on `SIGTERM`, or one Docker
kills after `-t` (exit 137), still leaves `docker compose stop` at rc 0. Read the exit code afterwards:
`docker compose -p spe-frontend ps -a --format '{{.Service}} {{.ExitCode}}' chat-ui agent` (inside an Ansible
expression, quote it as a plain string literal: a nested `{{ '{{…}}' }}` is a Jinja syntax error). A container
already stopped before keeps its old exit code, so compare only services that were running
(`ps --status running --services`).

## 5. Next.js's own `SIGTERM` handler exits before a detached run can be saved

**Symptom.** `docker compose stop chat-ui` (or `stop -t 30`) can kill the chat UI mid-save: a run that has no
browser attached (the AG-UI in-memory runner keeps it going after the tab closes) is cancelled by the
container runtime before `lib/shutdown.ts` finishes draining it.

**Cause.** `next/dist/server/lib/start-server.js` (used by the standalone `server.js`) installs its own
`SIGTERM` handler unless `NEXT_MANUAL_SIG_HANDLE` is set: it closes the HTTP server (waiting only for open
*responses*) and then calls `process.exit(143)` itself — before any handler the app code adds gets to finish
an async drain, since a detached run holds no HTTP response open for Next.js to wait on.

**Fix.** Set `NEXT_MANUAL_SIG_HANDLE=true` in the image so Next.js installs no handler of its own, and let
`lib/shutdown.ts`'s `installShutdown()` (registered from `instrumentation.ts`) be the only `SIGTERM` listener:
it refuses new runs, cancels every run in progress (each ends `cancelled` in its journal), drains the session queue (at most 25s)
and then exits. `node scripts/check-shutdown.mjs` checks this end to end, both standalone and in the built
image.

## 6. Clicking "New chat" right after `page.goto()` can be silently dropped

**Symptom.** `platform/dev/e2e/sessions.py`'s `check_stop`, called right after `page.goto(BASE + "/")` with no
other check in between, sends its message but `agent.isRunning` never flips (in the page of that time, which disabled *New chat*
during a run, it stayed enabled) and no run is ever recorded, even though the button visibly exists and the click reports success.

**Cause.** A fresh `page.goto()` return (the `load` event) does not mean the React app has hydrated yet. A
server-rendered *New chat* button exists in the DOM before its `onClick` is attached; a click landing in that
window does nothing (no second `startNew()` fires — confirmed by logging every `startNew()` call). Once
hydrated, the same click behaves normally. When `check_stop` runs later in the "all" scenario, the page it
reuses is already hydrated from an earlier `expect(...)` on the same page, so the race never shows there.

**Fix.** Every button that starts an action (New chat in both views, a row's open and ⋯ menu, the header's
actions) is now `disabled` until a `ready` flag goes true, owned once in `app/page.tsx` and passed down:
`useHydrated()` (`app/use-hydrated.ts`, a `useEffect` that runs only on the client, after hydration) **and**
`useAgent`'s `isReady`. Hydration alone turned out not to be enough: the first-load effect that calls
`startNew()`/`open()` is itself gated on `isReady`, so a New chat click that landed after hydration but before
`isReady` (no longer dropped, just early) would call `startNew()` itself and mount the chat ahead of that
effect — found by running the standalone `stop` scenario ten times in a row after fixing hydration alone, which
failed every time. Playwright's click already waits for "enabled", so no caller needs a stand-in wait before
one any more; `check_stop`, `two_turn` and `slow_loop` in `sessions.py` all rely on this now instead. The
textarea's own hydration-implying wait (`expect(get_by_test_id("copilot-chat-textarea")).to_be_visible(...)`)
stays where it precedes typing into the
textarea itself: that element is separately self-gated (mounted only once a session is open), not covered by a
disabled attribute on a button.

A later review (PR #11's final review, M4) found one more, much smaller sub-frame window of the same shape:
`isReady` flipping commits a render with the buttons enabled, and the first-load effect is a passive effect
that only runs after that commit, so a click in between still calls `startNew()` ahead of the effect, the same
way a click between hydration and `isReady` used to. `ready` now also requires `active !== null`
(`app/page.tsx`), which the first-load effect's every path (`open()`'s success, its not-found/error fallback to
`startNew()`, and the no-parameter `startNew()`) sets by calling `select()` before returning — so this cannot
leave `ready` false once the agent is actually ready, including with an empty session list. Not reproduced by a
human or by Playwright (whose stability check, two animation frames, outlasts it); closed anyway because the
fix is the same one-line shape as the bug it extends.

## 7. A stop clicked very soon after a run starts used to record it `failed`, not `cancelled`

**Symptom (now fixed at the source, kept here for how it was found).** `check_stop`'s flow (type a "slow"
message, wait for *New chat* to disable, click the composer's stop button) occasionally (roughly 1 run in
4–6, worse on a cold server) ended with the session's last run `status: "failed"` instead of `"cancelled"`,
with `started_at`/`ended_at` only ~50 ms apart — far too short for the fake agent's first streamed chunk
(1 s in).

**Cause.** `@ag-ui/client` 1.0.2 only turns an aborted fetch into `RUN_ERROR{code:"abort"}` inside its SSE
parser, which subscribes once the agent's response HEADERS frame has arrived. A stop clicked before that —
and the sidebar's *New chat* disables as soon as the client locally starts the run (`onRunInitialized`),
well before the agent's response headers can arrive — reaches `lib/recorder.ts`'s stream `error:` callback
as a raw `AbortError` instead of a `RUN_ERROR` event, and that callback always recorded `"failed"`. Not,
as first suspected, a race with the recorder's own admission: waiting for the outgoing
`POST .../agent/spe/run` request to be *issued* (`page.expect_request`) did not help, because the request
being sent is not the same as its response headers having arrived. Any incidental delay before the stop
click (even `r.shot("during-run")` writing a screenshot) happened to move it past the delay-free test
agent's near-instant headers, hiding the bug rather than fixing it.

**Fix.** `lib/recorder.ts`'s stream `error:` handler now checks `error.name === "AbortError"` and records
`cancelled` for that case, same as the post-headers `RUN_ERROR{code:"abort"}` path (spec clarification 1,
`docs/superpowers/specs/2026-10-29-agui-chat-sessions-design.md`). `lib/recorder.test.ts` pins it with
`lib/test-agent.ts`'s new `headerDelayMs`, which holds the test agent's response headers back so the test
can abort before them reliably. `check_stop` needs no wait any more: 20/20 standalone `--scenario stop`
runs passed without one.
