"""The airlock in the AG-UI stream (L5): off, text streams as before; on, each text message goes out once,
redacted, at its end. A scripted FunctionModel stands in for the LLM; all values are synthetic."""
from __future__ import annotations

import httpx
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from spe_agent.app import create_app
from spe_agent.sandbox import SandboxClient
from test_app import SANDBOX, SANDBOX_KEY, SECRETS, FakeSandbox, config, log_records, post_run, running, until_status

# A study id and a sensitive path, each split across chunks.
CHUNKS = ["Found STU", "DY-0042 in /data-share/sens", "itive/registry/participants.csv", ". Done."]
REDACTED = "Found [redacted:study_id] in [redacted:sensitive_path]. Done."


def chunked_answer(chunks=CHUNKS, fail=False):
    """Calls run_command once, then streams `chunks` as the answer (and fails after them if `fail`)."""

    async def stream(messages, info):
        if not isinstance(messages[-1].parts[-1], ToolReturnPart):
            yield {0: DeltaToolCall(name="run_command", json_args='{"command": "ls"}', tool_call_id="call-1")}
            return
        for chunk in chunks:
            yield chunk
        if fail:
            raise RuntimeError("peer closed connection")

    return FunctionModel(stream_function=stream)


async def run(tmp_path, model, airlock_prefix):
    client = SandboxClient(SANDBOX, SANDBOX_KEY, http=httpx.AsyncClient(transport=httpx.MockTransport(FakeSandbox())))
    app = create_app(config(tmp_path), SECRETS, model_override=model, sandbox_client=client, retry_delay=0.01,
                     probe_interval=0.05, airlock_prefix=airlock_prefix)
    async with running(app) as c:
        await until_status(c, 200)
        return await post_run(c)


def contents(evs):
    return [e["delta"] for e in evs if e["type"] == "TEXT_MESSAGE_CONTENT"]


async def test_off_streams_the_chunks_unchanged(tmp_path):
    assert contents(await run(tmp_path, chunked_answer(), airlock_prefix=None)) == CHUNKS


async def test_on_emits_one_redacted_delta_before_the_message_end(tmp_path):
    evs = await run(tmp_path, chunked_answer(), airlock_prefix="STUDY")
    assert contents(evs) == [REDACTED]
    types = [e["type"] for e in evs]
    at = types.index("TEXT_MESSAGE_CONTENT")
    assert types[at - 1] == "TEXT_MESSAGE_START" and types[at + 1] == "TEXT_MESSAGE_END"
    assert "TOOL_CALL_RESULT" in types and types[-1] == "RUN_FINISHED"


async def test_on_leaves_a_benign_answer_unchanged(tmp_path):
    evs = await run(tmp_path, chunked_answer(["The workflow ", "finished: 3 reads."]), airlock_prefix="STUDY")
    assert contents(evs) == ["The workflow finished: 3 reads."]


async def test_on_flushes_a_cut_message_redacted_before_run_error(tmp_path):
    evs = await run(tmp_path, chunked_answer(CHUNKS[:2], fail=True), airlock_prefix="STUDY")
    assert contents(evs) == ["Found [redacted:study_id] in /data-share/sens"]
    types = [e["type"] for e in evs]
    assert types[-1] == "RUN_ERROR" and types.index("TEXT_MESSAGE_CONTENT") < types.index("RUN_ERROR")


async def test_run_log_holds_the_redacted_answer(tmp_path):
    await run(tmp_path, chunked_answer(), airlock_prefix="STUDY")
    (rec,) = log_records(tmp_path)
    assert rec["answer"] == REDACTED


async def test_on_releases_each_message_before_the_next_tool_call(tmp_path):
    """Text, then a tool call in the same response, then the answer: each message goes out redacted between
    its own START and END, the first before TOOL_CALL_START (a guard against an adapter upgrade)."""

    async def stream(messages, info):
        if not isinstance(messages[-1].parts[-1], ToolReturnPart):
            yield "Checking STU"
            yield "DY-0007 first."
            yield {0: DeltaToolCall(name="run_command", json_args='{"command": "ls"}', tool_call_id="call-1")}
            return
        yield "Done with STUDY-0007."

    evs = await run(tmp_path, FunctionModel(stream_function=stream), airlock_prefix="STUDY")
    assert contents(evs) == ["Checking [redacted:study_id] first.", "Done with [redacted:study_id]."]
    text = [e for e in evs if e["type"].startswith("TEXT_MESSAGE_")]
    assert [e["type"] for e in text] == ["TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT", "TEXT_MESSAGE_END"] * 2
    for start, content, end in (text[:3], text[3:]):
        assert start["messageId"] == content["messageId"] == end["messageId"]
    types = [e["type"] for e in evs]
    assert types.index("TEXT_MESSAGE_END") < types.index("TOOL_CALL_START")
