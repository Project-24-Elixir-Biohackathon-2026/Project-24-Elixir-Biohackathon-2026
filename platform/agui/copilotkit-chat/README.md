# SPE chat UI

Next.js 16.4.1 + CopilotKit 1.79.0 (v2 API), a thin client for the SPE agent.

- `app/api/copilotkit/[[...slug]]/route.ts`: `CopilotRuntime` (`@copilotkit/runtime/v2`) in
  multi-route mode (`/api/copilotkit/info`, `/api/copilotkit/agent/spe/run`, …) via
  `createCopilotRuntimeHandler({ basePath: "/api/copilotkit" })`, with one agent `spe`: an
  `HttpAgent` (`@ag-ui/client` 1.0.2) for `AGENT_URL` sending `Authorization: Bearer
  $AGENT_API_KEY`. Both variables are server-side only (not `NEXT_PUBLIC_*`) and read on the
  first request, so the build needs neither.
- `app/page.tsx`: `CopilotChat` (`@copilotkit/react-core/v2`) beside the sidebar; every tool call is
  a collapsible card (`useDefaultRenderTool`) with name, status, arguments and the first 40 lines
  or 4000 characters of the result, rendered as text. Run errors appear in a bar above the chat. A
  sidebar (`app/sidebar.tsx`) lists the sessions; the open one is in the URL (`?session=<id>`).
- `lib/`: chat sessions on the server, plain TypeScript that `node --test` runs without Next.js
  (see *Sessions*). `app/api/sessions/` wraps `lib/api.ts`.

Telemetry is off in the image: `NEXT_TELEMETRY_DISABLED=1`, `COPILOTKIT_TELEMETRY_DISABLED=true`,
`DO_NOT_TRACK=1` (the runtime's `/info` then tells the browser client the same).

## Sessions

Each conversation is a session: one JSON file, `/data/sessions/<id>.json`, on the `chat-sessions`
volume (mounted at `/data`; the image creates `/data/sessions` owned by `node`). `<id>` is the
AG-UI thread id, a lower-case UUID v4; nothing else ever names a file. The file holds the AG-UI
`messages` as the last run ended with them, one `runs[]` entry per run (`completed`, `failed` or
`cancelled`), and the metadata `title`, `tags`, `pinned`, `hidden` and `deleted_at`.

- `lib/recorder.ts` records every run on the `spe` agent from its AG-UI stream (AG-UI middleware,
  attached with `agent.use()`), whatever its outcome; one run per session at a time. It stores
  messages and run metadata only, never request headers or the agent key.
- `lib/sessions.ts` writes atomically (temporary file, then rename) and one session at a time,
  through a queue on `globalThis` that every route bundle shares. The chat UI is one Node process;
  a second one would need a file lock.
- `/api/sessions`: `GET` lists metadata (newest first, at most 1000, deleted ones left out);
  `GET`/`PATCH`/`DELETE /api/sessions/{id}` read one, change `title`, `tags`, `pinned` or `hidden`
  (bodies up to 16 KB), or mark it deleted. A deleted session's file is kept. There is no `POST`:
  a session exists once its first run is recorded. Errors are `{"error": "<message>"}`.

The files hold whatever participants typed and tools returned, canary values included: treat the
volume like the agent's run log.

**Sidebar.** `app/sidebar.tsx`, in Open WebUI's layout and colours (light and dark follow the system): *New chat*,
the sessions by title only, grouped and filtered by `lib/sidebar-view.ts` (below), and a button that collapses the
sidebar. Each row has a `⋯` menu (`app/row-menu.tsx`): rename (also a double-click on the
title; Enter or a click outside saves, Escape cancels), pin, tags, hide, and delete after a confirmation
(`app/delete-dialog.tsx`; the file is kept and archived). The menu closes on a click outside, Escape or a choice.
Tags are shown and edited only in the menu's tag editor (`app/tag-editor.tsx`): it suggests the tags in use (arrow
keys pick one, Enter adds it or the typed text), and a click on a tag removes it. Titles and tags are rendered as
text. The page only reads sessions and changes metadata (`lib/client.ts`); it never writes messages. The note that
this is the SPE agent and every tool call is shown sits under the composer (CopilotKit's `chatDisclaimerText`).

The sidebar's search filters by title (case-insensitive) and, as in Open WebUI, by `tag:<name>` terms (a
session must have every one; typing `tag:` suggests the tags in use), lists pinned sessions first and then
*Today*, *Yesterday*, *Previous 7 days* and *Older* by last change, and shows hidden sessions only with *Show
hidden*. The chat header shows the open session's title, renamable in place, and the same `⋯` menu as its
row. While a run is in progress, switching session and *New chat* are disabled; after a run the list is
fetched until it shows that run (up to 5 retries, 500 ms apart), else the error bar says the session could not
be saved. `platform/dev/e2e/sessions.py` drives all of it in a browser against the scripted agent.

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

```bash
npm ci && npm run build                       # type-checks too
# against the scripted agent (no LLM): in ../pydantic-ai-agent
#   uv run --group dev python ../../dev/fake_agent.py --port 18100 --key TEST_KEY
# SPE_SESSIONS_DIR (default /data/sessions) must be an existing, writable directory, or every save fails
SPE_SESSIONS_DIR=$(mktemp -d) AGENT_URL=http://127.0.0.1:18100/agent AGENT_API_KEY=TEST_KEY PORT=3000 NEXT_MANUAL_SIG_HANDLE=true \
  node .next/standalone/server.js
#   (copy .next/static to .next/standalone/.next/static first; the Dockerfile does)
docker build -t spe-chat-ui .                 # node:24-slim, user node, port 3000
npm test                                      # lib/*.test.ts with node --test (no model, no network)
node scripts/check-built-server.mjs           # after npm run build: the built server against fake_agent.py
```

The image runs with a read-only root filesystem when `/tmp` and `/app/.next/cache` are tmpfs
(uid 1000), with `cap_drop: ALL` and `no-new-privileges`.

TypeScript is pinned to 6.0.3: TypeScript 7 has no JavaScript API, which `next build` uses for its
type check.
