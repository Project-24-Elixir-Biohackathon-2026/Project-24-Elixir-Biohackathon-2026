"""Open-terminal discovery and tools, with sandbox-only authenticated requests."""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote

import httpx
from pydantic_ai import Tool

MAX_RESPONSE_BYTES = 1024 * 1024
REQUEST_TIMEOUT = 30.0

_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b([A-Za-z0-9_.-]*(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|client[_-]?secret))"
    r"(\s*[:=]\s*)(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;]+)"
)
_AUTHORIZATION_RE = re.compile(
    r"(?im)(\bauthorization\b\s*[:=]\s*)(?:Bearer\s+)?[^\s,;]+"
)


def redact_sensitive_data(text: str) -> str:
    """Mask common credential-like values in text returned by the sandbox."""
    text = _AUTHORIZATION_RE.sub(r"\1[redacted]", text)

    def redact_assignment(match: re.Match) -> str:
        return f"{match.group(1)}{match.group(2)}[redacted]"

    return _SECRET_ASSIGNMENT_RE.sub(redact_assignment, text)


class SandboxUnavailable(RuntimeError):
    """Discovery failed; the service should remain unready and retry."""


@dataclass(frozen=True)
class Operation:
    name: str
    method: str
    path: str
    description: str
    parameters: dict
    path_params: frozenset[str]
    query_params: frozenset[str]
    required_query: frozenset[str]
    has_body: bool


def _resolve(value, spec, seen=frozenset()):
    if isinstance(value, list):
        return [_resolve(v, spec, seen) for v in value]
    if not isinstance(value, dict):
        return value
    if "$ref" in value:
        ref = value["$ref"]
        if not ref.startswith("#/") or ref in seen:
            return {}
        target = spec
        try:
            for part in ref[2:].split("/"):
                target = target[part.replace("~1", "/").replace("~0", "~")]
        except (KeyError, TypeError):
            return {}
        return _resolve(target, spec, seen | {ref})
    return {k: _resolve(v, spec, seen) for k, v in value.items()}


def _clean(schema):
    schema = dict(schema)
    variants = [v for v in schema.get("anyOf", []) if v.get("type") != "null"]
    if len(variants) == 1:
        schema.pop("anyOf")
        schema.update(variants[0])
    if schema.get("default", False) is None:
        schema.pop("default")
    if "properties" in schema:
        schema["properties"] = {k: _clean(v) for k, v in schema["properties"].items()}
    if isinstance(schema.get("items"), dict):
        schema["items"] = _clean(schema["items"])
    if "anyOf" in schema:
        schema["anyOf"] = [_clean(v) for v in schema["anyOf"]]
    if not any(k in schema for k in ("type", "anyOf", "oneOf", "allOf", "properties")):
        schema["type"] = "string"
    return schema


def operations_from_openapi(spec: dict) -> list[Operation]:
    operations = []
    for path, item in spec.get("paths", {}).items():
        for method, raw in item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                continue
            if not raw.get("operationId"):
                continue
            op = _resolve(raw, spec)
            props, required, paths, queries, required_query = {}, [], set(), set(), set()
            for param in _resolve(item.get("parameters", []), spec) + op.get("parameters", []):
                location = param.get("in")
                if location not in {"path", "query"}:
                    continue
                name = param["name"]
                schema = param.get("schema", {})
                converted = {"type": schema.get("type", "string")}
                description = schema.get("description", param.get("description", ""))
                if "enum" in schema:
                    description += ". Possible values: " + ", ".join(map(str, schema["enum"]))
                if description:
                    converted["description"] = description
                props[name] = converted
                (paths if location == "path" else queries).add(name)
                if param.get("required") or location == "path":
                    required.append(name)
                    if location == "query":
                        required_query.add(name)
            has_body = "requestBody" in op
            body = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
            props.update({k: _clean(v) for k, v in body.get("properties", {}).items()})
            required.extend(body.get("required", []))
            operations.append(Operation(
                op["operationId"], method.upper(), path, op.get("description", op.get("summary", "")),
                {"type": "object", "properties": props, "required": list(dict.fromkeys(required))},
                frozenset(paths), frozenset(queries), frozenset(required_query), has_body,
            ))
    return operations


def select_operations(ops: list[Operation], allow: Literal["all"] | list[str]) -> list[Operation]:
    if allow == "all":
        return list(ops)
    by_name = {op.name: op for op in ops}
    unknown = set(allow) - by_name.keys()
    if unknown:
        raise ValueError("Unknown sandbox operation ids: " + ", ".join(sorted(unknown)))
    return [by_name[name] for name in allow]


class _ResponseText(str):
    def __new__(cls, text, total):
        obj = super().__new__(cls, text)
        obj.total_bytes = total
        return obj


def truncate(text: str, max_bytes: int) -> str:
    if max_bytes < 0:
        raise ValueError("max_bytes must be nonnegative")
    data = text.encode("utf-8", errors="replace")
    total = getattr(text, "total_bytes", len(data))
    if len(data) <= max_bytes and total <= len(data):
        return str(text)
    # Reserve the largest possible marker, then fit whole UTF-8 characters.
    marker_size = len(f"\n[truncated: {max_bytes} of {total} bytes shown]".encode())
    prefix = data[:max(0, max_bytes - marker_size)].decode("utf-8", errors="ignore")
    marker = f"\n[truncated: {len(prefix.encode())} of {total} bytes shown]"
    return (prefix + marker) if len(marker.encode()) <= max_bytes else marker[:max_bytes]


class SandboxClient:
    def __init__(self, base_url: str, api_key: str, *, http: httpx.AsyncClient | None = None):
        url = httpx.URL(base_url)
        if url.scheme not in {"http", "https"} or not url.host or url.userinfo or url.query or url.fragment or url.path not in {"", "/"}:
            raise ValueError("Sandbox base URL must be an HTTP(S) origin")
        self._base = str(url).rstrip("/")
        self._key = api_key
        self._owned = http is None
        self._http = http if http is not None else httpx.AsyncClient(trust_env=False)

    async def aclose(self):
        if self._owned:
            await self._http.aclose()

    async def _request(self, method, path, *, params=None, body=None, session_id=None):
        if not path.startswith("/") or path.startswith("//") or any(c in path for c in ("?", "#", "\\")):
            raise ValueError("Invalid sandbox route")
        headers = {"Authorization": f"Bearer {self._key}"}
        if session_id is not None:
            headers["X-Session-Id"] = session_id
        async with asyncio.timeout(REQUEST_TIMEOUT):
            async with self._http.stream(
                method, self._base + path, params=params, json=body, headers=headers,
                timeout=REQUEST_TIMEOUT, follow_redirects=False, auth=None,
            ) as response:
                data = bytearray()
                total = 0
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    total += len(chunk)
                    data.extend(chunk[:max(0, MAX_RESPONSE_BYTES - len(data))])
                text = bytes(data).decode("utf-8", errors="replace")
                text = redact_sensitive_data(text)
                    
                # Never echo the sandbox credential from an error or tool response.
                if self._key:
                    text = text.replace(self._key, "[redacted]")
                    
                return response.status_code, _ResponseText(text, total)

    async def _discover(self, path):
        try:
            status, text = await self._request("GET", path)
            if status != 200 or text.total_bytes > MAX_RESPONSE_BYTES:
                raise SandboxUnavailable("Sandbox discovery unavailable")
            result = json.loads(text)
            if not isinstance(result, dict):
                raise ValueError("Expected object")
            return result
        except (httpx.HTTPError, TimeoutError, ValueError):
            raise SandboxUnavailable("Sandbox discovery unavailable") from None

    async def openapi(self) -> dict:
        spec = await self._discover("/openapi.json")
        if not isinstance(spec.get("paths"), dict):
            raise SandboxUnavailable("Sandbox OpenAPI has no paths")
        return spec

    async def cwd(self) -> str | None:
        try:
            value = (await self._discover("/files/cwd")).get("cwd")
            return value if isinstance(value, str) else None
        except SandboxUnavailable:
            return None

    async def system_prompt(self) -> str | None:
        try:
            config = await self._discover("/api/config")
            if not isinstance(config.get("features"), dict) or not config["features"].get("system"):
                return None
            value = (await self._discover("/system")).get("prompt")
            return value if isinstance(value, str) else None
        except SandboxUnavailable:
            return None

    async def call(self, op: Operation, args: dict, *, session_id=None) -> str:
        try:
            for name in op.parameters.get("required", []):
                if name not in args or args[name] is None:
                    return json.dumps({"error": f"Missing required parameter: {name}"})
            path = op.path
            for name in op.path_params:
                value = str(args[name])
                if value in {"", ".", ".."}:
                    return json.dumps({"error": f"Invalid path parameter: {name}"})
                path = path.replace("{" + name + "}", quote(value, safe=""))
            params = {k: args[k] for k in op.query_params if k in args and (k in op.required_query or args[k] not in (None, ""))}
            body = (args if op.has_body else {}) if op.method in {"POST", "PUT", "PATCH", "DELETE"} else None
            status, text = await self._request(op.method, path, params=params, body=body, session_id=session_id)
            if status >= 300:
                return json.dumps({"error": f"HTTP error {status}: {text}"})
            return text
        except (httpx.TimeoutException, TimeoutError):
            return json.dumps({"error": "Sandbox request timed out"})
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            return json.dumps({"error": "Sandbox request failed"})


def build_tools(client: SandboxClient, ops: list[Operation], max_output_bytes: int, *, cwd=None) -> list[Tool]:
    if max_output_bytes < 0:
        raise ValueError("max_output_bytes must be nonnegative")

    def bind(op):
        async def invoke(ctx, **args):
            session = getattr(getattr(ctx, "deps", None), "session_id", None)
            return truncate(await client.call(op, args, session_id=session), max_output_bytes)
        description = op.description
        if op.name == "run_command" and cwd:
            description += f"\n\nThe current working directory is: {cwd}"
        return Tool.from_schema(invoke, op.name, description, op.parameters, takes_ctx=True)

    return [bind(op) for op in ops]
