# This workspace: one SPE evaluation instance

You are on the VM of one SPE instance of the SPE Range test bed. It runs a GA4GH workflow stack (WES, DRS, TRS behind Traefik on port 443) seeded with test data and canary tokens, and a chat frontend through which an LLM agent (the "SPE agent") probes it. People use this workspace to change the setup and try the change in that chat right away.

## Layout

- `~/sperange`: a git clone of the repository (github.com/kraatz/elixir-biohackathon-2026-test), the source of everything below. Edit here.
- `~/spe-frontend`: the chat frontend's compose project. Written by Ansible when the instance was built: `.env` (which frontend, image names, ports), `agent.yaml`, secret env files, the instance CA. `docker-compose.yml` is a link to `~/sperange/platform/instance/compose.yml`. Do not edit the secret files; do not print them.
- `~/workflow-stack`: the GA4GH services (compose project `workflow-stack`), `/data-share`: the seeded dataset.

The frontend is either Open WebUI (`spe-frontend` containers `open-webui`, `open-terminal`) or our own AG-UI agent (`chat-ui` or `chat-ui-dev`, `agent`, `sandbox`); `COMPOSE_PROFILES` in `~/spe-frontend/.env` says which.

## What a change needs

Live, nothing to run (bind mounts from the clone):

- the SPE agent's runbook and helper scripts: `platform/ansible/roles/sandbox/files/agent/` is `/opt/agent` inside the sandbox; the runbook tells the agent what is there.
- the SPE agent's system prompt: `platform/ansible/roles/sandbox/files/system_prompt.txt` (AG-UI frontend; read on every run).
- the agent's Python source: `platform/agui/pydantic-ai-agent/src/` (the agent restarts itself on a saved file; a syntax error keeps it down until fixed, `spe-apply logs agent` shows it).
- the chat UI's source, only in `ui-dev` mode: `platform/agui/copilotkit-chat/app/`.

`spe-apply up`: the compose file (`platform/instance/compose.yml`) or `~/spe-frontend/agent.yaml`.

`spe-apply` (build, then up): the agent's dependencies (`pyproject.toml`, `uv.lock`), the chat UI outside `ui-dev` mode, `Dockerfile.terminal`, anything in the GA4GH stack's images. A build with unchanged inputs takes seconds thanks to Docker's cache.

Nothing here applies to the Ansible roles or the Coder template: those run on the portal when a workspace starts. For them, commit, push, merge, restart the workspace.

## Rules

- Keep changes in `~/sperange`: commit on a branch with a clear message. The VM is destroyed on the next workspace stop; only what is pushed survives.
- Never put a key, token or canary value into a commit, a file in the clone, or your answer. The agent's run log (`docker compose -p spe-frontend exec agent cat /var/lib/spe-agent/runs.jsonl`) holds canaries: quote from it sparingly.
- Every chat with the SPE agent is a paid model call; do not script loops against it.
- The sandbox reaches only the three GA4GH APIs by design; do not "fix" TLS with `-k` or add network routes.
