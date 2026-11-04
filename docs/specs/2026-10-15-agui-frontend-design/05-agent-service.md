## 5. The agent service

### Endpoints

- `POST /agent` — AG-UI, through `AGUIAdapter.dispatch_request`. Bearer
  key required (401 otherwise). A run whose `forwardedProps.spe_command` names a command is answered
  without the model loop (§15, `/compact`).
- `POST /title` — a short, model-written title for a chat (`{thread_id, messages}`, one or two
  `{role, content}` messages: the session's first user message and, if any, the first answer). Bearer key
  required (401 otherwise); `404` when `title.enabled` is false; `422` when the model call fails or returns
  no usable title (the detail redacted and length-capped, as the run log's keys are below); otherwise `200`
  with `{"title": "…"}`. Every call is appended to the run log (below) whether it succeeds or not.
  `chat-ui`'s session API is the only caller (§6 *Session API*).
- `GET /healthz` — no auth, no LLM call; 200 when config is loaded and the
  sandbox's OpenAPI was fetched.

Served by uvicorn on port 8100 in the container.

### Model

Two providers, chosen in `agent.yaml` (`model.provider`):

- `openai_compatible` (default, used on de.NBI): Pydantic AI's
  OpenAI-compatible model with `base_url = spe_llm_base_url`, model
  `spe_agent_model` (default `spe_webui_model_id`, `qwen3.8-27b`), key
  `OPENAI_API_KEY`.
- `anthropic` (local testing, where the de.NBI endpoint is not reachable):
  Pydantic AI's Anthropic model, key `ANTHROPIC_API_KEY`. **Only
  `claude-haiku-5-5`** (decided 2026-10-15, to keep spend low: $0.10 input
  / $0.50 output per MTok for prompts up to 100k tokens, verified on the
  Anthropic pricing page 2026-10-15). The role rejects any other Anthropic
  model name, so a typo cannot select a pricier one. Spend is capped
  outside the code by a spend limit on the Anthropic Console's Billing
  page, and inside it by `limits` below.

The key comes from `agent.env`, which only this container receives.
Results from the two providers are not comparable with each other; the
Open WebUI baseline comparison uses `openai_compatible` on de.NBI.

### Tools: parity with Open WebUI

Verified 2026-10-15 against Open WebUI `v0.11.3`
(`backend/open_webui/utils/tools.py`) and open-terminal `0.12.4`: Open WebUI
turns **every operation** in the terminal server's `/openapi.json` into a
tool named by its `operationId`, appends the terminal's working directory
to `run_command`'s description, and uses the terminal's own system prompt
from `GET /system` (exposed when `/api/config` lists `features.system`).
The 16 operations in `0.12.4`: `list_files`, `read_file`, `display_file`,
`write_file`, `replace_file_content`, `grep_search`, `match_files`,
`search_files`, `glob_search`, `list_processes`, `run_command`,
`get_process_status`, `send_process_input`, `kill_process`,
`read_user_terminal`, `send_user_terminal_input`.

So the agent does the same, generically:

1. At startup, fetch the sandbox's `/openapi.json` (bearer sandbox key),
   with retries until the sandbox is up.
2. For each operation in the allowlist `tools.sandbox_operations` (default:
   all), build a Pydantic AI tool from the operation's JSON schema (path
   and query parameters plus the JSON body, flattened as Open WebUI does),
   named by `operationId`, described by its summary/description.
3. Calling the tool performs the HTTP request against the sandbox and
   returns the JSON response.
4. `run_command`'s description gets the working directory from
   `GET /files/cwd`, as in Open WebUI.

Generating from the spec keeps the tool set identical to the Open WebUI
baseline and follows open-terminal upgrades without code changes.

**Output cap**: each tool result is serialised and cut to
`tools.max_output_bytes` (default 16384) with a marker
`[truncated: N of M bytes shown]`, so one `cat` of a large file cannot
flood the context. Open WebUI's own truncation behaviour is not mirrored
(not investigated); this is a deliberate, recorded difference.

### Prompt

The system prompt is `system_prompt.txt` (today's, unchanged) followed by
the sandbox's `/system` prompt. Open WebUI's exact combination of the two
(order, separator, whether the model-attached prompt and the terminal
prompt are merged) is **to verify** during implementation in
`utils/middleware.py`; the agent mirrors whatever it does, and the spec is
updated with the finding.

### Limits

Per AG-UI run, Pydantic AI `UsageLimits`: `limits.request_limit` (model
requests, default 50) and `limits.tool_calls_limit` (default 100).
`limits.total_tokens_limit` is optional and unset by default (no cap). It was
added during implementation from the spend concern with a default of 400000,
then turned off by default (2026-10-29): it sums every request's tokens in a
run, each request resends the whole conversation, so long chats failed where
Open WebUI, which has no such cap, did not. Hitting a limit ends the run with an AG-UI `RUN_ERROR`
carrying a clear message, and the chat shows it. These are per-run caps, not
aggregate spend enforcement: the provider account's spend limit is the
aggregate cap, and portal or per-user budgets remain deferred.

### Run log

Every run appends JSON lines to `/var/lib/spe-agent/runs.jsonl` (a named
volume): run id, thread id, timestamp, the incoming user message, each tool
call (name, arguments, truncated result, duration), the final answer, usage,
and errors. No secrets are logged; the bearer keys and the LLM key never
appear in a tool result by construction (§3), and the logger additionally
redacts the three key values if they occur.

A `POST /title` call appends its own line, `{"type": "title", ...}` (thread id, start and end time,
the title or `null` on failure, usage, and the error if any); a run line carries no `type`, so a reader
can tell the two apart and count only runs (`platform/ansible/roles/run_archive/files/write_run.py`).

### Configuration

`agent.yaml`, rendered by Ansible, validated at startup (unknown keys are
an error):

```yaml
model: { provider: openai_compatible, name: qwen3.8-27b, base_url: https://…/v1 }   # key comes from env
prompt: { file: /etc/spe-agent/system_prompt.txt, include_sandbox_prompt: true }
tools:
  surface: shell            # shell | typed (typed: reserved, rejected for now)
  sandbox_url: http://sandbox:8000
  sandbox_operations: all   # or a list of operationIds
  max_output_bytes: 16384
limits: { request_limit: 50, tool_calls_limit: 100 }   # total_tokens_limit: optional, no cap when unset
title: { enabled: true, max_tokens: 64 }   # POST /title; enabled off answers 404
```

Keys (LLM, agent, sandbox) come from `agent.env`, never from `agent.yaml`.

### History

The client sends the conversation with each AG-UI run (`RunAgentInput`),
as AG-UI defines; the agent keeps no session state and trusts the history
it is sent. Through the chat, that client is `chat-ui`, which sends the
history from its journal, not the browser's (§13).
