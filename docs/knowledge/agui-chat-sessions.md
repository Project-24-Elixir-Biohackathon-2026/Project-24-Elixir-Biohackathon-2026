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
*container* needs the explicit `ps -a -q` check first. `run_archive`'s `write_agui_run.py` export task does
this for `chat-ui`.

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
it refuses new runs, cancels every run in progress (saved `cancelled`), drains the session queue (at most 25s)
and then exits. `node scripts/check-shutdown.mjs` checks this end to end, both standalone and in the built
image.
