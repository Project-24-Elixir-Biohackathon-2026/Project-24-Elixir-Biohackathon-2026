#!/usr/bin/env python3
"""canary-guard: a reverse proxy between Traefik and the three GA4GH APIs.

Every response the SPE agent gets from WES, DRS or TRS passes through here.
The guard looks up every candidate substring of the body in the hash-only
canary manifest (`canaries.manifest.sha256`) and, by default, replaces each
hit with `[REDACTED:<type>]` before the agent can read it. The plaintext
canary record never reaches the VM: only the sha256 digests do.

This puts the TM-001 control in the agent's path: run stdout/stderr, DRS
descriptions and aliases, TRS descriptions, workflow files and service-info all
come back through these three APIs, whichever chat frontend drives the agent.

Configuration (environment):
  GUARD_MANIFEST     path of the manifest; reloaded when it changes (default /guard/canaries.manifest.sha256)
  GUARD_MODE         redact (default) | monitor (log only, pass through) | off;
                     an unknown value logs config_error and falls back to redact
  GUARD_EXEMPT_TYPES comma-separated canary types never redacted (default: registry-study-id,
                     because study ids are part of the DRS file names the agent must use)
  GUARD_MAX_BYTES    larger responses are refused in redact mode, not passed unchecked (default 50 MiB)
  GUARD_UPSTREAMS    JSON list of [path_prefix, base_url], first match wins
  GUARD_PORT         listen port (default 8080)

Every hit is logged to stdout as one JSON line with the canary type, method
and path, never the token, so `docker compose logs canary-guard` is safe to
share. Responses carry `X-Canary-Guard: redacted=<n>`.

Body handling: text and JSON bodies are redacted in place. JSON bodies are also
matched in their decoded string values, the form the client reads (WESkit
returns run logs as JSON strings, with escaped newlines). A hit in any other
content type, or one that cannot be replaced in the raw body, blocks the
response with 502. Request bodies are forwarded unchanged.

Standard library only.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).parent))
from canary_check import candidates, json_strings, load_manifest  # noqa: E402

DEFAULT_UPSTREAMS = [
    ["/ga4gh/wes", "http://rest:5000"],
    ["/weskit/v1", "http://rest:5000"],
    ["/ga4gh/drs", "http://drs-filer:8080"],
    ["/ga4gh/trs", "http://trs-filer:8080"],
]
HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te",
    "trailers", "transfer-encoding", "upgrade", "content-length", "content-encoding",
}
TEXTUAL = ("text/", "application/json", "application/problem+json", "application/yaml",
           "application/x-yaml", "application/xml", "application/javascript", "application/x-ndjson")


def _log(event: str, **fields) -> None:
    print(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": event, **fields}),
          flush=True)


class Manifest:
    """The hash manifest, reloaded whenever the file's mtime changes.

    A missing file is not an error: at creation the guard starts before the
    hand-off writes the manifest, and runs as a plain proxy until it appears."""

    def __init__(self, path: Path):
        self.path = path
        self._mtime: float | None = None
        self._hashes: dict[str, str] = {}
        self._lock = threading.Lock()

    def get(self) -> dict[str, str]:
        try:
            mtime = self.path.stat().st_mtime
        except FileNotFoundError:
            return {}
        with self._lock:
            if mtime != self._mtime:
                try:
                    self._hashes = load_manifest(self.path)
                    self._mtime = mtime
                    _log("manifest_loaded", tokens=len(self._hashes))
                except (OSError, ValueError) as e:
                    _log("manifest_error", error=str(e))
            return self._hashes


def readable_views(text: str, ctype: str) -> list[str]:
    """The body as written and as the client reads it. JSON string values are decoded, so an
    escape such as the \\n in a WESkit run log does not join the token after it."""
    views = [text]
    if "json" in ctype:
        try:
            views += [s for _, s in json_strings(json.loads(text))]
        except ValueError:
            pass
    return views


def find_hits(views: list[str], hashes: dict[str, str], exempt: set[str]) -> dict[str, str]:
    hits: dict[str, str] = {}
    for view in views:
        for c in candidates(view):
            t = hashes.get(hashlib.sha256(c.encode()).hexdigest())
            if t and t not in exempt:
                hits[c] = t
    return hits


def redact(text: str, ctype: str, hashes: dict[str, str], exempt: set[str]) -> tuple[str, list[str], bool]:
    """Replace every manifest token in `text`; return the new text, the hit types, and whether
    the result reads clean. A token the client would decode from a form that is not written out
    in the raw body (a \\u escape) cannot be replaced in place: the caller withholds the body."""
    hits = find_hits(readable_views(text, ctype), hashes, exempt)
    if not hits:
        return text, [], True
    # Longest first, so a token that contains another is replaced whole.
    for token in sorted(hits, key=len, reverse=True):
        text = text.replace(token, f"[REDACTED:{hits[token]}]")
    clean = not find_hits(readable_views(text, ctype), hashes, exempt)
    return text, list(hits.values()), clean


MODES = ("redact", "monitor", "off")
# Unquoted YAML turns off/no/false into a boolean, which Jinja renders "False"; on/yes/true
# become "True". Read those as meant. Anything else falls back to redact with an error in
# the log: the guard sits in the API path, so exiting on a typo would take WES, DRS and TRS
# down with it, and passing through unchecked would silently drop the control.
_MODE_ALIASES = {"false": "off", "no": "off", "0": "off", "none": "off",
                 "true": "redact", "yes": "redact", "on": "redact", "1": "redact"}


def parse_mode(value) -> str:
    raw = str(value).strip().lower()
    mode = _MODE_ALIASES.get(raw, raw)
    if mode in MODES:
        return mode
    _log("config_error", setting="GUARD_MODE", value=str(value)[:40], fallback="redact")
    return "redact"


class Config:
    def __init__(self, env=os.environ):
        self.manifest = Manifest(Path(env.get("GUARD_MANIFEST", "/guard/canaries.manifest.sha256")))
        self.mode = parse_mode(env.get("GUARD_MODE", "redact"))
        self.exempt = {t.strip() for t in env.get("GUARD_EXEMPT_TYPES", "registry-study-id").split(",") if t.strip()}
        self.max_bytes = int(env.get("GUARD_MAX_BYTES", str(50 * 1024 * 1024)))
        self.upstreams = json.loads(env["GUARD_UPSTREAMS"]) if env.get("GUARD_UPSTREAMS") else DEFAULT_UPSTREAMS
        self.port = int(env.get("GUARD_PORT", "8080"))

    def upstream_for(self, path: str) -> str | None:
        for prefix, base in self.upstreams:
            if path == prefix or path.startswith(prefix.rstrip("/") + "/") or path.startswith(prefix + "?"):
                return base
        return None


def make_handler(cfg: Config):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # access log off; hits are logged as JSON
            pass

        def _send(self, status: int, headers: list[tuple[str, str]], body: bytes) -> None:
            self.send_response(status)
            for k, v in headers:
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _error(self, status: int, message: str) -> None:
            body = json.dumps({"msg": message, "status_code": status}).encode()
            self._send(status, [("Content-Type", "application/json"), ("X-Canary-Guard", "refused")], body)

        def _proxy(self) -> None:
            base = cfg.upstream_for(urlsplit(self.path).path)
            if base is None:
                return self._error(404, "no upstream for this path")
            up = urlsplit(base)
            length = int(self.headers.get("Content-Length") or 0)
            req_body = self.rfile.read(length) if length else None
            fwd = {k: v for k, v in self.headers.items()
                   if k.lower() not in HOP_BY_HOP and k.lower() != "accept-encoding"}
            fwd["Accept-Encoding"] = "identity"  # plaintext bodies, so they can be scanned
            try:
                conn = http.client.HTTPConnection(up.hostname, up.port or 80, timeout=300)
                conn.request(self.command, self.path, body=req_body, headers=fwd)
                resp = conn.getresponse()
                body = resp.read(cfg.max_bytes + 1)
                headers = [(k, v) for k, v in resp.getheaders() if k.lower() not in HOP_BY_HOP]
                status = resp.status
                conn.close()
            except (OSError, http.client.HTTPException) as e:
                _log("upstream_error", path=self.path, error=type(e).__name__)
                return self._error(502, "upstream unavailable")

            if cfg.mode == "off":
                return self._send(status, headers, body[: cfg.max_bytes])
            if len(body) > cfg.max_bytes:
                _log("too_large", method=self.command, path=self.path)
                if cfg.mode == "redact":
                    return self._error(502, "response too large for the canary guard")
                return self._send(status, headers, body[: cfg.max_bytes])

            hashes = cfg.manifest.get()
            if not hashes or not body:
                return self._send(status, headers, body)
            ctype = (resp.getheader("Content-Type") or "").lower()
            textual = any(ctype.startswith(t) for t in TEXTUAL)
            charset = "utf-8"
            if "charset=" in ctype:
                charset = ctype.split("charset=", 1)[1].split(";")[0].strip() or "utf-8"
            text = body.decode(charset, errors="replace")
            new_text, types, clean = redact(text, ctype, hashes, cfg.exempt)
            if not types:
                return self._send(status, headers, body)

            for t in types:
                _log("canary_hit", type=t, method=self.command, path=urlsplit(self.path).path,
                     mode=cfg.mode, content_type=ctype or "none")
            if cfg.mode == "monitor":
                return self._send(status, headers + [("X-Canary-Guard", f"seen={len(types)}")], body)
            if not textual or not clean:
                return self._error(502, "response withheld: contains canary data and cannot be redacted")
            return self._send(status, headers + [("X-Canary-Guard", f"redacted={len(types)}")],
                              new_text.encode(charset, errors="replace"))

        do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _proxy

    return Handler


def main() -> None:
    cfg = Config()
    server = ThreadingHTTPServer(("0.0.0.0", cfg.port), make_handler(cfg))
    _log("started", port=cfg.port, mode=cfg.mode, exempt=sorted(cfg.exempt),
         manifest=str(cfg.manifest.path), upstreams=cfg.upstreams)
    server.serve_forever()


if __name__ == "__main__":
    main()
