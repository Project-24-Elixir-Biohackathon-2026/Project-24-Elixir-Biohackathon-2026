# platform

Everything that builds, runs or tests an SPE evaluation instance. The threat
catalog these instances exist for is in `../threats/`.

| Directory | What | Read |
|---|---|---|
| `ansible/` | Builds one instance (VM, data with canaries, WES/DRS/TRS stack, chat frontend), verifies it, archives its run, tears it down | `ansible/README.md` |
| `coder/` | The portal: participants pick a testbed preset, get an instance with the frontend one click away, and every stop archives the run | `coder/README.md` |
| `agui/` | The AG-UI frontend: `pydantic-ai-agent/`, our Pydantic AI agent served over AG-UI, and `copilotkit-chat/`, its Next.js + CopilotKit chat | each one's `README.md` |
| `promptfoo-evals/` | promptfoo suite that drives an instance's agent directly and checks answers and tool calls | `promptfoo-evals/README.md` |
| `dev/` | Dummy dataset generator, a scripted agent for offline runs, tests for the host-side scripts | `../AGENTS.md`, "Running things" |

## Two frontends, one sandbox

Each instance runs both chat frontends on its VM (`spe_frontends`, an instance-file
variable listing `openwebui` and `agui`; the portal always deploys both and shows a
button for each). The person picks the chat; both drive the same sandbox:

| | `openwebui` | `agui` |
|---|---|---|
| Chat | Open WebUI on `127.0.0.1:8080` | CopilotKit chat on `127.0.0.1:3000` |
| Agent loop | Open WebUI's own | `pydantic-ai-agent` on `127.0.0.1:8100`, over AG-UI |
| Holds the LLM key | Open WebUI | the agent only |
| Commands run in | the one open-terminal sandbox (`ansible/roles/sandbox`), shared by both | |
| Login | none (`spe_webui_auth: false`); the portal or the SSH tunnel is the gate | bearer key between chat and agent; none in the browser |
| Documentation by the tester | pinned "Run report" note, chat tags | not yet |
| Archived on stop | chats, notes, tags, parameters, canary record | parameters, canary record |
| Evaluations | | `promptfoo-evals/` (AG-UI provider) |

Both are in the compose project `spe-frontend`; `spe_frontends: [agui]` (or
`[openwebui]`) deploys only one, `[]` none.

## Where things run

```
controller (portal VM, or your machine)        SPE VM, one per instance
  ansible-playbook create / verify /    ──▶    workflow-stack: Traefik :443, WES, DRS, TRS
    archive / destroy                           spe-frontend:   chat + agent/Open WebUI + sandbox
  coder server + provisioner                    coder-agent (portal instances only)
  ansible/output/<instance>/  (canary record)
  /data-share: base dataset in, runs/ out
```

Secrets never enter the repo: the seed in the instance file reproduces every
canary, the LLM key comes from the environment, `ansible/output/` is ignored.
`../AGENTS.md` lists the rules.
