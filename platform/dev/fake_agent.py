#!/usr/bin/env python3
"""The real agent service with a scripted model and an in-process fake sandbox.

For exercising the chat UI and AG-UI clients without an LLM or a sandbox:
  cd platform/agui/pydantic-ai-agent && uv run --group dev python ../../dev/fake_agent.py --port 18100 --key <test key>
The model runs one `run_command` per turn and then answers; a message containing
"fail" makes the model raise, so the run ends in RUN_ERROR; a message containing
"slow" streams its answer in SLOW_STEPS chunks, SLOW_STEP_SECONDS apart (about 10 s),
for stopping, closing or archiving a run in progress. The run log goes to a
temporary directory, or to --run-log PATH; --key defaults to $SPE_AGENT_API_KEY, so
the key need not sit in argv.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
from pathlib import Path

import httpx
import uvicorn
from pydantic_ai.messages import ModelRequest, ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from spe_agent.app import create_app
from spe_agent.config import Config, Secrets
from spe_agent.sandbox import SandboxClient

FIXTURE = Path(__file__).resolve().parents[1] / "agui" / "pydantic-ai-agent" / "tests" / "fixtures" / "open-terminal-0.12.4-openapi.json"

SLOW_STEPS = 10
SLOW_STEP_SECONDS = 1.0


def fake_sandbox(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/openapi.json":
        return httpx.Response(200, json=json.loads(FIXTURE.read_text()))
    if path == "/files/cwd":
        return httpx.Response(200, json={"cwd": "/home/user"})
    if path == "/api/config":
        return httpx.Response(200, json={"features": {"system": False}})
    if path == "/execute":
        cmd = json.loads(request.content).get("command", "")
        return httpx.Response(200, json={"id": "p1", "status": "done", "exit_code": 0,
                                         "output": f"$ {cmd}\nfake output line 1\nfake output line 2"})
    return httpx.Response(404, json={"detail": "not in the fake sandbox"})


async def scripted(messages, info):
    users = [p.content for m in messages if isinstance(m, ModelRequest)
             for p in m.parts if isinstance(p, UserPromptPart)]
    last_user = str(users[-1]) if users else ""
    if "fail" in last_user.lower():
        raise RuntimeError("scripted model failure (the message asked for it)")
    last = messages[-1].parts[-1]
    if isinstance(last, ToolReturnPart):
        if "slow" in last_user.lower():
            for step in range(1, SLOW_STEPS + 1):
                await asyncio.sleep(SLOW_STEP_SECONDS)
                yield f"Slow step {step} of {SLOW_STEPS}. "
        for chunk in (f"Turn {len(users)}: ", "the command ran. ", "Its output was:\n\n", str(last.content)):
            yield chunk
    else:
        yield {0: DeltaToolCall(name="run_command", json_args=json.dumps({"command": f"echo turn {len(users)}"}),
                                tool_call_id=f"call-{len(users)}")}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=18100)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--key", default=os.environ.get("SPE_AGENT_API_KEY"),
                    help="bearer key clients must send (default: $SPE_AGENT_API_KEY)")
    ap.add_argument("--run-log", type=Path, help="run log path (default: in a temporary directory)")
    args = ap.parse_args()
    if not args.key:
        ap.error("--key or SPE_AGENT_API_KEY is required")
    tmp = Path(tempfile.mkdtemp(prefix="fake-agent-"))
    run_log = args.run_log or tmp / "runs.jsonl"
    (tmp / "prompt.txt").write_text("You are a scripted test agent.")
    config = Config.model_validate({
        # Placeholder only: the scripted model replaces it and no LLM is called.
        "model": {"provider": "anthropic", "name": "claude-haiku-5-5"},
        "prompt": {"file": str(tmp / "prompt.txt")},
        "tools": {"sandbox_url": "http://sandbox:8000"},
        "run_log": str(run_log),
    })
    secrets = Secrets(agent_api_key=args.key, sandbox_api_key="fake-sandbox-key", llm_api_key="no-llm")
    client = SandboxClient("http://sandbox:8000", "fake-sandbox-key",
                           http=httpx.AsyncClient(transport=httpx.MockTransport(fake_sandbox)))
    app = create_app(config, secrets, model_override=FunctionModel(stream_function=scripted), sandbox_client=client,
                     retry_delay=0.1)
    print(f"fake agent on http://{args.host}:{args.port}/agent, run log {run_log}", flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
