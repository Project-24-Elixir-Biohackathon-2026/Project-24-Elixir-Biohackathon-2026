# SPE chat UI

Next.js and CopilotKit (v2 API), a thin client for the SPE agent. It owns the
conversation history: each session is an append-only journal on the server, and the
agent is sent that history, never the browser's.

```bash
npm ci && npm run build                       # type-checks too
npm test                                      # lib/*.test.ts with node --test, no model, no network
docker build -t spe-chat-ui .                 # node:26-slim, user node, port 3000
# the built server against the scripted agent:
#   (cd ../pydantic-ai-agent && uv run --group dev python ../../dev/fake_agent.py --port 18100 --key TEST_KEY)
SPE_SESSIONS_DIR=$(mktemp -d) AGENT_URL=http://127.0.0.1:18100/agent AGENT_API_KEY=TEST_KEY PORT=3000 NEXT_MANUAL_SIG_HANDLE=true \
  node .next/standalone/server.js             # copy .next/static to .next/standalone/.next/static first
node scripts/check-built-server.mjs           # the same, scripted
```

`AGENT_URL` and `AGENT_API_KEY` are server-side only and read on the first request.
Telemetry is off in the image. TypeScript stays at 6.x: `next build` uses its
JavaScript API, which TypeScript 7 does not have.

## Layout

| Path | What |
|---|---|
| `app/api/copilotkit/[[...slug]]/route.ts` | `CopilotRuntime` with one agent `spe`, an `HttpAgent` for `AGENT_URL` with the bearer key, and the session recorder attached |
| `app/api/sessions/` | The session API: list, read, patch metadata, delete, title |
| `app/page.tsx`, `app/sidebar.tsx`, `app/tool-calls.tsx` | The chat, the sidebar, the tool-call cards |
| `lib/` | Sessions on the server, plain TypeScript that `node --test` runs: `recorder.ts` (the run hook), `journal.ts`, `rebuild.ts`, `anchor.ts`, `sessions.ts`, `api.ts`, `export.ts`, `shutdown.ts` |
| `scripts/export-journals.ts` | The archive's exporter: journals to one Open WebUI-shaped bundle |
| `instrumentation.ts` | Installs the SIGTERM drain |

## Sessions

One journal per session, `/data/sessions/<id>.jsonl` on the `chat-sessions` volume;
`<id>` is the AG-UI thread id, a UUID v4. Lines: `created`, per run `run_start`
(the new user message, what the client sent that was not used, the request's other
fields), every AG-UI `event`, `run_end` with the status (`completed`, `failed`,
`cancelled`, `aborted`, `refused`), and `meta` lines for title, tags, pinned,
hidden, deleted. Nothing rewrites a journal.

- **The recorder** takes only the new user message from each request and sends the
  agent the journal's history. Whatever else the client sent that differs is
  journaled as ignored (`fabricated`, `edited`, `deleted`, `system`) and the browser
  gets a `MESSAGES_SNAPSHOT` of what the agent saw. `run_start` is fsynced before
  the agent is called. Runs on one session may overlap and become branches; the
  chat reopens on the branch of the run that ended last. A run whose only new
  message is `/compact` or `/compact <focus>` is a command: sent the history and
  `forwardedProps.spe_command`, refused when there is nothing to compact.
- **The session API**: `GET /api/sessions` (newest first, at most 1000, deleted
  left out); `GET`, `PATCH` (`title`, `tags`, `pinned`, `hidden`; bodies up to 16 KB)
  and `DELETE /api/sessions/{id}`; `POST /api/sessions/{id}/title` asks the agent for
  a title and keeps it only if the session has none. No route creates a session or
  changes a message.
- **The sidebar**: New chat, titles grouped by day, search by title and `tag:<name>`,
  pinned first, hidden behind *Show hidden*; a row menu with rename, pin, tags,
  hide, delete; the menu gives focus back to its `⋯` when it closes (after a click
  outside, only when the click left focus nowhere: `lib/menu.ts`, `refocusIfLost`).
  `?session=<id>` in the URL reopens a session, which starts at its newest content
  (`app/page.tsx`, `SCROLL_VIEW`).
- **Leaving a running chat**: each session the page shows or streams has a
  CopilotKit agent of its own (`spe-<id>` on thread `<id>`, routed to the runtime's
  `spe`), held by `app/session-agent.tsx` while it is needed (`lib/live-sessions.ts`).
  Switching session and New chat stay enabled during a run, and the run goes on in
  its session's agent; reopening that session shows it still streaming, with no
  fetch. Once the run ends the agent is dropped unless its session is open. Runs in
  several sessions may stream at once.
- **Shutdown**: on SIGTERM new runs are refused, runs in progress are cancelled and
  journaled, the queue drains within 25 s, the process exits. The image sets
  `NEXT_MANUAL_SIG_HANDLE=true` so Next.js does not exit first. The final archive
  relies on it.

The journals hold what participants typed and tools returned, canaries included:
treat the volume like the agent's run log. `platform/dev/e2e/sessions.py` drives
the sidebar in a browser against the scripted agent.
