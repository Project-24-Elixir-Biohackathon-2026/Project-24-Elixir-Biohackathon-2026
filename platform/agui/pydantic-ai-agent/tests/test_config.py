from pathlib import Path

import pytest
import yaml

from spe_agent.config import CompactionCfg, ConfigError, load_config, load_secrets

VALID = {
    "model": {"provider": "openai_compatible", "name": "qwen3.8-27b", "base_url": "https://llm.example/v1"},
    "prompt": {"file": "/etc/spe-agent/system_prompt.txt"},
    "tools": {"sandbox_url": "http://sandbox:8000"},
}


def write(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "agent.yaml"
    p.write_text(yaml.safe_dump(data))
    return p


def test_valid_config_loads_with_defaults(tmp_path):
    cfg = load_config(write(tmp_path, VALID))
    assert cfg.tools.surface == "shell"
    assert cfg.tools.sandbox_operations == "all"
    assert cfg.tools.max_output_bytes == 16384
    lim = cfg.limits.usage_limits()
    assert (lim.request_limit, lim.tool_calls_limit, lim.total_tokens_limit) == (50, 100, None)


def test_total_tokens_limit_can_be_set(tmp_path):
    cfg = load_config(write(tmp_path, {**VALID, "limits": {"total_tokens_limit": 400000}}))
    assert cfg.limits.usage_limits().total_tokens_limit == 400000


def test_unknown_key_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="tool"):
        load_config(write(tmp_path, {**VALID, "tool": {}}))


def test_typed_surface_is_reserved(tmp_path):
    data = {**VALID, "tools": {**VALID["tools"], "surface": "typed"}}
    with pytest.raises(ConfigError, match="reserved"):
        load_config(write(tmp_path, data))


def test_any_anthropic_model_without_a_guard(tmp_path):
    data = {**VALID, "model": {"provider": "anthropic", "name": "claude-opus-5"}}
    cfg = load_config(write(tmp_path, data))
    assert cfg.model.name == "claude-opus-5" and cfg.model.allowed_models is None


@pytest.mark.parametrize("model", [
    {"provider": "anthropic", "name": "claude-opus-5"},
    {"provider": "openai_compatible", "name": "gpt-big", "base_url": "https://llm.example/v1"},
])
def test_allowed_models_rejects_others_for_any_provider(tmp_path, model):
    data = {**VALID, "model": {**model, "allowed_models": ["claude-haiku-5-5", "qwen3.8-27b"]}}
    with pytest.raises(ConfigError, match="allowed_models"):
        load_config(write(tmp_path, data))


def test_allowed_models_accepts_a_listed_model(tmp_path):
    data = {**VALID, "model": {"provider": "anthropic", "name": "claude-haiku-5-5",
                               "allowed_models": ["claude-haiku-5-5"]}}
    assert load_config(write(tmp_path, data)).model.name == "claude-haiku-5-5"


def test_empty_allowed_models_is_an_error(tmp_path):
    data = {**VALID, "model": {**VALID["model"], "allowed_models": []}}
    with pytest.raises(ConfigError, match="allowed_models"):
        load_config(write(tmp_path, data))


def test_openai_compatible_needs_base_url(tmp_path):
    data = {**VALID, "model": {"provider": "openai_compatible", "name": "qwen3.8-27b"}}
    with pytest.raises(ConfigError, match="base_url"):
        load_config(write(tmp_path, data))


def test_secrets_by_provider(tmp_path):
    cfg = load_config(write(tmp_path, VALID))
    env = {"SPE_AGENT_API_KEY": "a", "SANDBOX_API_KEY": "s", "OPENAI_API_KEY": "o"}
    sec = load_secrets(cfg, env)
    assert (sec.agent_api_key, sec.sandbox_api_key, sec.llm_api_key) == ("a", "s", "o")
    assert sorted(sec.values()) == ["a", "o", "s"]


def test_missing_secret_names_the_variable(tmp_path):
    cfg = load_config(write(tmp_path, {**VALID, "model": {"provider": "anthropic", "name": "claude-haiku-5-5"}}))
    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
        load_secrets(cfg, {"SPE_AGENT_API_KEY": "a", "SANDBOX_API_KEY": "s"})


@pytest.mark.parametrize("section,key", [("limits", "request_limit"), ("limits", "tool_calls_limit"),
                                         ("limits", "total_tokens_limit"), ("tools", "max_output_bytes")])
@pytest.mark.parametrize("value", [0, -1])
def test_caps_must_be_positive(tmp_path, section, key, value):
    data = {**VALID, section: {**VALID.get(section, {}), key: value}}
    with pytest.raises(ConfigError, match=key):
        load_config(write(tmp_path, data))


def test_compaction_defaults(tmp_path):
    cfg = load_config(write(tmp_path, VALID))
    assert cfg.compaction == CompactionCfg(enabled=True, context_window_tokens=None, trigger_ratio=0.8,
                                           summary_max_tokens=4096)


def test_compaction_values(tmp_path):
    data = {**VALID, "compaction": {"enabled": False, "context_window_tokens": 20000, "trigger_ratio": 0.5,
                                    "summary_max_tokens": 1000}}
    cfg = load_config(write(tmp_path, data))
    assert (cfg.compaction.enabled, cfg.compaction.context_window_tokens, cfg.compaction.trigger_ratio,
            cfg.compaction.summary_max_tokens) == (False, 20000, 0.5, 1000)


@pytest.mark.parametrize("bad", [{"trigger_ratio": 0}, {"trigger_ratio": 1}, {"trigger_ratio": 1.5},
                                 {"context_window_tokens": 0}, {"summary_max_tokens": 0}, {"window": 1000}])
def test_compaction_refused(tmp_path, bad):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {**VALID, "compaction": bad}))
