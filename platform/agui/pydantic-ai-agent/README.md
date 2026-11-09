# SPE agent

A Pydantic AI agent for one SPE instance, served over AG-UI. It holds the LLM key
and calls the open-terminal sandbox, where model-chosen commands run; it runs no
commands itself. Deployed by the `agui` Ansible role next to the sandbox and the chat
UI. Design: `docs/specs/2026-10-15-agui-frontend-design/`.

```bash
uv run --group dev pytest -q                   # offline: no LLM, no network
docker build -t spe-agent:dev .                # runs the same tests in its test stage
SPE_AGENT_CONFIG=agent.yaml SPE_AGENT_API_KEY=… SANDBOX_API_KEY=… OPENAI_API_KEY=… \
  uv run python -m spe_agent                   # serves :8100
```

## Endpoints

| Route | What |
|---|---|
| `POST /agent` | AG-UI `RunAgentInput` in, server-sent events out. `Authorization: Bearer <SPE_AGENT_API_KEY>`, checked before readiness: 401 without it, 422 on a malformed body, 503 until the sandbox's tools are discovered |
| `POST /title` | A 2-4 word title for a session's first message (or first exchange); same key; 404 when `title.enabled` is false |
| `GET /healthz` | No auth, no model call. 200 `{"status": "ok", "tools": N}` once ready, else 503 with a reason |

**Readiness.** A background task discovers the sandbox (`/openapi.json`,
`/files/cwd`, `/api/config`, `/system`) with backoff and builds the agent; it probes
every 30 s and rediscovers after a sandbox restart. A run in progress keeps the agent
it started with.

## Configuration

`agent.yaml` (`SPE_AGENT_CONFIG`, default `/etc/spe-agent/agent.yaml`), validated at
startup; an unknown key, a bad limit, a missing prompt file or a model outside
`model.allowed_models` stops the process with exit 2. Keys come from the environment
only: `SPE_AGENT_API_KEY`, `SANDBOX_API_KEY`, and `OPENAI_API_KEY` or
`ANTHROPIC_API_KEY` by provider.

- `model.provider`: `openai_compatible` (`model.base_url`, `model.name`) or
  `anthropic`. Another vendor Pydantic AI supports: add it to `ModelCfg.provider`
  and `load_secrets` (`config.py`), `build_model` (`agent.py`), the extra in
  `pyproject.toml`, the role's check and `agent.env.j2`.
- `prompt.file`, then the sandbox's `/system` prompt when
  `prompt.include_sandbox_prompt` (Open WebUI's order). System messages sent by the
  client are stripped.
- `tools.sandbox_url`, `tools.sandbox_operations` (`all` or an allowlist of
  operation ids), `tools.max_output_bytes`.
- `limits.request_limit` (50), `limits.tool_calls_limit` (100),
  `limits.total_tokens_limit` (unset: no cap). Per run, not a spend budget.
- `compaction.enabled` (true), `compaction.context_window_tokens` (null: only the
  reactive trigger), `compaction.trigger_ratio` (0.8), `compaction.summary_max_tokens`
  (4096). Before a request at or past the trigger, or after a provider rejects a
  request as too long, the agent asks the same model for a summary of the history
  (`compaction_prompt.md`) and sends the system prompt, the summary, the latest
  request and what follows. The summary enters the stream as an assistant message
  with id prefix `spe-compaction-`, so the chat keeps it and later runs cut there.
  At most one compaction per request and three per run. `/compact [focus]` from the
  chat compacts on demand.
- `title.enabled` (true), `title.max_tokens` (1024).
- `run_log` (`/var/lib/spe-agent/runs.jsonl`).

## Runs

Each request's history comes from the request alone. The AG-UI thread id is sent to
the sandbox as `X-Session-Id`. A run ends with one terminal event: `RUN_FINISHED`, or
`RUN_ERROR` with the key values replaced by `[redacted]` and the message cut to 500
characters. A client that disconnects cancels the run and its model request;
commands started in the sandbox keep running there (`kill_process`, or restart the
sandbox container).

**Run log**: one JSON line per run: ids, times, status, the last user message, each
tool call with its result and duration, the answer, usage, the error, compactions;
keys redacted, fields cut to 16384 bytes, file 0600. It holds participant input and
canaries: never publish it.

**Airlock (L5)**: `SPE_AIRLOCK=1` with `SPE_STUDY_ID_PREFIX` set turns on a pattern
filter over the agent's answer, catching five classes: sensitive paths, study ids,
AWS access and secret keys, and `*_KEY`/`*_SECRET` assignments, also written as
Markdown (`code`, **bold**, a table row); a value is one token or a quoted string on
one line, so an unquoted passphrase keeps all but its first word (`airlock.py`; `SPE_AIRLOCK=1` without the
prefix is a configuration error, exit 2). The assignment names match in any case, so
a benign `primary_key: id` or `cache_key = f(x)` also shows a redacted value: a leaked
`api_key=` matters more than a changed schema line. On, each text
message is buffered and sent whole, redacted, right before it ends rather than
token by token, so a pattern split across stream chunks (a study id, a path) is
still caught; the user sees the message appear all at once when the model finishes
it, a wait of its whole generation time. Tool results, reasoning events and
compaction summaries (the automatic markers and `/compact`) are not the answer and
are not filtered. Off (the default), events stream unchanged. The
same filter runs standalone as `python -m spe_agent.airlock`, copying stdin to
stdout redacted when the container's environment turns it on, for the controls
suite's `airlock` probe.

## Image

`Dockerfile`: `python:3.14-slim`, dependencies from the frozen `uv.lock`, the test
suite in the `test` stage, user `spe` (uid 10001), port 8100, a health check on
`/healthz`. Runs with a read-only root, a `/tmp` tmpfs, `cap_drop: ALL` and
`no-new-privileges`; `/var/lib/spe-agent` is a volume owned by uid 10001.

## Sandbox tools

`operations_from_openapi` turns the sandbox's OpenAPI into tools (16 operations in
the fixture, captured from `ghcr.io/open-webui/open-terminal:0.16.1` with its browser
and desktop tools off, as the sandbox runs it), `select_operations` applies the
allowlist, `build_tools` binds them with `Tool.from_schema`. Limits:

- Only the configured origin receives the bearer header; redirects are errors;
  model arguments cannot set headers, origin or path traversal.
- 30 s deadline per call; responses stream in 64 KiB chunks, at most 1 MiB kept;
  results are cut to `max_output_bytes` with a marker giving the original size.
- Sandbox credentials are redacted from responses; transport errors are not exposed.
