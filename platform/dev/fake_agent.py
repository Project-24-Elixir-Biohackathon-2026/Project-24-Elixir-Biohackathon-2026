#!/usr/bin/env python3
"""The real agent service with a scripted model and an in-process fake sandbox.

For exercising the chat UI and AG-UI clients without an LLM or a sandbox:
  cd platform/agui/pydantic-ai-agent && uv run --group dev python ../../dev/fake_agent.py --port 18100 --key <test key>
The model runs one `run_command` per turn and then answers; a message containing
"fail" makes the model raise, so the run ends in RUN_ERROR; a message containing
"slow" streams its answer in SLOW_STEPS chunks, SLOW_STEP_SECONDS apart (1 s, or
$SPE_FAKE_SLOW_STEP_SECONDS; about 10 s by default),
for stopping, closing or archiving a run in progress; a message containing "compact"
runs a command with a long output, so the history passes the scripted window
(COMPACT_WINDOW tokens) and the agent compacts it with a scripted summary (once per
session: in a session that already compacted, "compact" answers "compacted" without
running the command, as the summary stays in the history); a message containing "echo-input" makes the model answer, instead of
running a command, with the JSON list of {role, id} of what it was sent (the system prompt left out), so a
client can see which history reached the model. The run log
goes to a temporary directory, or to --run-log PATH; --key defaults to
$SPE_AGENT_API_KEY, so the key need not sit in argv.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
import uuid
from pathlib import Path

import httpx
import uvicorn
from pydantic_ai.messages import (
    ModelRequest, ModelResponse, SystemPromptPart, TextPart, ToolCallPart, ToolReturnPart, UserPromptPart,
)
from pydantic_ai.ui._utils import get_ui_message_id
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from spe_agent.app import create_app
from spe_agent.compaction import FRAME, SUMMARY_PROMPT
from spe_agent.config import Config, Secrets
from spe_agent.sandbox import SandboxClient

FIXTURE = Path(__file__).resolve().parents[1] / "agui" / "pydantic-ai-agent" / "tests" / "fixtures" / "open-terminal-0.12.4-openapi.json"

SLOW_STEPS = 10
# The dev VM's live archive check sets SPE_FAKE_SLOW_STEP_SECONDS (fake-agent.compose.yml) for a longer run.
SLOW_STEP_SECONDS = float(os.environ.get("SPE_FAKE_SLOW_STEP_SECONDS", "1.0"))

# Not the brief's ≈8,500: FunctionModel's own usage estimate (pydantic_ai.models.function._estimate_usage)
# counts only message content, never tool schemas, so the brief's ≈3,000-token tool overhead never enters
# the estimate once a response carries usage. An ordinary turn is ≈95 tokens; the long output, cut to the
# tool cap, takes the next request to ≈5,500 — over this window's trigger (0.8 × 6000) but under 8000's.
COMPACT_WINDOW = 6000        # tokens
LONG_OUTPUT_CHARS = 20_000   # more than the tool cap, so the cut, not this number, sets the size


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
        if cmd.startswith("print-long-output"):
            return httpx.Response(200, json={"id": "p1", "status": "done", "exit_code": 0,
                                             "output": f"$ {cmd}\n" + "x" * LONG_OUTPUT_CHARS})
        return httpx.Response(200, json={"id": "p1", "status": "done", "exit_code": 0,
                                         "output": f"$ {cmd}\nfake output line 1\nfake output line 2"})
    return httpx.Response(404, json={"detail": "not in the fake sandbox"})


def summarise(messages, info) -> ModelResponse:
    """The compaction's summary request: system prompt SUMMARY_PROMPT, the transcript as the user part."""
    parts = messages[0].parts
    if not (isinstance(parts[0], SystemPromptPart) and parts[0].content == SUMMARY_PROMPT):
        raise RuntimeError("not a summary request")
    text = str(parts[-1].content)
    latest = next((line for line in reversed(text.splitlines()) if "compact" in line.lower()), "")
    return ModelResponse(parts=[TextPart(
        f"Scripted summary of {len(text)} characters of conversation. The latest request was: {latest.strip()}")])


def received(messages) -> list[dict]:
    """What the model was sent, as [{role, id}]: one entry per part, the system prompt left out, with the AG-UI id
    of the message the part came from. pydantic-ai keeps one AG-UI id per model message (the adapter's
    set_ui_message_id), so AG-UI messages merged into one model message all show the last one's id."""
    out = []
    for m in messages:
        ui_id = get_ui_message_id(m)
        for p in m.parts:
            if isinstance(p, UserPromptPart):
                role = "user"
            elif isinstance(p, ToolReturnPart):
                role = "tool"
            elif isinstance(p, (TextPart, ToolCallPart)):
                role = "assistant"
            else:
                continue
            out.append({"role": role, "id": ui_id})
    return out


async def scripted(messages, info):
    users = [str(p.content) for m in messages if isinstance(m, ModelRequest)
             for p in m.parts if isinstance(p, UserPromptPart) and not str(p.content).startswith(FRAME)]
    last_user = users[-1] if users else ""
    if "echo-input" in last_user.lower():
        yield json.dumps(received(messages))
        return
    if "fail" in last_user.lower():
        raise RuntimeError("scripted model failure (the message asked for it)")
    last = messages[-1].parts[-1]
    compacting = "compact" in last_user.lower()
    if compacting and isinstance(last, UserPromptPart) and any(
            isinstance(p, UserPromptPart) and str(p.content).startswith(FRAME)
            for m in messages if isinstance(m, ModelRequest) for p in m.parts):
        # The agent compacted after the long output: the request holds the summary and the latest request.
        yield f"Turn {len(users)}: the command ran. The conversation was compacted."
        return
    if isinstance(last, ToolReturnPart):
        if "slow" in last_user.lower():
            for step in range(1, SLOW_STEPS + 1):
                await asyncio.sleep(SLOW_STEP_SECONDS)
                yield f"Slow step {step} of {SLOW_STEPS}. "
        for chunk in (f"Turn {len(users)}: ", "the command ran. ", "Its output was:\n\n", str(last.content)):
            yield chunk
    else:
        command = f"print-long-output turn {len(users)}" if compacting else f"echo turn {len(users)}"
        # A unique id: after a compaction the turn count starts again, and an id reused from an earlier run
        # makes an AG-UI client append this call's arguments and result to that run's call.
        yield {0: DeltaToolCall(name="run_command", json_args=json.dumps({"command": command}),
                                tool_call_id=f"call-{len(users)}-{uuid.uuid4().hex[:8]}")}


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
        "compaction": {"context_window_tokens": COMPACT_WINDOW},
    })
    secrets = Secrets(agent_api_key=args.key, sandbox_api_key="fake-sandbox-key", llm_api_key="no-llm")
    client = SandboxClient("http://sandbox:8000", "fake-sandbox-key",
                           http=httpx.AsyncClient(transport=httpx.MockTransport(fake_sandbox)))
    app = create_app(config, secrets, model_override=FunctionModel(summarise, stream_function=scripted),
                     sandbox_client=client, retry_delay=0.1)
    print(f"fake agent on http://{args.host}:{args.port}/agent, run log {run_log}", flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
