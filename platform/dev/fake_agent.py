#!/usr/bin/env python3
"""The real agent service with a scripted model and an in-process fake sandbox.

For exercising the chat UI and AG-UI clients without an LLM or a sandbox:
  cd platform/agui/pydantic-ai-agent && uv run --group dev python ../../dev/fake_agent.py --port 18100 --key <test key>
The model runs one `run_command` per turn and then answers; a message containing
"fail" makes the model raise, so the run ends in RUN_ERROR; a message containing
"slow" streams its answer in SLOW_STEPS chunks, SLOW_STEP_SECONDS apart (1 s, or
$SPE_FAKE_SLOW_STEP_SECONDS; about 10 s by default),
for stopping, closing or archiving a run in progress; a message containing "slow-fail" runs its
command and streams the slow steps, then raises (a run error after a while, from a session left meanwhile);
a message containing "compact"
runs a command with a long output, so the history passes the scripted window
(COMPACT_WINDOW tokens) and the agent compacts it with a scripted summary; it compacts
every time it is sent, not once per session (the request right after a fresh compaction,
within the same run, is answered "compacted" without running the command again, as the
summary is already the latest thing in the history); a command (`spe_command`) is
answered with a fixed summary that quotes its focus; a message containing "multi-tool" makes the
model run two commands in one response, the second exiting 1 (the chat groups them and shows the failure);
a message containing "echo-input"
makes the model answer, instead of running a command, with the JSON list of {role, id}
of what it was sent (the system prompt left out), so a
client can see which history reached the model. `/threat-score` is on, with scripted embeddings
(no network): a draft containing "secret" scores high, "Secrets and credentials" among its high categories, any other
draft low; with --embeddings-url (and $SPE_FAKE_EMBEDDINGS_KEY) the drafts are embedded by that
OpenAI-compatible endpoint instead, for a look at real scores. `/title` is off (the e2e finds rows by
their auto title; see `title: {enabled: False}` below). The run log
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
from spe_agent.compaction import FOCUS_HEADING, SUMMARY_PROMPT, SUMMARY_PROMPT_MANUAL, is_framed
from spe_agent.config import Config, Secrets
from spe_agent.sandbox import SandboxClient
from spe_agent.threat import ThreatModel

FIXTURE = Path(__file__).resolve().parents[1] / "agui" / "pydantic-ai-agent" / "tests" / "fixtures" / "open-terminal-0.16.1-openapi.json"

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
        if cmd.startswith("exit-1"):
            return httpx.Response(200, json={"id": "p2", "status": "done", "exit_code": 1,
                                             "output": f"$ {cmd}\nscripted failure"})
        if cmd.startswith("print-long-output"):
            return httpx.Response(200, json={"id": "p1", "status": "done", "exit_code": 0,
                                             "output": f"$ {cmd}\n" + "x" * LONG_OUTPUT_CHARS})
        return httpx.Response(200, json={"id": "p1", "status": "done", "exit_code": 0,
                                         "output": f"$ {cmd}\nfake output line 1\nfake output line 2"})
    return httpx.Response(404, json={"detail": "not in the fake sandbox"})


# Automatic summaries written but not yet answered with "compacted" (scripted's check).
FRESH: set[str] = set()


def summarise(messages, info) -> ModelResponse:
    """The compaction's summary request: system prompt SUMMARY_PROMPT (automatic) or SUMMARY_PROMPT_MANUAL
    (/compact), the transcript as the first user part, a manual request's focus (after FOCUS_HEADING) as a second."""
    system, text_part, *focus_part = messages[0].parts
    if not isinstance(system, SystemPromptPart) or system.content not in (SUMMARY_PROMPT, SUMMARY_PROMPT_MANUAL):
        raise RuntimeError("not a summary request")
    text = str(text_part.content)
    if system.content == SUMMARY_PROMPT_MANUAL:
        focus = str(focus_part[0].content).removeprefix(f"{FOCUS_HEADING}:\n\n") if focus_part else ""
        focus_text = focus.strip("`\n") or "(none)"
        return ModelResponse(parts=[TextPart(f"Scripted summary on request of {len(text)} characters. "
                                             f"Focus: {focus_text}")])
    latest = next((line for line in reversed(text.splitlines()) if "compact" in line.lower()), "")
    nonce = f"[summary {uuid.uuid4().hex[:8]}]"
    FRESH.add(nonce)
    return ModelResponse(parts=[TextPart(
        f"Scripted summary of {len(text)} characters of conversation. The latest request was: {latest.strip()} "
        f"{nonce}")])


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
             for p in m.parts if isinstance(p, UserPromptPart) and not is_framed(p.content)]
    last_user = users[-1] if users else ""
    if "echo-input" in last_user.lower():
        yield json.dumps(received(messages))
        return
    slow_fail = "slow-fail" in last_user.lower()  # before "fail", which raises at once
    if "fail" in last_user.lower() and not slow_fail:
        raise RuntimeError("scripted model failure (the message asked for it)")
    last = messages[-1].parts[-1]
    compacting = "compact" in last_user.lower()
    # Already compacted for this very request: the head's frame holds a summary not answered yet. The shape
    # can't tell: after a marker from an earlier run, build_sent also puts the frame and the latest prompt in
    # the head request, as compacted() does right after a fresh compaction; so summarise() tags each summary.
    fresh = next((n for p in messages[0].parts if isinstance(p, UserPromptPart) and is_framed(p.content)
                  for n in FRESH if n in str(p.content)), None)
    if compacting and isinstance(last, UserPromptPart) and fresh is not None:
        FRESH.discard(fresh)
        # The agent compacted after the long output: the request holds the summary and the latest request.
        yield f"Turn {len(users)}: the command ran. The conversation was compacted."
        return
    if isinstance(last, ToolReturnPart):
        if "slow" in last_user.lower():
            for step in range(1, SLOW_STEPS + 1):
                await asyncio.sleep(SLOW_STEP_SECONDS)
                yield f"Slow step {step} of {SLOW_STEPS}. "
            if slow_fail:
                raise RuntimeError("scripted model failure after the slow steps (the message asked for it)")
        for chunk in (f"Turn {len(users)}: ", "the command ran. ", "Its output was:\n\n", str(last.content)):
            yield chunk
    elif "multi-tool" in last_user.lower():
        tag = uuid.uuid4().hex[:8]
        yield {0: DeltaToolCall(name="run_command", json_args=json.dumps({"command": f"echo turn {len(users)}"}),
                                tool_call_id=f"call-{len(users)}a-{tag}"),
               1: DeltaToolCall(name="run_command", json_args=json.dumps({"command": f"exit-1 turn {len(users)}"}),
                                tool_call_id=f"call-{len(users)}b-{tag}")}
    else:
        command = f"print-long-output turn {len(users)}" if compacting else f"echo turn {len(users)}"
        # A unique id: after a compaction the turn count starts again, and an id reused from an earlier run
        # makes an AG-UI client append this call's arguments and result to that run's call.
        yield {0: DeltaToolCall(name="run_command", json_args=json.dumps({"command": command}),
                                tool_call_id=f"call-{len(users)}-{uuid.uuid4().hex[:8]}")}


def fake_embeddings(request: httpx.Request) -> httpx.Response:
    """A draft with "secret" in it lies along the general and the secrets heads' weights; any other against them."""
    heads = {h["id"]: h["weights"] for h in ThreatModel.packaged().heads}
    text = json.loads(request.content)["input"][0].lower()
    sign = 1 if "secret" in text else -1
    embedding = [sign * (g + s) for g, s in zip(heads["general"], heads["secrets"])]
    return httpx.Response(200, json={"data": [{"index": 0, "embedding": embedding}]})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=18100)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--key", default=os.environ.get("SPE_AGENT_API_KEY"),
                    help="bearer key clients must send (default: $SPE_AGENT_API_KEY)")
    ap.add_argument("--run-log", type=Path, help="run log path (default: in a temporary directory)")
    ap.add_argument("--embeddings-url", help="score drafts with this OpenAI-compatible endpoint (its /embeddings, "
                    "key in $SPE_FAKE_EMBEDDINGS_KEY) instead of the scripted embeddings")
    args = ap.parse_args()
    if not args.key:
        ap.error("--key or SPE_AGENT_API_KEY is required")
    tmp = Path(tempfile.mkdtemp(prefix="fake-agent-"))
    run_log = args.run_log or tmp / "runs.jsonl"
    (tmp / "prompt.txt").write_text("You are a scripted test agent.")
    config = Config.model_validate({
        # Placeholder only: the scripted model replaces it and no LLM is called.
        "model": {"provider": "openai_compatible", "name": "scripted", "base_url": "http://llm.invalid/v1"},
        "threat_score": {"enabled": True, **({"base_url": args.embeddings_url} if args.embeddings_url else {})},
        "prompt": {"file": str(tmp / "prompt.txt")},
        "tools": {"sandbox_url": "http://sandbox:8000"},
        "run_log": str(run_log),
        "compaction": {"context_window_tokens": COMPACT_WINDOW},
        # The e2e finds rows by their auto title (sessions.py, auto_title): no model title here. /title answers
        # 404, which the chat UI's title route logs and ignores.
        "title": {"enabled": False},
    })
    secrets = Secrets(agent_api_key=args.key, sandbox_api_key="fake-sandbox-key",
                      llm_api_key=os.environ.get("SPE_FAKE_EMBEDDINGS_KEY", "no-llm") if args.embeddings_url else "no-llm")
    client = SandboxClient("http://sandbox:8000", "fake-sandbox-key",
                           http=httpx.AsyncClient(transport=httpx.MockTransport(fake_sandbox)))
    app = create_app(config, secrets, model_override=FunctionModel(summarise, stream_function=scripted),
                     sandbox_client=client, retry_delay=0.1,
                     threat_http=None if args.embeddings_url else httpx.AsyncClient(transport=httpx.MockTransport(fake_embeddings)))
    print(f"fake agent on http://{args.host}:{args.port}/agent, run log {run_log}", flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
