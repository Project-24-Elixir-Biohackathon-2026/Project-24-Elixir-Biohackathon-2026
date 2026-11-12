"""A minimal chat client for the tester model: Anthropic Messages or any OpenAI-compatible endpoint.

Standard library only. The key is read from a file and never logged or returned.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

ANTHROPIC_URL = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"


class LLMError(Exception):
    pass


def _key(cfg: dict) -> str:
    path = cfg.get("key_file") or os.environ.get("MATRIX_TESTER_KEY_FILE", "")
    if path:
        with open(path) as f:
            return f.read().strip()
    return os.environ.get("MATRIX_TESTER_KEY", "")


def _post(url: str, headers: dict, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raise LLMError(f"tester model answered HTTP {e.code}: {e.read()[:300].decode(errors='replace')}") from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise LLMError(f"tester model request failed: {type(e).__name__}: {getattr(e, 'reason', e)}") from None


def chat(cfg: dict, system: str, messages: list[dict], max_tokens: int = 600) -> str:
    """One completion. `messages` are [{role: user|assistant, content}], starting with a user turn."""
    api = cfg.get("api", "anthropic")
    model = cfg.get("model")
    if not model:
        raise LLMError("tester: set tester.model")
    key = _key(cfg)
    timeout = float(cfg.get("timeout_s", 120))
    temperature = float(cfg.get("temperature", 0.8))
    if api == "anthropic":
        url = cfg.get("url", ANTHROPIC_URL).rstrip("/") + "/v1/messages"
        data = _post(url, {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION},
                     {"model": model, "system": system, "messages": messages,
                      "max_tokens": max_tokens, "temperature": temperature}, timeout)
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
    if api == "openai":
        url = cfg.get("url", "").rstrip("/")
        if not url:
            raise LLMError("tester: an openai-compatible tester needs tester.url (the base URL, ending in /v1)")
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        data = _post(url + "/chat/completions", headers,
                     {"model": model, "messages": [{"role": "system", "content": system}, *messages],
                      "max_tokens": max_tokens, "temperature": temperature}, timeout)
        try:
            return (data["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError):
            raise LLMError("tester model returned no choices") from None
    raise LLMError(f"tester.api must be anthropic or openai, not {api!r}")
