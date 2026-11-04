"""The Pydantic AI agent: model from config, prompt, sandbox tools."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic_ai import Agent, Tool
from pydantic_ai.models import Model

from .compaction import Compaction, CompactionRun
from .config import CompactionCfg, ModelCfg


@dataclass(frozen=True)
class RunDeps:
    """Per-run dependencies. `session_id` (the AG-UI thread id) becomes the sandbox's X-Session-Id,
    as Open WebUI sends its chat id. `compaction` collects the run's compactions (mutable inside)."""

    session_id: str | None = None
    compaction: CompactionRun = field(default_factory=CompactionRun)


def compose_prompt(base: str, sandbox_prompt: str | None) -> str:
    """Open WebUI v0.11.3 appends the terminal's /system prompt to the system message
    (utils/middleware.py, add_or_update_system_message(..., append=True)) and later prepends the
    model's own prompt (routers/openai.py, apply_system_prompt_to_body), both joined by a newline:
    model prompt first, then the terminal prompt."""
    return f"{base}\n{sandbox_prompt}" if sandbox_prompt else base


def build_model(cfg: ModelCfg, api_key: str) -> Model:
    if cfg.provider == "anthropic":
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        return AnthropicModel(cfg.name, provider=AnthropicProvider(api_key=api_key))
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    return OpenAIChatModel(cfg.name, provider=OpenAIProvider(base_url=cfg.base_url, api_key=api_key))


def build_agent(model: Model, prompt: str | Callable[[], str], tools: list[Tool],
                compaction: CompactionCfg | None = None) -> Agent[RunDeps, str]:
    """`prompt` is the system prompt, or a function returning it; a function is called at the
    start of every run, so a prompt read from a file follows the file without a restart."""
    source = prompt if callable(prompt) else (lambda: prompt)
    capabilities = [Compaction(compaction, source)] if compaction is not None and compaction.enabled else []
    agent: Agent[RunDeps, str] = Agent(model, tools=tools, deps_type=RunDeps, name="spe-agent",
                                       capabilities=capabilities)

    @agent.system_prompt
    def _system_prompt() -> str:
        return source()

    return agent
