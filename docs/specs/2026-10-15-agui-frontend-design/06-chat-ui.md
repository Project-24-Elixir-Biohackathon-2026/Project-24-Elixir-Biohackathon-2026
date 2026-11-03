## 6. The chat UI

- Next.js app, two parts:
  - `app/page.tsx`: full-screen `<CopilotChat>` wired to agent `spe`, with the sessions sidebar.
  - `app/api/copilotkit/[[...slug]]/route.ts` (catch-all; implementation
    finding, §12): `CopilotRuntime` (`@copilotkit/runtime/v2`)
    with `agents: { spe: new HttpAgent({ url: AGENT_URL, headers: { Authorization: … } }) }`
    (`@ag-ui/client`), and the run route's hook that keeps the conversation record (§13).
- **Tool calls are rendered** with `useDefaultRenderTool`
  (`@copilotkit/react-core/v2`, verified in CopilotKit docs 2026-10-15): one
  collapsible card per call showing the tool name, its arguments (for
  `run_command`, the command), status, and the first lines of the result.
- No secrets in the browser. The conversation is kept on the server, in `chat-ui`, which owns it (§13);
  the browser changes only a session's metadata.
- Exact package versions are pinned in `package-lock.json`; the image runs
  `next start` as a non-root user.

### Sessions

The chat has an Open WebUI-style sidebar of **sessions**: list, open, new, rename, search, pin, tags (add,
remove, filter), hide and delete. A session is one conversation, one AG-UI thread (its `threadId` is the
session id) and one journal (§13).

- **Storage.** Journals live in `/data/sessions/` on the named volume `chat-sessions`, mounted at `/data` in
  `chat-ui` (`roles/agui/templates/docker-compose.yml.j2`). The app runs as `node` (uid 1000) without the
  rights to fix ownership, so the image creates the directory: the Dockerfile runs
  `install -d -o node -g node -m 0700 /app/.next/cache /data /data/sessions`, and Docker copies it, with its owner, into the
  named volume when it is first mounted empty. The container keeps `read_only: true`, its tmpfs mounts
  (`/tmp`, `/app/.next/cache`), `cap_drop: ALL`, `no-new-privileges` and its limits.
- **Code.** The sessions code lives in `lib/` beside `app/`; the Dockerfile copies `lib/` into the build
  stage and `.dockerignore` admits it (but not `lib/*.test.ts`). `npm run build` in the checkout passes
  even when the image cannot resolve `lib/`, so the image build is part of the checks (§10).
- **Ids.** A session id is a canonical lower-case UUID (v4, as `crypto.randomUUID()` makes), chosen by the
  browser. The store refuses every other string before building a path, so no request input reaches the
  filesystem except as a validated UUID.
- **Metadata.** `title`, `tags`, `pinned`, `hidden` (changed by the browser) and `deleted_at` (set by
  `DELETE`). Each change appends a `meta` line to the journal (§13).
  - `title`: the first user message's text, whitespace collapsed, cut to 60 characters, until a `PATCH`
    sets one; `"Untitled"` if it has no text. A later run never changes a title the user set. Titles are at
    most 200 characters.
  - `tags`: each trimmed, lower-cased, matching `[a-z0-9._-]{1,32}`, at most 20, de-duplicated, kept in the
    order given. An invalid tag makes the whole `PATCH` fail with 400.
  - `updated_at` is the time of the journal's last line; the list is ordered by it, newest first.
- **Hidden** sessions leave the default list and are shown with *Show hidden*; they stay openable and
  editable. **Delete** is soft: `deleted_at` is set, the session is gone from every API answer and refused
  for new runs, and its journal is kept and archived (§14). A run already in progress is not cancelled and
  goes on being journaled.

### Session API

Routes under `app/api/sessions/`, beside `/api/copilotkit`. The browser changes metadata only; there is no
`POST`: a session exists once its first run has started (its first `run_start`, §13).

| Call | Answer |
|---|---|
| `GET /api/sessions` | `200`, a JSON list of metadata (`id`, `title`, `tags`, `pinned`, `hidden`, `created_at`, `updated_at`, and `last_run_at`: the last run's end, `null` before the first), deleted sessions left out, hidden ones included, newest `updated_at` first, at most 1000 |
| `GET /api/sessions/{id}` | `200` with `id`, `title`, `tags`, `pinned`, `hidden`, `created_at`, `updated_at` and `messages`: the tip's branch (§13); `404` if missing or deleted. `version`, `title_source` and `last_run_at` are no longer answered: the journal keeps neither of the first two, and the third is a list-only field (clarification 9) |
| `PATCH /api/sessions/{id}` | body: any of `title`, `tags`, `pinned`, `hidden`; `200` with the new metadata; `400` for an unknown key (`messages`, `runs` and `id` included), a wrong type or an invalid value (nothing changed); `404` if missing or deleted |
| `DELETE /api/sessions/{id}` | sets `deleted_at`; `204`; `404` if missing or already deleted |

The list is served from an index in memory, built at startup with one pass over the journals and updated
on every append (§13). An id that is not a UUID gets `400`. Bodies over 16 KB get `413`. Error bodies are
`{"error": "<generic message>"}` and never contain paths or stack traces; details go to the server log. No
route changes a message.

**No authentication of its own.** The chat UI has none: it is reached only through the SSH tunnel to
`127.0.0.1:{{ spe_agui_ui_port }}` or the Coder proxy, one participant per instance. The session API sits
behind the same boundary. If an instance ever serves several participants, sessions need an owner (out of
scope).

### The sidebar

Plain React and CSS in `app/` (no new dependencies); all session data is rendered as React text.

- **Look:** Open WebUI's sidebar and chat chrome, finished to the standard of claude.ai and chatgpt.com:
  its gray scale, type sizes, row and menu geometry and transitions, light and dark
  (`prefers-color-scheme`), Heroicons-style inline SVG icons; the CopilotKit chat restyled to the same
  palette.
- **Layout:** a left sidebar (about 260 px, collapsible) and the chat to its right. Top to bottom: *New
  chat*; a search box filtering by title (case-insensitive substring, in the browser), where Open WebUI's
  `tag:<name>` terms filter by tag (several must all match) and typing `tag:` suggests the tags in use;
  the list, pinned first, then grouped *Today*, *Yesterday*, *Previous 7 days*, *Older* by `updated_at`,
  each row with its title only (as in Open WebUI), the open one highlighted, `⋯` shown on hover, focus,
  the open row and the row whose menu is open (on a touch screen, `hover: none`, always); at the bottom a
  *Show hidden* toggle and the note "Deleted sessions are kept in the run archive."
- **Row menu (`⋯`):** a popover anchored to the button, one open at a time; it closes on a click outside,
  Escape, choosing an item, opening a session or *New chat*; Escape and a choice return focus to its `⋯` (a
  click outside leaves it where the click put it); arrow keys move between items. *Rename* (inline in the
  row, also by double-click; text selected; Enter, Tab or a click outside saves, Esc cancels), *Pin* /
  *Unpin*, *Tags* (Open WebUI's tag editor: the session's tags as pills, each removed by its ×, and an "Add
  a tag…" input whose suggestions are the tags in use; Enter adds), *Hide* / *Unhide*, *Delete* (a dialog
  "Delete chat?" with "This removes it from your list. It is kept in the run archive.", *Cancel* and
  *Delete*; Escape cancels, wherever focus is). The page-wide Escape handlers skip a key an earlier handler
  already took (`defaultPrevented`).
- **Chat header:** a quiet row with the session's title (*New chat* before the first run), renamable in
  place, and the same `⋯` menu. The note that this is the SPE agent and that every tool call is shown is
  the muted line under the composer.
- **Open session in the URL:** `?session=<id>`. Loading the page with it fetches the session; without it,
  or with an id that answers 404, the page starts a new session (and drops the parameter).
- **Opening a session:** `GET /api/sessions/{id}`, then CopilotChat's `threadId` set to the id and
  `agent.setMessages(messages)`; the tool cards render again from the stored tool-call messages. **New
  chat:** a fresh `crypto.randomUUID()` and an empty history; the session joins the list once its first
  run has started.
- **During a run** (the agent's `isRunning`), switching and *New chat* are disabled, so a run never ends
  in a session the participant has left. CopilotChat's stop button ends the run (recorded `cancelled`).
  This is a convenience: runs from two tabs on one session become two branches (§13), never an overwrite.
- **Refresh:** the list is fetched on load, after each run ends and after each metadata change; no polling.
  A run that ends with a terminal event or a stream error, the stop button's included, has its `run_end`
  written before that event is passed on to the browser, so the fetch after it finds the run. Only a run
  whose stream to the browser ends early (the connection dropped while the detached run goes on, §13) ends
  after the browser's run has ended, and so can land after that fetch: after a run ends, until the list
  shows the open session with a `last_run_at` not older than the run's start, the page fetches it again, up
  to 5 times at 500 ms. If it still does not, the error bar says "this session could not be saved".
- **Errors:** a failed API call shows in the existing error bar; the open chat is never cleared. A run
  refused by `chat-ui` (§13) shows its `RUN_ERROR` there. If the runtime is still not ready after 15 s, the
  bar says "The agent runtime is unreachable; reload the page.", and the message goes once it is ready.

### Security and limits

- **Isolation unchanged.** `chat-ui` gains only `/data`. The agent and sandbox cannot reach the volume
  (other containers; the sandbox is on `tools` only). The model supplies text, never a path.
- **No keys in the record.** Journals and the archive hold no request headers and no runtime
  configuration, so never the agent key (`AGENT_API_KEY`, the only secret `chat-ui` holds). Message content
  is stored unchanged, not redacted: whatever a participant pasted or a tool returned is kept, as in the
  run log. Tool results may contain canary values and dataset content, as Open WebUI's export does; the run
  directory's existing handling applies to the AG-UI files (§14).
- **Key scan as a detector.** The key check (§9) covers the volume: no file under `/data/sessions` contains
  the agent key, the LLM key or the sandbox key. The LLM and sandbox keys are not in `chat-ui`, so a hit
  there means one reached the conversation through the agent or a tool: the check fails and reports it,
  the record does not hide it.
- **Untrusted text.** Titles, tags and messages render as React text, never as HTML; the chat's own
  message rendering is unchanged. The archive fences tool arguments and results with a fence longer than
  any run of backticks inside (§14).
- **Input limits:** `PATCH` bodies ≤ 16 KB, titles ≤ 200 characters, tags as above, ids UUID-only, the list
  capped at 1000.
- **Size and failures.** No per-journal limit; each tool result is already capped by the agent's
  `tools.max_output_bytes`. A journal that cannot be written ends the run with "this session could not be
  saved" (§13).
- **Lifetime.** Only `destroy.yml` removes the volume, and only after `archive.yml` succeeded.
