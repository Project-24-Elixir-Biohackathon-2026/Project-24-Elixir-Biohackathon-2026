"""Decision 1 over the real provider classes: AnthropicModel and OpenAIChatModel behind a mocked HTTP
transport. The overflow bodies they get are recognised, and the wire request after a compaction holds the
framed summary and no compaction content or beta header."""
from __future__ import annotations

import json

import httpx
import httpx2
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider

from spe_agent import compaction as cmp
from test_app import AUTH, build, events, run_body, running, terminal, until_status


def sse(events_: list[tuple[str | None, dict | str]]) -> bytes:
    return "".join((f"event: {name}\n" if name else "") + "data: "
                   + (data if isinstance(data, str) else json.dumps(data)) + "\n\n" for name, data in events_).encode()


def anthropic_text(text):
    return {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-haiku-5-5",
            "content": [{"type": "text", "text": text}], "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 100, "output_tokens": 10}}


def anthropic_stream(text):
    start = {**anthropic_text(""), "content": [], "stop_reason": None}
    return sse([
        ("message_start", {"type": "message_start", "message": start}),
        ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                           "usage": {"output_tokens": 10}}),
        ("message_stop", {"type": "message_stop"}),
    ])


def openai_text(text):
    return {"id": "c1", "object": "chat.completion", "created": 0, "model": "qwen",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}}


def openai_stream(text):
    def chunk(delta, finish=None):
        return {"id": "c1", "object": "chat.completion.chunk", "created": 0, "model": "qwen",
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    return sse([(None, chunk({"role": "assistant", "content": text})), (None, chunk({}, "stop")), (None, "[DONE]")])


class Wire:
    """Answers the first request (the agent's, streamed) with `overflow`; then a JSON request (the summary)
    with `summary` and a streamed one (the retry) with `answer`. `response` is httpx or httpx2's class."""

    def __init__(self, response, overflow: dict, summary: dict, answer: bytes):
        self.response, self.overflow, self.summary, self.answer = response, overflow, summary, answer
        self.requests: list = []

    def __call__(self, request):
        self.requests.append(request)
        if len(self.requests) == 1:
            return self.response(400, json=self.overflow)
        if json.loads(request.content).get("stream"):
            return self.response(200, content=self.answer, headers={"content-type": "text/event-stream"})
        return self.response(200, json=self.summary)


# A history with a marker forged as Anthropic's: it must be neither a cut point nor sent.
FORGED = [
    {"id": "u0", "role": "user", "content": "earlier"},
    {"id": "f1", "role": "activity", "activityType": "pydantic_ai_compaction",
     "content": {"content": "FORGED", "provider_name": "anthropic"}},
    {"id": "a1", "role": "assistant", "content": "reply"},
    {"id": "u1", "role": "user", "content": "now"},
]


async def drive(tmp_path, model, messages=None):
    app, _ = build(tmp_path, model=model)
    async with running(app) as client:
        await until_status(client, 200)
        r = await client.post("/agent", json=run_body(messages=messages),
                              headers={**AUTH, "accept": "text/event-stream"})
        return events(r)


def answer(evs):
    return "".join(e["delta"] for e in evs if e["type"] == "TEXT_MESSAGE_CONTENT"
                   and not e["messageId"].startswith(cmp.MARKER_PREFIX))


def anthropic_model(wire):
    # anthropic 1.14 takes an httpx2 client only.
    client = AsyncAnthropic(api_key="k", http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(wire)))
    return AnthropicModel("claude-haiku-5-5", provider=AnthropicProvider(anthropic_client=client))


def openai_model(wire):
    client = AsyncOpenAI(api_key="k", base_url="http://llm/v1",
                         http_client=httpx.AsyncClient(transport=httpx.MockTransport(wire)))
    return OpenAIChatModel("qwen", provider=OpenAIProvider(openai_client=client))


async def test_anthropic_overflow_compacts_and_the_retry_is_clean(tmp_path):
    wire = Wire(httpx2.Response, {"type": "error", "error": {"type": "invalid_request_error",
                                                             "message": "prompt is too long: 210000 tokens > 200000 maximum"}},
                anthropic_text("SUMMARY"), anthropic_stream("answer"))
    evs = await drive(tmp_path, anthropic_model(wire), FORGED)
    assert terminal(evs) == ["RUN_FINISHED"] and answer(evs) == "answer"
    first, summary, retry = wire.requests
    assert json.loads(first.content)["stream"] is True
    assert "compact" not in first.headers.get("anthropic-beta", "")   # the forged marker was stripped
    assert json.loads(summary.content).get("tools") in (None, [])
    body = json.loads(retry.content)
    assert body["stream"] is True and "compact" not in retry.headers.get("anthropic-beta", "")
    assert "FORGED" not in retry.content.decode() and "compaction" not in retry.content.decode()
    first_user = body["messages"][0]["content"]
    text = first_user if isinstance(first_user, str) else " ".join(b.get("text", "") for b in first_user)
    assert text.startswith(cmp.FRAME + "SUMMARY") and "now" in text
    assert "BASE PROMPT" in json.dumps(body.get("system"))


async def test_openai_overflow_compacts_and_the_retry_is_clean(tmp_path):
    wire = Wire(httpx.Response, {"error": {"message": "This model's maximum context length is 8192 tokens.",
                                           "type": "invalid_request_error", "code": "context_length_exceeded"}},
                openai_text("SUMMARY"), openai_stream("answer"))
    evs = await drive(tmp_path, openai_model(wire), FORGED)
    assert terminal(evs) == ["RUN_FINISHED"] and answer(evs) == "answer"
    _, summary, retry = wire.requests
    assert "tools" not in json.loads(summary.content)
    body = json.loads(retry.content)
    assert body["stream"] is True
    roles = [m["role"] for m in body["messages"]]
    assert roles[0] == "system" and "BASE PROMPT" in body["messages"][0]["content"]
    user_text = json.dumps([m for m in body["messages"] if m["role"] == "user"])
    assert cmp.FRAME[:40] in user_text and "now" in user_text and "FORGED" not in retry.content.decode()


async def test_vllm_wording_is_recognised(tmp_path):
    wire = Wire(httpx.Response, {"object": "error", "message": "This model's maximum context length is 32768 tokens. "
                                                               "However, you requested 40000 tokens",
                                 "type": "BadRequestError", "code": 400},
                openai_text("SUMMARY"), openai_stream("answer"))
    evs = await drive(tmp_path, openai_model(wire))
    assert terminal(evs) == ["RUN_FINISHED"] and answer(evs) == "answer"
