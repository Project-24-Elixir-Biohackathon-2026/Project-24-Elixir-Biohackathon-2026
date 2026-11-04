# SPE chat UI

Next.js 16.4.1 + CopilotKit 1.79.0 (v2 API), a thin client for the SPE agent.

- `app/api/copilotkit/[[...slug]]/route.ts`: `CopilotRuntime` (`@copilotkit/runtime/v2`) in
  multi-route mode (`/api/copilotkit/info`, `/api/copilotkit/agent/spe/run`, …) via
  `createCopilotRuntimeHandler({ basePath: "/api/copilotkit" })`, with one agent `spe`: an
  `HttpAgent` (`@ag-ui/client` 1.0.2) for `AGENT_URL` sending `Authorization: Bearer
  $AGENT_API_KEY`. Both variables are server-side only (not `NEXT_PUBLIC_*`) and read on the
  first request, so the build needs neither.
- `app/page.tsx`: `CopilotChat` (`@copilotkit/react-core/v2`) beside the sidebar; every tool call is
  a collapsible card (`useDefaultRenderTool`, `app/tool-calls.tsx`, after Open WebUI's `ToolCallDisplay`):
  a status icon and "Executing `<name>`…" / "View Result from `<name>`" / "`<name>` failed", then the
  arguments as rows (`run_command`'s as a `$ <command>` line) and the first 40 lines or 4000 characters
  of the result, rendered as text (`lib/tool-card.ts`). Several calls in one assistant message share a
  group header. Run errors appear in a bar above the chat. A
  sidebar (`app/sidebar.tsx`) lists the sessions; the open one is in the URL (`?session=<id>`).
- `lib/`: chat sessions on the server, plain TypeScript that `node --test` runs without Next.js
  (see *Sessions*). `app/api/sessions/` wraps `lib/api.ts`.

Telemetry is off in the image: `NEXT_TELEMETRY_DISABLED=1`, `COPILOTKIT_TELEMETRY_DISABLED=true`,
`DO_NOT_TRACK=1` (the runtime's `/info` then tells the browser client the same).

## Sessions

Each conversation is a session with one append-only journal, `/data/sessions/<id>.jsonl`, on the
`chat-sessions` volume (mounted at `/data`; the image creates `/data/sessions` owned by `node`). `<id>` is the
AG-UI thread id, a lower-case UUID v4; nothing else ever names a file. One JSON line per step: `created`,
then per run `run_start` (the new user message, what the client sent that was not used, the request's
`tools`, `context`, `state`, `forwardedProps`, and for a command run its `command`), every AG-UI `event` the
agent sent, `run_end` with the status (`completed`, `failed`, `cancelled`, `aborted`, `refused`); and `meta`
lines for `title`, `tags`, `pinned`, `hidden`, `deleted_at`. Nothing rewrites or truncates a journal. Files of
the earlier format (`<id>.json`) are neither read nor migrated.

- `lib/recorder.ts` is the run route's hook (AG-UI middleware, attached with `agent.use()`): the chat UI owns
  the history. From each request it takes only the new user message and sends the agent the journal's
  history; whatever else the client sent that differs is journaled as ignored (`fabricated`, `edited`,
  `deleted`, `system`) and, when there is any, the browser gets a `MESSAGES_SNAPSHOT` of what the agent saw.
  `run_start` is fsynced before the agent is called; a journal that cannot be written ends the run with
  "this session could not be saved". Runs on one session may overlap and become branches; the chat reopens
  on the branch of the run that ended last. It never stores request headers or the agent key. A run whose
  only new message is `/compact` or `/compact <focus>` is a command (`lib/command.ts`): journaled as
  `run_start.command` with no message, sent the history with `forwardedProps.spe_command`, refused when there
  is nothing to compact or the focus is over 1000 characters; an admitted one always sends the browser the
  snapshot.
- `lib/journal.ts` writes and parses the lines, `lib/rebuild.ts` rebuilds a conversation with
  `@ag-ui/client`'s own event handling, `lib/anchor.ts` compares the client's history with the journal.
- `lib/sessions.ts` appends one session at a time through a queue on `globalThis` that every route bundle
  shares, and serves the list from an index in memory (also on `globalThis`), built by one pass over the
  journals on first use and updated on every append. The chat UI is one Node process.
- `/api/sessions`: `GET` lists metadata (newest first, at most 1000, deleted ones left out);
  `GET`/`PATCH`/`DELETE /api/sessions/{id}` read one (its latest branch), change `title`, `tags`, `pinned` or
  `hidden` (bodies up to 16 KB; one `meta` line each), or mark it deleted. A deleted session's journal is
  kept. No route creates a session: one is listed once a run has added a message. `POST
  /api/sessions/{id}/title` asks the agent's `POST /title` (same `AGENT_URL` host and key) for a 2-4 word title
  from the first completed run's user message and answer, read from the journal, and appends it as a `meta`
  title only if the session has none (a rename, even one made while the model writes, wins); it answers the
  metadata, unchanged when nothing was written or the agent failed (logged). Errors are `{"error": "<message>"}`.

The journals hold whatever participants typed and tools returned, canary values included: treat the
volume like the agent's run log.

**Sidebar.** `app/sidebar.tsx`, in Open WebUI's layout and colours: *New chat*,
the sessions by title only, grouped and filtered by `lib/sidebar-view.ts` (below), a theme control in the
footer (System / Light / Dark), and a button that collapses the sidebar. Each row has a `⋯` menu
(`app/row-menu.tsx`): rename (also a double-click on the
title; Enter, Tab or a click outside saves, Escape cancels), pin, tags, hide, and delete after a confirmation
(`app/delete-dialog.tsx`; the journal is kept and archived). The menu closes on a click outside, Escape or a choice;
on a touch screen every row shows its `⋯`.
Tags are shown and edited only in the menu's tag editor (`app/tag-editor.tsx`): it suggests the tags in use (arrow
keys pick one, Enter adds it or the typed text), and a click on a tag removes it. Titles and tags are rendered as
text. The page only reads sessions and changes metadata (`lib/client.ts`); it never writes messages. The note that
this is the SPE agent and every tool call is shown sits under the composer (CopilotKit's `chatDisclaimerText`).

The sidebar's search filters by title (case-insensitive) and, as in Open WebUI, by `tag:<name>` terms (a
session must have every one; typing `tag:` suggests the tags in use), lists pinned sessions first and then
*Today*, *Yesterday*, *Previous 7 days* and *Older* by last change, and shows hidden sessions only with *Show
hidden*. The chat header shows the open session's title, renamable in place, and the same `⋯` menu as its
row; a New chat not yet recorded shows no title. A New chat's first finished run, once listed, makes one title
call: the row shows the first message until the model's title arrives. While a run is in progress, switching session and *New chat* are disabled; after a run the list is
fetched until it shows that run (up to 5 retries, 500 ms apart), else the error bar says the session could not
be saved. If the runtime is not ready within 15 s, the error bar says it is unreachable.
`platform/dev/e2e/sessions.py` drives all of it in a browser against the scripted agent.

**Opening a session** sets its messages on the agent and then mounts a new `CopilotChat` (`key={id}`) inside
`CopilotChatConfigurationProvider` with `threadId={id}` and `hasExplicitThreadId={false}`. With an explicit
`threadId`, CopilotChat 1.79 asks the runtime to *connect* to the thread and first clears the agent's messages on a
thread it has not connected to; the runtime's in-memory runner only knows threads this process ran. A malformed,
unknown or deleted `?session=` starts a new session and drops the parameter.

**Shutdown.** `instrumentation.ts` installs `lib/shutdown.ts` on `SIGTERM`: new runs are refused, every run in
progress is cancelled (its `run_end` says `cancelled`), the session queue drains (at most 25 s) and the process exits. The
image sets `NEXT_MANUAL_SIG_HANDLE=true` so that Next.js's own handler does not exit first; `node
scripts/check-shutdown.mjs [--image <tag>]` checks it. The final archive (`destroy.yml`, `spe_archive_final: true`)
relies on it: it stops `chat-ui`, then `agent`, before copying the journals; a plain `archive.yml` stops nothing.

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
