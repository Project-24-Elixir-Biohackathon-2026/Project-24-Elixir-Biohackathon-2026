"""POST /title: auth, the disabled flag, parsing the model's answer and the run-log line."""
from __future__ import annotations

import json

import pytest
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from spe_agent.title import parse_title
from test_app import AGENT_KEY, AUTH, LLM_KEY, build, log_records, running, until_status


def title_body(thread="t1", messages=None):
    return {"thread_id": thread, "messages": messages or [{"role": "user", "content": "how do I reset my password?"}]}


def answering(text: str):
    def function(messages, info):
        return ModelResponse(parts=[TextPart(text)])

    return FunctionModel(function=function)


async def post_title(client, **kw):
    return await client.post("/title", json=title_body(**kw), headers=AUTH)


# --- auth and the disabled flag ----------------------------------------------------------------

async def test_no_auth_is_401(tmp_path):
    app, _ = build(tmp_path, model=answering('{"title": "Password Reset"}'))
    async with running(app) as c:
        await until_status(c, 200)
        r = await c.post("/title", json=title_body())
    assert r.status_code == 401
    assert AGENT_KEY not in r.text


async def test_no_auth_with_a_bad_body_is_still_401(tmp_path):
    """Auth is checked before the body is parsed: an unauthenticated request with a bad body still gets 401,
    not 422 with the schema's errors."""
    app, _ = build(tmp_path, model=answering('{"title": "Password Reset"}'))
    async with running(app) as c:
        await until_status(c, 200)
        r = await c.post("/title", json={"messages": []})
    assert r.status_code == 401
    assert AGENT_KEY not in r.text


async def test_disabled_is_404(tmp_path):
    app, _ = build(tmp_path, model=answering('{"title": "Password Reset"}'), title={"enabled": False})
    async with running(app) as c:
        await until_status(c, 200)
        r = await post_title(c)
    assert r.status_code == 404


# --- parsing the model's answer -----------------------------------------------------------------

async def test_json_answer(tmp_path):
    app, _ = build(tmp_path, model=answering('{"title": "Password Reset"}'))
    async with running(app) as c:
        await until_status(c, 200)
        r = await post_title(c)
    assert r.status_code == 200
    assert r.json() == {"title": "Password Reset"}


async def test_fenced_json_answer(tmp_path):
    app, _ = build(tmp_path, model=answering('```json\n{"title": "Password Reset"}\n```'))
    async with running(app) as c:
        await until_status(c, 200)
        r = await post_title(c)
    assert r.status_code == 200
    assert r.json() == {"title": "Password Reset"}


async def test_bare_text_answer(tmp_path):
    app, _ = build(tmp_path, model=answering('  "Password Reset"  '))
    async with running(app) as c:
        await until_status(c, 200)
        r = await post_title(c)
    assert r.status_code == 200
    assert r.json() == {"title": "Password Reset"}


async def test_empty_answer_is_422(tmp_path):
    app, _ = build(tmp_path, model=answering('   '))
    async with running(app) as c:
        await until_status(c, 200)
        r = await post_title(c)
    assert r.status_code == 422
    assert "detail" in r.json()


async def test_model_error_is_422(tmp_path):
    def failing(messages, info):
        raise RuntimeError("provider unreachable")

    app, _ = build(tmp_path, model=FunctionModel(function=failing))
    async with running(app) as c:
        await until_status(c, 200)
        r = await post_title(c)
    assert r.status_code == 422
    assert "provider unreachable" in r.json()["detail"]


@pytest.mark.parametrize("raw,title", [
    ('{"title": "Password Reset"}', "Password Reset"),
    ('```json\n{"title": "  Password Reset  "}\n```', "Password Reset"),
    ('`Password Reset`', "Password Reset"),
    ('"Password   Reset"', "Password Reset"),
    ('Password Reset', "Password Reset"),
    ("x" * 200, "x" * 80),
    # prose around JSON, or JSON cut off mid-string: the title field, not the whole raw text
    ('Sure! {"title": "Password Reset"}', "Password Reset"),
    ('{"title": "Password Re', "Password Re"),
    # a fenced non-JSON body: the fenced text, not the fence markers or language tag
    ('```\nPassword Reset\n```', "Password Reset"),
])
def test_parse_title_cases(raw, title):
    assert parse_title(raw) == title


@pytest.mark.parametrize("raw", ["", "   ", '{"title": ""}', '{"title": "   "}',
                                  '{"name": "x"}'])  # JSON-ish but no usable title: no title, not the raw JSON
def test_parse_title_empty(raw):
    assert parse_title(raw) == ""


# --- the run-log line ----------------------------------------------------------------------------

async def test_run_log_line_on_success(tmp_path):
    app, _ = build(tmp_path, model=answering('{"title": "Password Reset"}'))
    async with running(app) as c:
        await until_status(c, 200)
        await post_title(c, thread="thread-9")
    (rec,) = log_records(tmp_path)
    assert rec["type"] == "title"
    assert rec["thread_id"] == "thread-9"
    assert rec["title"] == "Password Reset"
    assert rec["error"] is None
    assert set(rec["usage"]) == {"input_tokens", "output_tokens"}
    assert rec["started"] <= rec["ended"]


async def test_model_error_detail_is_sanitized(tmp_path):
    def failing(messages, info):
        raise RuntimeError(f"401 from provider: invalid x-api-key {LLM_KEY}")

    app, _ = build(tmp_path, model=FunctionModel(function=failing))
    async with running(app) as c:
        await until_status(c, 200)
        r = await post_title(c)
    assert r.status_code == 422
    assert LLM_KEY not in r.text and "[redacted]" in r.json()["detail"]
    # the run log keeps the redacted error too (the raw secret must never be written to disk)
    (rec,) = log_records(tmp_path)
    assert LLM_KEY not in json.dumps(rec)


async def test_run_log_line_on_failure(tmp_path):
    def failing(messages, info):
        raise RuntimeError("boom")

    app, _ = build(tmp_path, model=FunctionModel(function=failing))
    async with running(app) as c:
        await until_status(c, 200)
        await post_title(c)
    (rec,) = log_records(tmp_path)
    assert rec["type"] == "title"
    assert rec["title"] is None
    assert rec["usage"] is None
    assert "boom" in rec["error"]


async def test_long_message_content_is_capped_before_the_prompt(tmp_path):
    seen = []

    def function(messages, info):
        seen.append(messages)
        return ModelResponse(parts=[TextPart('{"title": "Long Message"}')])

    app, _ = build(tmp_path, model=FunctionModel(function=function))
    async with running(app) as c:
        await until_status(c, 200)
        await post_title(c, messages=[{"role": "user", "content": "x" * 5000}])
    prompt = seen[0][0].parts[0].content
    assert len(prompt) < 5000 + 500


async def test_configured_max_tokens_reaches_the_model(tmp_path):
    seen = []

    def function(messages, info):
        seen.append(info)
        return ModelResponse(parts=[TextPart('{"title": "Password Reset"}')])

    app, _ = build(tmp_path, model=FunctionModel(function=function), title={"max_tokens": 17})
    async with running(app) as c:
        await until_status(c, 200)
        await post_title(c)
    assert seen[0].model_settings.get("max_tokens") == 17


async def test_invalid_body_is_422(tmp_path):
    app, _ = build(tmp_path, model=answering('{"title": "Password Reset"}'))
    async with running(app) as c:
        await until_status(c, 200)
        r = await c.post("/title", json={"thread_id": "t1", "messages": []}, headers=AUTH)
    assert r.status_code == 422


async def test_unknown_field_is_422(tmp_path):
    app, _ = build(tmp_path, model=answering('{"title": "Password Reset"}'))
    async with running(app) as c:
        await until_status(c, 200)
        body = {**title_body(), "extra": "nope"}
        r = await c.post("/title", json=body, headers=AUTH)
    assert r.status_code == 422
