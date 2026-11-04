## 11. Things to verify during implementation

Each is recorded back into this spec when settled.

0. Re-provisioning this VM with the agentvm fix gives passwordless sudo
   (`sudo -n true`).
1. On the de.NBI hosts, once SSH access works again: which one is the
   controller (`clouds.yaml`, `~/.venv-openstack`, `/data-share`), which
   one hosts the first test SPE, and that it meets §7.0's requirements.

2. Open WebUI's combination of model system prompt and terminal `/system`
   prompt (§5 *Prompt*).
3. How Open WebUI flattens path/query/body parameters into one tool schema
   (`utils/tools.py`, `convert_openapi_to_tool_payload` or equivalent), so
   our generated schemas match.
4. Current Pydantic AI APIs used: `AGUIAdapter.dispatch_request`,
   `UsageLimits` fields, building a tool from a JSON schema
   (`Tool.from_schema` or equivalent).
5. CopilotKit v2 package names and the `HttpAgent` headers option.
6. That a read-only root filesystem works for the Next.js and uvicorn
   images; drop it for a container where it does not, and say so here.
