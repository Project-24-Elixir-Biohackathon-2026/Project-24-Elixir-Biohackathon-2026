#!/usr/bin/env python3
"""TRS write guard (spe_mitigate_trs_guard, experiments/trs-guard.yml).

Traefik sends every TRS request that is not GET or HEAD here. A version write (PUT
/tools/{id}/versions/{v}, GA4GH TRS body: {"files": [{"file_wrapper": {"content": ...}}, ...]})
is refused (403) when any file content names a path under the sensitive data tier -- the shape
of a workflow an agent registers after following an injected instruction to read a sensitive
file (threats/TM-003, paths/P2). Every other write -- a tool own description (which legitimately
carries free text that can mention that tier, e.g. a planted injection payload: the catalog own
installer writes one on every build), any body this guard does not recognise as a files-bearing
write, a DELETE -- forwards to trs-filer unchanged.

This is a content check, not the TRS read-only mode (mitigations/L1.yml, spe_harden_trs_readonly,
which refuses every write regardless of content): it narrows rather than closes paths/P2.md (a
payload that builds the path at runtime instead of naming it literally, splits it across fields,
or encodes it, is not caught -- the known limit experiments/trs-guard.yml rationale names).
Standard library only.
"""
import argparse
import http.client
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY = 1 << 20
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer",
       "transfer-encoding", "upgrade", "host", "content-length"}
REFUSED = "workflow content names a path under the sensitive data tier: not accepted here"


def check(body: bytes, markers: list[str]) -> tuple[int, str] | None:
    """None if the request may pass, else (status, reason). Only a files-bearing TRS version
    write is scanned: markers (e.g. "sensitive/") are plain substrings checked against each
    file content field (file_wrapper.content), decoded as UTF-8, replacing what does not decode
    so a binary or mixed-encoding body is still scanned rather than waved through. A tool own PUT
    (no files list -- organization, name, description, toolclass) is not scanned at all: its
    description is free text that legitimately names the sensitive tier (a planted injection
    payload does), so scanning it would refuse the catalog own installer writes, not only an
    agent write."""
    if not body:
        return None
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None  # not a JSON body this guard understands; let trs-filer judge it
    if not isinstance(data, dict):
        return None
    files = data.get("files")
    if not isinstance(files, list):
        return None  # a tool-level write (description, etc.), not a version workflow files
    for f in files:
        if not isinstance(f, dict):
            continue
        wrapper = f.get("file_wrapper")
        content = wrapper.get("content") if isinstance(wrapper, dict) else None
        if isinstance(content, str) and any(m in content for m in markers):
            return 403, REFUSED
    return None


def serve(host: str, port: int, up_host: str, up_port: int, markers: list[str]) -> ThreadingHTTPServer:
    class Guard(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _reply(self, status: int, msg: str) -> None:
            data = json.dumps({"msg": msg, "status_code": status}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)
            self.close_connection = True

        def _handle(self) -> None:
            if any(len(self.headers.get_all(h) or []) > 1
                   for h in ("Content-Type", "Content-Length", "Transfer-Encoding")):
                return self._reply(400, "repeated Content-Type, Content-Length or Transfer-Encoding header")
            if "chunked" in self.headers.get("Transfer-Encoding", "").lower():
                return self._reply(411, "chunked request bodies are not accepted")
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self._reply(400, "bad Content-Length")
            if length > MAX_BODY:
                return self._reply(413, "request body too large")
            body = self.rfile.read(length)
            verdict = check(body, markers)
            if verdict:
                return self._reply(*verdict)
            headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
            conn = http.client.HTTPConnection(up_host, up_port, timeout=120)
            try:
                conn.request(self.command, self.path, body=body, headers=headers)
                resp = conn.getresponse()
                data = resp.read()
            finally:
                conn.close()
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() not in HOP:
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_POST = do_PUT = do_PATCH = do_DELETE = do_GET = _handle

        def log_message(self, fmt, *args):
            print(f"{self.command} {self.path} " + fmt % args, flush=True)

    return ThreadingHTTPServer((host, port), Guard)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", default="0.0.0.0:8080")
    ap.add_argument("--upstream", default="trs-filer:8080")
    ap.add_argument("--marker", action="append", default=["sensitive/"],
                     help="repeatable: a substring of the dataset sensitive tier to refuse on sight")
    a = ap.parse_args()
    lh, lp = a.listen.rsplit(":", 1)
    uh, up = a.upstream.rsplit(":", 1)
    serve(lh, int(lp), uh, int(up), a.marker).serve_forever()


if __name__ == "__main__":
    main()
