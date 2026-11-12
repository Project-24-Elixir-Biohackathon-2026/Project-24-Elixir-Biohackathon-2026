"""Model backends and their configuration (lab_models.py, lab_llm.Generator, threatlab.load_config)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import lab_llm  # noqa: E402
import lab_models  # noqa: E402
import threatlab  # noqa: E402
from fake_openai import FakeOpenAI  # noqa: E402

KEY = "sk-test-0123456789abcdef0123456789abcdef"
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["ok"],
          "properties": {"ok": {"type": "boolean"}}}


@pytest.fixture
def server():
    s = FakeOpenAI()
    yield s
    s.close()


def backend(server, **kw):
    return lab_models.make_backend("litellm", {"backend": "openai-compatible", "base_url": server.url,
                                               "model": "qwen", "api_key": KEY, **kw})


def test_structured_answer_with_json_schema(server):
    server.answers = ['{"ok": true}']
    data, prov = backend(server).call("sys", "user", SCHEMA)
    assert data == {"ok": True}
    headers, body = server.requests[0]
    assert body["response_format"]["type"] == "json_schema"
    assert body["messages"][0]["role"] == "system"
    assert prov["structured_mode"] == "json_schema" and prov["endpoint_host"] == "127.0.0.1"
    assert KEY not in json.dumps(prov)


def test_falls_back_when_response_format_is_rejected(server):
    server.answers = [400, '```json\n{"ok": false}\n```']
    b = backend(server)
    data, prov = b.call("sys", "user", SCHEMA)
    assert data == {"ok": False} and b.mode == "json_object"
    assert server.requests[1][1]["response_format"] == {"type": "json_object"}


def test_retries_once_with_the_validation_errors(server):
    server.answers = ['{"ok": "yes"}', '{"ok": true}']
    data, prov = backend(server).call("sys", "user", SCHEMA)
    assert data == {"ok": True} and prov["attempts"] == 2
    retry = server.requests[1][1]["messages"]
    assert retry[-1]["role"] == "user" and "does not validate" in retry[-1]["content"]


def test_gives_up_after_the_retry(server):
    server.answers = ["not json", "still not"]
    with pytest.raises(RuntimeError, match="did not return valid JSON"):
        backend(server).call("sys", "user", SCHEMA)


def test_refusal(server):
    server.answers = [{"choices": [{"finish_reason": "stop", "message": {"content": "", "refusal": "no"}}]}]
    with pytest.raises(lab_models.Refused):
        backend(server).call("sys", "user", SCHEMA)


def test_wrong_key_is_an_error_without_the_key(server):
    b = backend(server, api_key="sk-wrong-0123456789abcdef0123456789abcdef")
    with pytest.raises(RuntimeError) as e:
        b.call("sys", "user", SCHEMA)
    assert "401" in str(e.value) and "sk-wrong" not in str(e.value)


def test_key_from_env_and_file(server, tmp_path, monkeypatch):
    monkeypatch.setenv("MY_LLM_KEY", KEY)
    server.answers = ['{"ok": true}', '{"ok": true}']
    b = lab_models.make_backend("x", {"backend": "openai-compatible", "base_url": server.url, "model": "m",
                                      "api_key_env": "MY_LLM_KEY"})
    assert b.call("s", "u", SCHEMA)[0] == {"ok": True}
    f = tmp_path / "key"
    f.write_text(KEY + "\n")
    b = lab_models.make_backend("y", {"backend": "openai-compatible", "base_url": server.url, "model": "m",
                                      "api_key_file": str(f)})
    assert b.call("s", "u", SCHEMA)[0] == {"ok": True}
    monkeypatch.delenv("MY_LLM_KEY")
    with pytest.raises(SystemExit, match="MY_LLM_KEY"):
        lab_models.make_backend("z", {"backend": "openai-compatible", "base_url": server.url, "model": "m",
                                      "api_key_env": "MY_LLM_KEY"}).key()


def test_complete_puts_one_system_message_first(server):
    server.answers = ["hello"]
    text, _ = backend(server).complete([{"role": "user", "content": "a"}, {"role": "system", "content": "s"},
                                        {"role": "assistant", "content": "b"}, {"role": "user", "content": "c"}],
                                       json_mode=True)
    msgs = server.requests[0][1]["messages"]
    assert text == "hello" and msgs[0] == {"role": "system", "content": "s"}
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
    assert server.requests[0][1]["response_format"] == {"type": "json_object"}


def test_generator_routes_roles_and_guards_paid(server):
    models = {"default": {"backend": "claude-code", "model": "haiku"},
              "litellm": {"backend": "openai-compatible", "base_url": server.url, "model": "qwen", "api_key": KEY}}
    g = lab_llm.Generator(models=models, roles={"judge": "litellm"})
    assert g.backend("proposer").kind == "claude-code" and g.backend("judge").kind == "openai-compatible"
    with pytest.raises(lab_models.PaidNotAllowed):
        g.judge("threat", {"title": "t", "message": "m", "indicators": []}, {"answer": "a", "tool_calls": []})
    assert not server.requests
    server.answers = ['{"reproduced": false, "confidence": "high", "reason": "no"}']
    g = lab_llm.Generator(models=models, roles={"judge": "litellm"}, allow_paid=True)
    j, prov = g.judge("threat", {"title": "t", "message": "m", "indicators": []}, {"answer": "a", "tool_calls": []})
    assert j["reproduced"] is False and prov["role"] == "judge"


def test_generator_rejects_unknown_roles_and_models():
    with pytest.raises(SystemExit):
        lab_llm.Generator(models={"default": {}}, roles={"jduge": "default"})
    with pytest.raises(SystemExit):
        lab_llm.Generator(models={"default": {}}, roles={"judge": "nope"})


def test_old_generator_block_still_works(tmp_path):
    p = tmp_path / "lab.yaml"
    p.write_text("generator: {model: sonnet, timeout_s: 60}\n")
    cfg = threatlab.load_config(p)
    assert cfg["models"]["default"] == {"backend": "claude-code", "model": "sonnet", "timeout_s": 60}
    g = lab_llm.Generator(**threatlab.gen_kwargs(cfg))
    assert g.backend("judge").describe() == "claude-code sonnet"


def test_inline_key_needs_an_ignored_config(tmp_path, monkeypatch):
    p = tmp_path / "lab.yaml"
    p.write_text(f"models:\n  litellm: {{backend: openai-compatible, base_url: http://x/v1, model: m, api_key: {KEY}}}\n")
    calls = []
    monkeypatch.setattr(threatlab, "ensure_ignored", lambda path: calls.append(path))
    threatlab.load_config(p)
    assert calls == [p]
    monkeypatch.setattr(threatlab, "ensure_ignored", lambda path: (_ for _ in ()).throw(SystemExit("not ignored")))
    with pytest.raises(SystemExit):
        threatlab.load_config(p)


def test_role_table_never_shows_the_key(server):
    cfg = {"models": {"default": {"backend": "claude-code", "model": "haiku"},
                      "litellm": {"backend": "openai-compatible", "base_url": server.url, "model": "qwen",
                                  "api_key": KEY}}, "roles": {"judge": "litellm"}}
    t = threatlab.role_table(cfg)
    assert "judge" in t and "[paid]" in t and KEY not in t


def test_claude_code_backend_command(monkeypatch):
    seen = {}

    def fake_run(cmd, input, capture_output, text, cwd, env, timeout):
        seen["cmd"], seen["env"] = cmd, env
        out = {"subtype": "success", "result": "plain text", "structured_output": {"ok": True}, "usage": {}}
        return subprocess.CompletedProcess(cmd, 0, json.dumps(out), "")

    monkeypatch.setattr(lab_models.shutil, "which", lambda _: "/bin/claude")
    monkeypatch.setattr(lab_models.subprocess, "run", fake_run)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-not-pass")
    b = lab_models.make_backend("default", {"backend": "claude-code", "model": "haiku"})
    assert b.call("s", "u", SCHEMA)[0] == {"ok": True}
    assert "--json-schema" in seen["cmd"] and "ANTHROPIC_API_KEY" not in seen["env"]
    assert seen["cmd"][seen["cmd"].index("--tools") + 1] == ""
    text, _ = b.complete([{"role": "system", "content": "s"}, {"role": "user", "content": "u"}])
    assert text == "plain text" and "--json-schema" not in seen["cmd"]
