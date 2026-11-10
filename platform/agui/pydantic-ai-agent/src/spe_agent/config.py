"""agent.yaml (rendered by Ansible) and the secrets from the environment."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, PositiveInt, ValidationError, model_validator
from pydantic_ai.usage import UsageLimits

class ConfigError(Exception):
    pass


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelCfg(_Strict):
    provider: Literal["openai_compatible", "anthropic"] = "openai_compatible"
    name: str
    base_url: str | None = None
    # Optional guard, for any provider: when set, only these model names are accepted, so a
    # typo cannot select a pricier model (the development VM pins claude-haiku-5-5 this way).
    allowed_models: list[str] | None = None

    @model_validator(mode="after")
    def _check(self) -> "ModelCfg":
        if self.allowed_models is not None:
            if not self.allowed_models:
                raise ValueError("model.allowed_models is empty: leave it out to allow any model")
            if self.name not in self.allowed_models:
                raise ValueError(f"model.name {self.name!r} is not in model.allowed_models "
                                 f"({', '.join(self.allowed_models)})")
        if self.provider == "openai_compatible" and not self.base_url:
            raise ValueError("openai_compatible provider needs model.base_url")
        return self


class PromptCfg(_Strict):
    file: Path
    include_sandbox_prompt: bool = True


class ToolsCfg(_Strict):
    surface: Literal["shell", "typed"] = "shell"
    sandbox_url: str
    sandbox_operations: Literal["all"] | list[str] = "all"
    max_output_bytes: PositiveInt = 16384

    @model_validator(mode="after")
    def _check(self) -> "ToolsCfg":
        if self.surface == "typed":
            raise ValueError("tools.surface 'typed' is reserved and not implemented yet; use 'shell'")
        return self


class LimitsCfg(_Strict):
    request_limit: PositiveInt = 50
    tool_calls_limit: PositiveInt = 100
    # Off by default: it sums every request's tokens in a run, and each request resends the whole
    # conversation, so a long chat hits it while Open WebUI, which has no such cap, does not.
    total_tokens_limit: PositiveInt | None = None

    def usage_limits(self) -> UsageLimits:
        return UsageLimits(request_limit=self.request_limit, tool_calls_limit=self.tool_calls_limit,
                           total_tokens_limit=self.total_tokens_limit)


class CompactionCfg(_Strict):
    enabled: bool = True
    # The model's context window in tokens. Unset: only a provider's "too long" error compacts.
    context_window_tokens: PositiveInt | None = None
    trigger_ratio: float = Field(0.8, gt=0, lt=1)
    summary_max_tokens: PositiveInt = 4096


class TitleCfg(_Strict):
    enabled: bool = True
    # Room for a reasoning model to think first: qwen3.8-27b spends ~120 tokens before a ~13-token title.
    max_tokens: PositiveInt = 1024


class GuardCfg(_Strict):
    # No bare `off`: YAML reads an unquoted off as false, and a mode must never turn into another.
    mode: Literal["disabled", "observe", "enforce"] = "disabled"
    # The shared canary matcher, loaded by path (platform/canary_check/canary_check.py; the image
    # carries a copy at this path, and the instance mounts the clone's file over it).
    matcher: Path = Path("/app/matcher/canary_check.py")
    # The hand-off's hash-only manifest: digests and types, never a plaintext canary.
    manifest: Path = Path("/etc/spe-agent/canaries/canaries.manifest.sha256")
    # Study ids are part of the DRS file names the agent must use.
    exempt_types: list[str] = ["registry-study-id"]
    # File names no analysis needs (the instance's masked files): denied in a tool call,
    # redacted in a tool result, recorded in the agent's own text.
    sensitive_names: list[str] = []

    @model_validator(mode="after")
    def _check(self) -> "GuardCfg":
        spaced = [n for n in self.sensitive_names if not n or any(c.isspace() for c in n)]
        if spaced:
            raise ValueError(f"guard.sensitive_names must be non-empty and hold no whitespace: {spaced}")
        return self


class Config(_Strict):
    model: ModelCfg
    prompt: PromptCfg
    tools: ToolsCfg
    limits: LimitsCfg = LimitsCfg()
    compaction: CompactionCfg = CompactionCfg()
    title: TitleCfg = TitleCfg()
    guard: GuardCfg = GuardCfg()
    run_log: Path = Path("/var/lib/spe-agent/runs.jsonl")


class Secrets(BaseModel):
    agent_api_key: str
    sandbox_api_key: str
    llm_api_key: str

    def values(self) -> list[str]:
        return [self.agent_api_key, self.sandbox_api_key, self.llm_api_key]


def load_config(path: Path) -> Config:
    try:
        data = yaml.safe_load(Path(path).read_text()) or {}
        return Config.model_validate(data)
    except (OSError, yaml.YAMLError, ValidationError) as e:
        raise ConfigError(f"{path}: {e}") from e


def load_secrets(cfg: Config, environ: Mapping[str, str]) -> Secrets:
    llm_var = "ANTHROPIC_API_KEY" if cfg.model.provider == "anthropic" else "OPENAI_API_KEY"
    names = {"agent_api_key": "SPE_AGENT_API_KEY", "sandbox_api_key": "SANDBOX_API_KEY", "llm_api_key": llm_var}
    missing = [var for var in names.values() if not environ.get(var)]
    if missing:
        raise ConfigError(f"missing environment variables: {', '.join(missing)}")
    return Secrets(**{field: environ[var] for field, var in names.items()})
