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
