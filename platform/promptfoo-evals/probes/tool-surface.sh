# tool-surface (L4): the agent's tool list includes run_command. Runs in the agent container.
set -u
python - <<'EOF'
import asyncio, os
from spe_agent.config import load_config
from spe_agent.sandbox import SandboxClient, operations_from_openapi, select_operations

cfg = load_config(os.environ["SPE_AGENT_CONFIG"])

async def names():
    client = SandboxClient(cfg.tools.sandbox_url, os.environ["SANDBOX_API_KEY"])
    try:
        ops = operations_from_openapi(await client.openapi())
    finally:
        await client.aclose()
    return sorted(op.name for op in select_operations(ops, cfg.tools.sandbox_operations))

tools = asyncio.run(names()) if cfg.tools.surface == "shell" else []
print("TOOLS", ",".join(tools) or "-")
if "run_command" in tools:
    print(f"PROBE open surface={cfg.tools.surface}")
else:
    print(f"PROBE closed surface={cfg.tools.surface}")
EOF
