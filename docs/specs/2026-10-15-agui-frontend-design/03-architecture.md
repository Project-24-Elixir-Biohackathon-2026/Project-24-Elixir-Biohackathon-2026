## 3. Architecture

```
 operator ─SSH tunnel─▶ 127.0.0.1:3000  ┌ chat-ui (Node) ────────────────┐   network: ui
                                        │ Next.js page: <CopilotChat>     │
                                        │ /api/copilotkit: CopilotRuntime │
                                        │   HttpAgent ─ bearer agent key ─┼─┐
                                        └────────────────────────────────┘ │ AG-UI (SSE)
 promptfoo ─SSH tunnel─▶ 127.0.0.1:8100 ┌ agent (Python) ────────────────┐◀┘   networks: ui, tools
                                        │ FastAPI + AGUIAdapter           │── de.NBI LLM (holds key)
                                        │ Pydantic AI agent, agent.yaml   │
                                        │ run log (JSONL volume)          │
                                        └──────────┬─────────────────────┘
                                                   │ bearer sandbox key, HTTP
                                        ┌ sandbox (open-terminal) ───────┐   network: tools
                                        │ unchanged image: SPE CA,        │── Traefik :443 ─▶ WES/DRS/TRS
                                        │ WES/DRS/TRS_BASE, runbook       │
                                        └────────────────────────────────┘
```

Three containers in one compose project, `spe-frontend`, the same project as the Open WebUI
role's; the sandbox is shared with Open WebUI when both frontends are on (clarification 23):

| Container | Holds | Never holds |
|---|---|---|
| `chat-ui` | the agent's bearer key (server side only, in the runtime route), the sessions' journals (§13) | the LLM key, the sandbox key |
| `agent` | the LLM key, the agent key, the sandbox key, the prompt | — (runs no model-chosen commands) |
| `sandbox` | the sandbox key (visible to its commands), CA, API bases, runbook | the LLM key, the agent key |

**Key boundary rule**: the process holding the LLM key and the place where
model-chosen commands run are different containers (0005, *The LLM key
boundary*).

**Why the agent requires a bearer key.** The agent must share a network
with the sandbox to call it, so the sandbox can reach the agent's port at
the network level. Without a key, a command in the sandbox could call the
agent — spending the LLM key and recursing. The agent therefore rejects
requests without `Authorization: Bearer <spe_agent_api_key>`; the sandbox
never has that key. The chat-ui sends it from its server-side runtime
route, never to the browser; promptfoo reads it from an environment
variable on the controller.
