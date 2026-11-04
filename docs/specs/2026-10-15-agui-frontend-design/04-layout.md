## 4. Layout in the repository

```
agent/                         Python service (own Dockerfile, pyproject, tests)
  src/spe_agent/
    app.py                     FastAPI: POST /agent (AG-UI), GET /healthz, bearer check
    config.py                  load + validate agent.yaml (pydantic model)
    sandbox.py                 open-terminal client; tools generated from its OpenAPI
    agent.py                   build the Pydantic AI Agent from config
    runlog.py                  JSONL run log
  tests/
chat-ui/                       Next.js app (own Dockerfile, package-lock.json)
  app/page.tsx                 full-screen CopilotChat + default tool-call renderer
  app/api/copilotkit/route.ts  CopilotRuntime + HttpAgent(AGENT_URL, bearer)
evals/
  promptfooconfig.yaml
  agui_provider.py             promptfoo Python provider speaking AG-UI
  README.md
ansible/roles/
  sandbox/                     NEW, shared: Dockerfile.terminal, AGENTS.md, CA copy, image build
  openwebui/                   uses sandbox; otherwise unchanged
  agui/                        NEW: build agent + chat-ui images, render config, compose up, checks
docs/specs/                    this file
```

The `sandbox` role is the current `openwebui` role's build steps moved
unchanged (Dockerfile, runbook, CA copy, `docker_image` build). The
`openwebui` role depends on it; its rendered compose and env files do not
change. `system_prompt.txt` moves to the `sandbox` role too, since both
frontends use it.

The `agui` role copies `agent/` and `chat-ui/` from the repo checkout on
the controller to the VM as build contexts and builds the images there,
as `workflow_stack` does. No registry.
