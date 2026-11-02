# SIGKILL on `uv run` orphans the process it started

**Symptom.** A Node check that spawns `uv run … python fake_agent.py` and, on a timeout, sends the child
`SIGKILL` exits, but `fake_agent.py` keeps running (still holding its port), and a pipe on the check's
output (`node check.mjs | grep …`) never ends, because the orphan still holds the inherited stdout.

**Why.** `uv run` starts Python as its own child and forwards catchable signals to it; `SIGKILL` cannot be
caught, so `uv` dies alone and the Python process is reparented.

**Fix.** Stop such a child with `SIGTERM` (uv passes it on), as `platform/agui/copilotkit-chat/scripts/check-built-server.mjs`'s
deadline does, and give it a moment before `process.exit()`. Leftovers: `pgrep -fa fake_agent`.
