"""POST /title: a short, model-written title for a chat, from its first one or two messages.

One tool-free model request (as `Compaction._summary_request` does), with the configured model and
`title.max_tokens`. The prompt, adapted from Open WebUI 0.11.3's `DEFAULT_TITLE_GENERATION_PROMPT_TEMPLATE`
(`title_prompt.md`), asks for a 2-4 word title as JSON; the answer is parsed leniently (JSON, fenced JSON,
or bare text) and every call is logged via the same `RunLog` as `/agent` runs, with its own `type` so a
run-log reader can tell the two apart.
"""
from __future__ import annotations

import json
import re
import time
from importlib.resources import files
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.messages import ModelRequest, TextPart, UserPromptPart
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.settings import ModelSettings

from .config import TitleCfg

TITLE_PROMPT = files("spe_agent").joinpath("title_prompt.md").read_text()
MAX_CONTENT_CHARS = 2000  # each message's content, before it reaches the prompt
MAX_TITLE_CHARS = 80
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_TITLE_FIELD = re.compile(r'"title"\s*:\s*"((?:[^"\\]|\\.)*)')


class TitleMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str


class TitleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thread_id: str
    messages: list[TitleMessage] = Field(min_length=1, max_length=2)


def _cap(content: str) -> str:
    return content if len(content) <= MAX_CONTENT_CHARS else content[:MAX_CONTENT_CHARS] + " […]"


def _render(messages: list[TitleMessage]) -> str:
    return "\n".join(f"{m.role.upper()}: {_cap(m.content)}" for m in messages)


def _prompt(messages: list[TitleMessage]) -> str:
    return TITLE_PROMPT.replace("{{CHAT_HISTORY}}", _render(messages))


def _clean(text: str) -> str:
    text = text.strip().strip("`'\" ")
    return re.sub(r"\s+", " ", text).strip()[:MAX_TITLE_CHARS]


def parse_title(raw: str) -> str:
    """The model's answer: JSON `{"title": ...}`, in a ``` fence or not, prose around the JSON, JSON cut off
    mid-string, or else the bare text. JSON-ish with no usable title in it answers "" (422), not the raw JSON."""
    text = raw.strip()
    fence = _FENCE.search(text)
    body = fence.group(1).strip() if fence else text
    try:
        data = json.loads(body)
    except ValueError:
        data = None
    if isinstance(data, dict) and isinstance(data.get("title"), str):
        return _clean(data["title"])
    field = _TITLE_FIELD.search(body)  # JSON inside prose, or cut off mid-string
    if field:
        return _clean(field.group(1))
    if "{" in body:  # JSON-ish but no title in it: no usable title (422)
        return ""
    return _clean(body)


async def generate_title(model: Model, cfg: TitleCfg, body: TitleRequest) -> tuple[str | None, dict]:
    """Returns the title (or None on failure) and the run-log record for the call."""
    started = time.time()
    title: str | None = None
    usage: dict[str, int] | None = None
    error: str | None = None
    try:
        messages = [ModelRequest(parts=[UserPromptPart(_prompt(body.messages))])]
        response = await model.request(messages, ModelSettings(max_tokens=cfg.max_tokens), ModelRequestParameters())
        usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
        raw = "".join(p.content for p in response.parts if isinstance(p, TextPart))
        cleaned = parse_title(raw)
        if cleaned:
            title = cleaned
        else:
            error = "the model returned an empty title"
    except Exception as e:  # any model failure becomes a 422, not a 500
        error = str(e) or type(e).__name__
    record = {"type": "title", "thread_id": body.thread_id, "started": started, "ended": time.time(),
              "title": title, "usage": usage, "error": error}
    return title, record
