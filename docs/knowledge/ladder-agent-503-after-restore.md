# Agent suite: "agent answered HTTP 503" on most tests after each restore

**Symptom** (slice 10's first L0 clean run, 2026-11-09): `run.sh` exits 0 but `reports/L0-clean/agent.json` has
`errors: 59` of 65, every one `agent answered HTTP 503`, in about 1.4 s. The agent's log shows
`sandbox stopped answering; rediscovering` once per test, and `GET /healthz` answers 503 too.

**Cause.** The beforeEach restore (`isolation.restore`) stops and recreates the sandbox and the stack, which takes
~45 s, longer than the agent's sandbox probe (`probe_interval`, 30 s). The probe catches the sandbox down, the
agent drops to "not ready" (503 on `/healthz` and on `POST /agent`, before any work) and rediscovers with a backoff
that doubles up to 30 s. `restore` waits for the stack and the APIs, not for the agent, so the test's POST lands in
that window.

**Fix.** The provider retries a 503 every 2 s for up to `config.ready_timeout_s` (180 s, `agent.yaml`) before
reporting it (`agui_provider._open_when_ready`); promptfoo's worker `timeout` covers the wait. A 503 past it is
still an `error`, never a result.
