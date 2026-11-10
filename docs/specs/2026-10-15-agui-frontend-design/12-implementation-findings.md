## 12. Implementation findings (2026-10-15)

Recorded during implementation on `agent-agui-frontend-impl`; the plan's progress file
(`docs/plans/2026-10-15-agui-frontend-progress.md`) holds every ruling with its cost if
wrong. *Verified* means observed in this work; *pending* means not yet observed.

**Versions verified** (installed and exercised): pydantic-ai-slim 2.56.0 (ag-ui,
anthropic, openai extras), ag-ui-protocol 0.1.22, FastAPI 0.143.2, uvicorn 0.54.0,
httpx 0.28.1, Python 3.13 image (3.12 for local tests); Next.js 16.4.1, React 19.3.1,
@copilotkit/react-core and @copilotkit/runtime 1.79.0, @ag-ui/client 1.0.2, Node 24,
TypeScript 6.0.3 (7.x has no JavaScript API, which `next build`'s type check needs);
promptfoo 0.124.1; open-terminal 0.12.4
(`sha256:ca1d60e70f4eca35db62b80b128fffc7d7c156298167aac25cc4982947bcea5b`); Open WebUI
v0.11.3 source at `2a960a5`. `claude-haiku-5-5` exists and is active (model-info
endpoint, no model call).

**§11 settled:**

- *0, passwordless sudo*: works on the development VM (`sudo -n true`).
- *2, prompt combination*: Open WebUI appends the terminal's `/system` prompt to the
  system message (`utils/middleware.py`, `add_or_update_system_message(..., append=True)`)
  and later prepends the model's prompt (`routers/openai.py`,
  `apply_system_prompt_to_body`), joined with `\n`. The agent sends
  `system_prompt.txt` + `\n` + the sandbox prompt. Client-sent system messages are
  stripped (`manage_system_prompt='server'`).
- *3, parameter flattening*: mirrored from `convert_openapi_to_tool_payload`; the
  differences are listed in `agent/README.md` (no `display_file` inline/page
  parameters, non-JSON responses as UTF-8 text rather than base64 data URIs,
  redirects not followed, sandbox key redacted from responses, 30 s deadline).
- *4, Pydantic AI APIs*: `AGUIAdapter.from_request`/`run_stream`/`streaming_response`
  (`dispatch_request` equivalent, wrapped so each event can be logged and `RUN_ERROR`
  sanitised), `Tool.from_schema`, `FunctionModel(stream_function=…)` for offline
  tests, `UsageLimits(request_limit, tool_calls_limit, total_tokens_limit)`.
  `AgentRunResult.usage` is a property.
- *5, CopilotKit v2*: `CopilotKitProvider`, `CopilotChat`, `useDefaultRenderTool`
  (`@copilotkit/react-core/v2`); `CopilotRuntime` + `createCopilotRuntimeHandler`
  (`@copilotkit/runtime/v2`), multi-route mode under `basePath: /api/copilotkit`,
  hence the catch-all route; `HttpAgent({url, headers})` carries the bearer key.
- *6, read-only root filesystem*: verified for both images. The agent needs a `/tmp`
  tmpfs and its run-log volume (uid 10001); the chat UI (Next.js standalone output,
  `node server.js`) needs `/tmp` and `/app/.next/cache` as tmpfs (uid 1000). Both run
  with `cap_drop: ALL` and `no-new-privileges`.
- *1, de.NBI hosts*: settled 2026-10-16, see the results at the end of this section.

**Behaviour added or made precise:**

- *Readiness*: `/healthz` and authenticated `/agent` answer 503 until the sandbox's
  OpenAPI is read (retry 1 s doubling to 30 s); afterwards the sandbox is probed every
  30 s and a failure returns the service to 503 until rediscovery, so a sandbox
  restart needs no agent restart (verified with the real image). Auth is checked
  before readiness.
- *Errors*: `RUN_ERROR` messages have the three key values redacted and are cut to 500
  characters; a run ends with exactly one terminal event.
- *Run log*: built from the AG-UI events sent to the client; durations run from the end
  of a call's arguments to its result; failed runs have no usage.
- *Telemetry*: off in the chat UI image (`NEXT_TELEMETRY_DISABLED`,
  `COPILOTKIT_TELEMETRY_DISABLED`, `DO_NOT_TRACK`), which CopilotKit's runtime also
  reports to its browser client; the documented promptfoo run disables its telemetry.
- *Deployment*: build contexts are the git-tracked files only; images are tagged by a
  content hash; a label carries the hash of the bind-mounted config so a change to it
  alone recreates the agent; the openwebui role now removes orphans so switching works
  in both directions; the key-boundary check asks the sandbox's own `/execute` API.

**Observed results (development VM, `anthropic`/`claude-haiku-5-5`):** create,
converge without rebuild or restart, `verify.yml`, frontend switching both ways, the
key boundary and the browser UI against a scripted agent — all without model calls.
Real-model results (dev VM, `anthropic`/`claude-haiku-5-5`, 2026-10-15, approved by the user): the AG-UI smoke run through `verify.yml -e spe_agui_smoke=true` passed (`run_command`, `get_process_status`, `run_command`, `RUN_FINISHED`; `failed=0`); a two-turn chat in the browser showed 3 then 1 tool cards and answered the second turn from the first turn's history, no error, no key in any response; the promptfoo starter suite passed 3 of 3 with no key in the report. All 8 runs together: 27 model requests, 244,099 input and 5,035 output tokens (about $0.03 at the spec's prices).
On de.NBI (2026-10-16, `agent-service-1`, `openai_compatible`/`qwen3.8-27b`, beside an untouched
Open WebUI stack): create, converge, the no-cost checks, the smoke run, a two-turn chat and
the promptfoo suite (3/3) passed. §11 item 1: `spe-ga4gh-api-2` is the controller with a
hand-run stack; `spe-ga4gh-api` refuses the de.NBI key; `agent-service-1` meets §7.0, with
`/data-share` there being the mounted Manila share, so `spe_data_root` points elsewhere.

### Leaving a running chat (2026-11-08 to 2026-11-09)

Decisions 26 and 40–44, built in the fork's PRs #57, #58 and #62 (clarification 28). *Verified* against
`platform/dev/fake_agent.py` in the browser (`platform/dev/e2e/sessions.py`, scenarios `leave-running`, `stop`,
`rejoin`, `running-marks` and `all`) and by `npm test`; no model call.

**Versions verified:** Next.js 16.4.5, React 19.3.1, CopilotKit 1.84.1 (`@copilotkit/react-core/v2`,
`@copilotkit/runtime/v2`), `@ag-ui/client` 1.0.2. 1.84.1's `useAgent` takes the thread-scoped props §6 names
(`agentId`, `runtimeAgentId`, `threadId`, all required), and `CopilotKitCore.connectAgent({ agent })` rejoins.

**Decision 42 rejoins live.** A throwaway page checked it before the chat changed: two private agents stream in
two sessions at once; an ordinary open, a remount and a send show each message id once with no `connect`
request (the stop point did not apply); stop in a rejoined chat journals `cancelled`. What it found and the
chat now does:

- *`connectAgent` clears the messages first*: on a freshly loaded page every rejoin counts as a restore and
  calls `agent.setMessages([])` before connecting, so with no merge the first list React drew was empty. The
  merge (`lib/rejoin.ts`) therefore runs on every message change from a subscriber made before `connectAgent`
  is called, and once after it ends (also when it fails, so a failed connect leaves the history), setting the
  messages only when the result differs. A merge from the replay's first event on failed the check.
- *The run in progress* is the set of ids the replay names since the last `RUN_STARTED`: each event's
  `messageId` and `parentMessageId`, a `TOOL_CALL_START`'s `toolCallId` (`@ag-ui/client` makes the assistant
  message with that id when no parent is named), and every message id of a `MESSAGES_SNAPSHOT` (the recorder
  sends one right after `RUN_STARTED`, §13). The runtime replays past runs first, then the running run whole from
  its own `RUN_STARTED`. A history message whose id is in that set is replaced by the agent's copy, the agent's
  messages the history lacks are appended, and every other replayed copy is dropped.
- *An ordering race the merge rests on*: the event pipeline works on its own copy of the agent's messages,
  taken when it starts, and writes it back on every event; the merge on `connectAgent`'s clearing must land
  after that copy, or the replay's `TEXT_MESSAGE_START` appends to the history's partial copy and repeats its
  text. It never did (the check and every `rejoin` run), but it rests on how many awaits CopilotKit makes
  between the clearing and the copy, which an upgrade can change. `rejoin` detects it: the streamed slow steps
  rise between ticks and end on exactly the run's steps, each once.
- *Cost*: one `GET /api/copilotkit/info` and one `POST /api/copilotkit/agent/spe/connect` per rejoin; none on an
  ordinary open or a remount.
- *A rejoin's end*: `connectAgent` fires the agent's run callbacks (`onRunInitialized`, `onRunFinalized`) like a
  run, so a rejoined run ends through the same watch as any run, reconciled until the list shows the session no
  longer `running` (§6 *Refresh*). A list without the session (deleted meanwhile) ends it with no error bar: the
  holder is dropped as for any session gone from the list.

**Behaviour made precise:**

- *A chat reopened mid-run*: `@ag-ui/client` copies a run's subscribers when the run starts, so a `CopilotChat`
  mounted on an agent already running froze. The holder forwards its agent's message changes, and the page
  redraws the open chat on each while it was mounted mid-run.
- *Only a session's latest run ends it*: an older run's end, whose list came back after a newer run started,
  no longer drops the session from the page's streaming set (which unmounted a holder mid-run on a switch).
- *List fetches apply in the order they started*: a session once listed and then missing from a list is gone
  for good in the page (a New chat's first run is never dropped before it is listed), so a list fetched before
  a newer one and answering after it is dropped as stale; it would otherwise have swapped an open New chat for
  another at its run's end.
- *Run errors* reach the error bar through each session's holder only; `CopilotChat`'s `onError` skips the run
  error codes, so the open session's error shows once. A left session's errors, its save failure included,
  carry its title (clarification 28).
- *The running mark*: the row's spinner keeps turning under `prefers-reduced-motion: reduce`, being the only
  motion that says another session's run goes on. The chat header has no running mark (its `⋯` is always
  shown), only the Delete rule.
- *Refresh*: the list is also fetched while the page is hidden if the polling holds (§6 says nothing against
  it); a failed fetch's error goes once a list loads again; only the first load waits for the runtime
  (clarification 28).
