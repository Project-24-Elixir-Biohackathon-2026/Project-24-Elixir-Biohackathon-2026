# SPE agent

A Pydantic AI pentest agent for one SPE instance, served over AG-UI. It holds the
LLM key and calls the open-terminal sandbox, where model-chosen commands run; it
runs no commands itself. Deployed by the `agui` Ansible role next to the sandbox and
the chat UI (`docs/specs/2026-10-15-agui-frontend-design.md`).

```bash
uv run --group dev pytest -q                   # offline tests: no LLM, no network
docker build -t spe-agent:dev .                # runs the same tests in its `test` stage
SPE_AGENT_CONFIG=agent.yaml SPE_AGENT_API_KEY=… SANDBOX_API_KEY=… ANTHROPIC_API_KEY=… \
  uv run python -m spe_agent                   # serves :8100
```

## Service

- `POST /agent`: AG-UI `RunAgentInput` in, server-sent events out, through
  `AGUIAdapter` (pydantic-ai-slim 2.56.0, `pydantic_ai/ui/_adapter.py`). Requires
  `Authorization: Bearer <SPE_AGENT_API_KEY>`; the key is checked before readiness, so
  an unauthenticated request always gets 401. A malformed body gets 422 without the
  input echoed back.
- `GET /healthz`: no auth, no LLM call. 200 `{"status": "ok", "tools": N}` once the
  sandbox's tools are discovered, else 503 with a reason.

**Readiness.** uvicorn starts at once. A background task fetches the sandbox's
`/openapi.json`, `/files/cwd`, `/api/config` and `/system` with backoff (1 s doubling
to 30 s) and builds the agent; until then authenticated `/agent` requests get 503.
When ready it probes `/openapi.json` every 30 s; if the sandbox stops answering the
service returns to 503 and rediscovers, so a sandbox restart needs no agent restart.
A run in progress keeps the agent it started with. An allowlisted operation the
sandbox does not offer keeps the service at 503 with that reason.

**Configuration.** `agent.yaml` (`SPE_AGENT_CONFIG`, default
`/etc/spe-agent/agent.yaml`), validated at startup; unknown keys, `surface: typed`,
non-positive limits or caps, a missing prompt file and a model outside
`model.allowed_models` (when set) stop the process with exit 2. Keys come from the environment
only: `SPE_AGENT_API_KEY`, `SANDBOX_API_KEY`, and `OPENAI_API_KEY` or
`ANTHROPIC_API_KEY` by provider.

**Providers.** `model.provider` is `openai_compatible` (any OpenAI-compatible API:
`model.base_url` plus `model.name`, key in `OPENAI_API_KEY`) or `anthropic` (key in
`ANTHROPIC_API_KEY`). Any model name is accepted unless `model.allowed_models` lists the
permitted ones (Ansible: `spe_agent_allowed_models`): an optional spend guard, used by
this repository's development VM to pin `claude-haiku-5-5`. To add a vendor Pydantic AI supports natively
(Google, Bedrock, Mistral, Groq, …): add it to `ModelCfg.provider` and its key variable
in `load_secrets` (`config.py`), build its model in `build_model` (`agent.py`), add the
extra to `pydantic-ai-slim[...]` in `pyproject.toml`, and allow it in the role's check and
in `platform/ansible/roles/agui/templates/agent.env.j2`.

**Prompt.** `prompt.file`, then a newline, then the sandbox's `/system` prompt (when
`prompt.include_sandbox_prompt` and `/api/config` lists `features.system`). That is
Open WebUI v0.11.3's order (commit `2a960a5`): `utils/middleware.py` appends the
terminal prompt to the system message (`add_or_update_system_message(...,
append=True)`), and `routers/openai.py` later prepends the model's prompt
(`apply_system_prompt_to_body`), both joined with `\n`
(`utils/misc.py`, `update_message_content`). System messages sent by the client are
stripped (`manage_system_prompt='server'`); the agent's prompt is reinjected.

**Runs.** Each request builds its history from the request alone (AG-UI
`RunAgentInput.messages`, including earlier tool calls and results); nothing is
shared between requests. When that history nears the model's context window
(`compaction.context_window_tokens` × `trigger_ratio`), or the provider rejects a
request as too long, the agent asks the same model for a summary and sends it in
place of the older messages; the summary goes into the stream as an assistant message
whose id starts with `spe-compaction-`, so the chat keeps it, and later runs cut the
history there. The run log's `compactions` lists each one. The AG-UI thread id is
sent to the sandbox as `X-Session-Id`, as Open WebUI sends its chat id. Per run,
`UsageLimits` caps model requests (`limits.request_limit`, 50) and tool calls
(`tool_calls_limit`, 100). These are per-run caps, not a spend budget: the provider
account's spend limit is the aggregate cap. `total_tokens_limit` can also cap a run's
tokens, but is unset (no cap) by default: it sums the tokens of every model request
in the run, and each request resends the whole conversation, so a long chat hit
400000 where Open WebUI, which has no such cap, went on.

A run ends with exactly one terminal event: `RUN_FINISHED`, or `RUN_ERROR` for a
provider error, an exceeded limit or any other failure. The error message has the
three key values replaced by `[redacted]` and is cut to 500 characters. When the
client disconnects, the agent run and its model request are cancelled. Commands the
model started in the sandbox in the background keep running there; stop them with
the sandbox's `kill_process` operation (the agent's own tool) or by restarting the
sandbox container (`docker compose -p spe-frontend restart sandbox`).

**Run log.** One JSON line per completed, failed or cancelled run in `run_log`
(default `/var/lib/spe-agent/runs.jsonl`, a named volume): run and thread ids, start
and end times, status, the last user message, each tool call (name, arguments,
result, seconds from the end of the call's arguments to its result), the answer,
usage (requests, tool calls, input and output tokens; absent for failed runs) and
the error. Every string, keys of mappings included, has the three key values
redacted, and each field is cut to 16384 bytes. The file is created 0600 in a 0700
directory; records are written whole under a lock. **The log holds player input and
tool results, which include scenario canaries: keep it out of git and do not
publish it.**

**Image.** `Dockerfile`: `python:3.13-slim`, dependencies from the frozen `uv.lock`
(uv 0.12.17), the offline suite run in the `test` stage (the final stage depends on
it), user `spe` (uid 10001), port 8100, `HEALTHCHECK` on `/healthz`. Verified to run
with a read-only root filesystem, a `/tmp` tmpfs, `cap_drop: ALL` and
`no-new-privileges`, with `/var/lib/spe-agent` as a writable volume owned by uid
10001. `.dockerignore` admits only `pyproject.toml`, `uv.lock`, `src/` and `tests/`.

## Sandbox tools

`operations_from_openapi` generates the 16 operations in the pinned fixture;
`select_operations` validates an allowlist, and `build_tools` binds each operation
using `Tool.from_schema` (verified in installed pydantic-ai 2.56.0 source).
`SandboxClient` supports discovery, optional cwd/system prompt, and authenticated
calls. Its owner must call `aclose()` at shutdown; injected HTTP clients remain
owned by their caller. Discovery failures raise `SandboxUnavailable` for later
readiness/retry handling. Optional metadata failures return `None`.

Fixture provenance, recorded by the preceding session: captured `/openapi.json`
from `ghcr.io/open-webui/open-terminal:0.12.4`, digest
`sha256:ca1d60e70f4eca35db62b80b128fffc7d7c156298167aac25cc4982947bcea5b`.
The fixture reports source version 0.12.4. It contains no runtime credentials.
The reference is Open WebUI v0.11.3 `backend/open_webui/utils/tools.py`.

Parity: local schema references are resolved without network access; path/query
parameters follow the baseline string fallback and enum descriptions. Body
properties are merged and nullable singleton schemas cleaned. Mutating requests
send all arguments when a body is defined, otherwise `{}`. Optional empty query
values are omitted; missing/null required values produce errors. The cwd suffix
is added to `run_command`, and a supplied session id becomes `X-Session-Id`.

Differences and limits:

- No Open WebUI-only `display_file` inline/page parameters or base64 binary data
  URIs. Non-JSON and malformed JSON are returned as UTF-8 text with replacement.
- Remote/unresolvable/cyclic schema references resolve to empty schemas. The
  pinned fixture requires no recursive schema support.
- Redirects are errors; the configured HTTP(S) origin alone receives the bearer
  header. Model arguments cannot set headers or origin. Path values are encoded
  as single segments; empty values and literal dot segments are rejected.
  Encoded traversal values remain escaped at the HTTP transport boundary. This
  does not promise confinement through a proxy that repeatedly decodes paths.
- Calls have a 30-second total deadline and HTTP timeout. Responses are streamed
  in 64 KiB chunks, retaining at most 1 MiB while counting the full decoded HTTP
  body for the truncation marker. Counting stops at the deadline, returning a
  timeout error for a never-ending stream. Oversized discovery is rejected.
- Tool results, including the truncation marker, fit `max_output_bytes`. The
  marker's total is the original response byte count; shown bytes count UTF-8
  output after replacement/redaction. For caps too small to fit a marker, only
  its leading bytes are returned. A truncated result is not necessarily JSON.
- Sandbox credentials are redacted from responses; transport exception details
  are not exposed. Owned clients disable environment proxy settings.

Tests: 50 sandbox, 15 configuration and 25 service tests, all offline.
