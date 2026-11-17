"""Model backends: the only code in threatlab that talks to a model.

Two backends, one interface:

    call(system, user, schema) -> (data, provenance)     structured answer, validated against `schema`
    complete(messages, json_mode=False) -> (text, provenance)   plain completion (promptfoo's attacker/grader)

* ``claude-code``: Claude Code in headless mode (``claude -p``) on its own login: no API key, no API
  bill. It runs with no tools, no MCP servers and no settings, in an empty temporary directory, with
  the Anthropic API-key variables removed from its environment: it can only write text.
* ``openai-compatible``: any ``/v1/chat/completions`` endpoint (the team's LiteLLM, vLLM, Ollama,
  OpenAI), over the standard library. The key comes from the config (``api_key``), an environment
  variable (``api_key_env``) or a file (``api_key_file``) and is sent only in the Authorization
  header: it never appears in provenance, errors or anything written to disk.

Which backend a role uses is configured in lab.yaml (``models:``, ``roles:``); see lab_llm.Generator.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

BACKENDS = ("claude-code", "openai-compatible")


class Refused(Exception):
    """The model refused; the payload is the call's provenance as JSON."""


class PaidNotAllowed(SystemExit):
    """A role would call a paid backend without --allow-paid-models."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def parse_json(text: str):
    """The JSON object in a model's answer: bare, or inside a ``` fence, or the outermost {...}."""
    t = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    try:
        return json.loads(t)
    except ValueError:
        start, end = t.find("{"), t.rfind("}")
        if start >= 0 and end > start:
            return json.loads(t[start:end + 1])
        raise


def schema_errors(data, schema: dict) -> list[str]:
    import jsonschema
    v = jsonschema.Draft202012Validator(schema)
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '(root)'}: {e.message}"[:300]
            for e in sorted(v.iter_errors(data), key=lambda e: list(e.absolute_path))][:20]


def flatten(messages: list[dict]) -> tuple[str, str]:
    """(system, user) from a chat: system messages joined; a single user turn as is, else a transcript."""
    system = "\n\n".join(str(m.get("content") or "") for m in messages if m.get("role") == "system")
    rest = [m for m in messages if m.get("role") != "system"]
    if len(rest) == 1 and rest[0].get("role") == "user":
        return system, str(rest[0].get("content") or "")
    turns = "\n\n".join(f"<turn role=\"{m.get('role')}\">\n{m.get('content') or ''}\n</turn>" for m in rest)
    return system, f"<conversation>\n{turns}\n</conversation>\n\nWrite the next assistant turn."


class ClaudeCodeBackend:
    kind = "claude-code"

    def __init__(self, name: str = "default", model: str = "haiku", timeout_s: float = 900, paid: bool = False, **_):
        self.name, self.model, self.timeout_s, self.paid = name, model, float(timeout_s), bool(paid)
        self._claude = None

    def describe(self) -> str:
        return f"claude-code {self.model}"

    def _bin(self) -> str:
        if not self._claude:
            self._claude = shutil.which("claude")
            if not self._claude:
                raise SystemExit("the claude CLI (Claude Code) is not on PATH: install it, or give this role "
                                 "an openai-compatible model in lab.yaml")
        return self._claude

    def _run(self, system: str, user: str, schema: dict | None) -> tuple[dict, dict]:
        env = {k: v for k, v in os.environ.items()
               if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL")}
        cmd = [self._bin(), "-p", "--output-format", "json"]
        if schema is not None:
            cmd += ["--json-schema", json.dumps(schema)]
        cmd += ["--system-prompt", system or "You are a helpful assistant.", "--model", self.model, "--tools", "",
                "--strict-mcp-config", "--setting-sources", "", "--no-session-persistence"]
        with tempfile.TemporaryDirectory(prefix="threatlab-gen-") as cwd:
            p = subprocess.run(cmd, input=user, capture_output=True, text=True, cwd=cwd, env=env,
                               timeout=self.timeout_s)
        try:
            out = json.loads(p.stdout)
        except ValueError:
            raise RuntimeError(f"claude -p failed (exit {p.returncode}): {(p.stderr or p.stdout)[-800:]}")
        prov = {"generator": "claude-code", "backend": self.name,
                "model": ",".join(out.get("modelUsage") or {}) or self.model,
                "session_id": out.get("session_id"), "when": _now(),
                "prompt_sha256": _sha((system or "") + "\n\n" + user),
                "stop_reason": out.get("stop_reason"), "usage": out.get("usage") or {},
                "list_price_usd": out.get("total_cost_usd")}  # notional: billed to the Claude Code plan, not an API key
        if out.get("stop_reason") == "refusal" or out.get("safety_stops"):
            raise Refused(json.dumps(prov))
        if out.get("is_error") or out.get("subtype") != "success":
            raise RuntimeError(f"claude -p failed: {out.get('subtype')} {str(out.get('result'))[:500]}")
        return out, prov

    def call(self, system: str, user: str, schema: dict) -> tuple[dict, dict]:
        out, prov = self._run(system, user, schema)
        if out.get("structured_output") is None:
            raise RuntimeError(f"claude -p did not return structured output: {str(out.get('result'))[:500]}")
        return out["structured_output"], prov

    def complete(self, messages: list[dict], json_mode: bool = False) -> tuple[str, dict]:
        system, user = flatten(messages)
        if json_mode:
            system += "\n\nAnswer with one JSON object and nothing else."
        out, prov = self._run(system, user, None)
        return str(out.get("result") or ""), prov


class OpenAICompatBackend:
    kind = "openai-compatible"
    MODES = ("json_schema", "json_object", "prompt")  # how a structured answer is asked for, best first

    def __init__(self, name: str, base_url: str = "", model: str = "", api_key: str | None = None,
                 api_key_env: str | None = None, api_key_file: str | None = None, timeout_s: float = 300,
                 paid: bool = True, temperature: float | None = None, max_tokens: int | None = None, **_):
        if not base_url or not model:
            raise SystemExit(f"model {name!r}: an openai-compatible backend needs base_url and model")
        self.name, self.base_url, self.model = name, base_url.rstrip("/"), model
        self.timeout_s, self.paid = float(timeout_s), bool(paid)
        self.temperature, self.max_tokens = temperature, max_tokens
        self._key_spec = {"api_key": api_key, "api_key_env": api_key_env, "api_key_file": api_key_file}
        self._key: str | None = None
        self.mode = "json_schema"

    def describe(self) -> str:
        return f"openai-compatible {self.model} @ {urlparse(self.base_url).hostname}"

    def key(self) -> str | None:
        if self._key is None:
            s = self._key_spec
            if s["api_key"]:
                self._key = str(s["api_key"])
            elif s["api_key_env"]:
                self._key = os.environ.get(s["api_key_env"]) or None
                if not self._key:
                    raise SystemExit(f"model {self.name!r}: environment variable {s['api_key_env']} is not set")
            elif s["api_key_file"]:
                try:
                    self._key = Path(os.path.expanduser(s["api_key_file"])).read_text().strip()
                except OSError as e:
                    raise SystemExit(f"model {self.name!r}: cannot read api_key_file: {e.strerror}")
            else:
                self._key = ""  # a local endpoint (Ollama) may need none
        return self._key or None

    def _scrub(self, text: str) -> str:
        k = self._key
        return text.replace(k, "<key>") if k else text

    def _post(self, payload: dict) -> dict:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        key = self.key()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        req = urllib.request.Request(self.base_url + "/chat/completions", data=json.dumps(payload).encode(),
                                     method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode(errors="replace")[:600]
            except Exception:  # noqa: BLE001
                pass
            raise HTTPStatus(e.code, self._scrub(body)) from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise RuntimeError(f"model {self.name!r} at {urlparse(self.base_url).hostname}: "
                               f"{type(e).__name__}: {self._scrub(str(getattr(e, 'reason', e)))[:200]}") from None

    def _chat(self, messages: list[dict], response_format: dict | None) -> tuple[str, dict]:
        payload = {"model": self.model, "messages": messages}
        if response_format:
            payload["response_format"] = response_format
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.max_tokens:
            payload["max_tokens"] = self.max_tokens
        out = self._post(payload)
        choice = (out.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        prov = {"generator": "openai-compatible", "backend": self.name, "model": out.get("model") or self.model,
                "endpoint_host": urlparse(self.base_url).hostname, "response_id": out.get("id"), "when": _now(),
                "prompt_sha256": _sha(json.dumps(messages, sort_keys=True)),
                "stop_reason": choice.get("finish_reason"), "usage": out.get("usage") or {}}
        if msg.get("refusal") or choice.get("finish_reason") == "content_filter":
            raise Refused(json.dumps(prov))
        return str(msg.get("content") or ""), prov

    @staticmethod
    def _system_first(messages: list[dict]) -> list[dict]:
        """One system message, first: Qwen and Mistral reject a system message anywhere else."""
        system = "\n\n".join(str(m.get("content") or "") for m in messages if m.get("role") == "system")
        rest = [{"role": m.get("role"), "content": m.get("content") or ""} for m in messages if m.get("role") != "system"]
        return ([{"role": "system", "content": system}] if system else []) + rest

    def _format(self, mode: str, schema: dict) -> dict | None:
        if mode == "json_schema":
            return {"type": "json_schema", "json_schema": {"name": "answer", "schema": schema, "strict": False}}
        if mode == "json_object":
            return {"type": "json_object"}
        return None

    def call(self, system: str, user: str, schema: dict) -> tuple[dict, dict]:
        instruction = ("\n\nAnswer with one JSON object that validates against this JSON schema, and nothing else:\n"
                       + json.dumps(schema))
        messages = [{"role": "system", "content": system + instruction}, {"role": "user", "content": user}]
        while True:
            try:
                text, prov = self._chat(messages, self._format(self.mode, schema))
                break
            except HTTPStatus as e:
                nxt = self.MODES.index(self.mode) + 1
                if e.code == 400 and nxt < len(self.MODES):  # the endpoint does not take this response_format
                    self.mode = self.MODES[nxt]
                    continue
                raise RuntimeError(f"model {self.name!r}: HTTP {e.code}: {e.body[:300]}") from None
        prov["structured_mode"] = self.mode
        for attempt in (1, 2):
            try:
                data = parse_json(text)
                errors = schema_errors(data, schema)
            except ValueError as e:
                data, errors = None, [f"not JSON: {e}"]
            if not errors:
                prov["attempts"] = attempt
                return data, prov
            if attempt == 2:
                raise RuntimeError(f"model {self.name!r} did not return valid JSON: {'; '.join(errors)[:500]}")
            messages = messages + [{"role": "assistant", "content": text},
                                   {"role": "user", "content": "Your answer does not validate:\n- "
                                    + "\n- ".join(errors) + "\nAnswer again with the corrected JSON object only."}]
            try:
                text, prov2 = self._chat(messages, self._format(self.mode, schema))
            except HTTPStatus as e:
                raise RuntimeError(f"model {self.name!r}: HTTP {e.code}: {e.body[:300]}") from None
            prov["usage_retry"] = prov2.get("usage")

    def complete(self, messages: list[dict], json_mode: bool = False) -> tuple[str, dict]:
        msgs = self._system_first(messages)
        fmt = {"type": "json_object"} if json_mode and self.mode in ("json_schema", "json_object") else None
        try:
            return self._chat(msgs, fmt)
        except HTTPStatus as e:
            if fmt and e.code == 400:
                self.mode = "prompt"
                return self._chat(msgs, None)
            raise RuntimeError(f"model {self.name!r}: HTTP {e.code}: {e.body[:300]}") from None


class HTTPStatus(Exception):
    def __init__(self, code: int, body: str):
        super().__init__(f"HTTP {code}")
        self.code, self.body = code, body


def make_backend(name: str, spec: dict):
    spec = dict(spec or {})
    kind = spec.pop("backend", "claude-code")
    if kind == "claude-code":
        return ClaudeCodeBackend(name=name, **spec)
    if kind == "openai-compatible":
        return OpenAICompatBackend(name=name, **spec)
    raise SystemExit(f"model {name!r}: unknown backend {kind!r} (one of {', '.join(BACKENDS)})")


def is_paid(spec: dict) -> bool:
    spec = spec or {}
    return bool(spec.get("paid", spec.get("backend", "claude-code") == "openai-compatible"))


def inline_keys(models: dict) -> list[str]:
    return [n for n, s in (models or {}).items() if (s or {}).get("api_key")]


def secret_values(models: dict) -> list[str]:
    """Every key the config resolves to, for tests and leak checks; never printed."""
    out = []
    for n, s in (models or {}).items():
        if (s or {}).get("backend") == "openai-compatible":
            try:
                k = make_backend(n, s).key()
            except SystemExit:
                k = None
            if k:
                out.append(k)
    return out
