#!/usr/bin/env python3
"""WES write guard (spe_harden_trs_readonly, ladder level L1).

Traefik sends every WES request that is not GET or HEAD here. The guard refuses
any file part (workflow_attachment) and any workflow_url that is not a TRS URI
of the stack's own TRS, and forwards everything else to WESkit unchanged. The
checks do not depend on the path, so path tricks cannot route around them.
Where Python's parsers and WESkit's (werkzeug) could read a request differently,
the guard refuses it: repeated Content-Type, Content-Length or Transfer-Encoding
headers, repeated parameters in Content-Type or a part's Content-Disposition,
and parts with a Content-Transfer-Encoding. Standard library only.
"""
import argparse
import http.client
import json
import re
from email.message import Message
from email.parser import BytesParser
from email.policy import HTTP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

TRS_URL = re.compile(r"trs://trs-filer\.weskit\.internal:8080/[^\s?#]+")
MAX_BODY = 1 << 20
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer",
       "transfer-encoding", "upgrade", "host", "content-length"}
NO_FILE = "workflow_attachment is not accepted here: run an installed TRS tool"
NO_URL = "workflow_url must be a TRS URI of an installed tool"
AMBIGUOUS = 400, "ambiguous request: repeated header parameter or part encoding"


def _repeats_params(value: str) -> bool:
    """True if a header value names a parameter twice (parsers disagree on which wins)."""
    m = Message()
    m["X"] = value
    names = [k for k, _ in (m.get_params(header="X") or [])[1:]]
    return len(names) != len(set(names))


def _names_file(value: str) -> bool:
    """True if a Content-Disposition names a filename in any form (filename, filename*, filename*N):
    werkzeug files the part as an upload even when the name is empty."""
    m = Message()
    m["X"] = value
    return any(re.sub(r"\*(\d+\*?)?$", "", k).lower() == "filename"
               for k, _ in (m.get_params(header="X") or [])[1:])


def check(content_type: str, body: bytes) -> tuple[int, str] | None:
    """None if the request may pass, else (status, reason)."""
    if not body:
        return None
    if _repeats_params(content_type or ""):
        return AMBIGUOUS
    ctype = (content_type or "").split(";")[0].strip().lower()
    urls: list[str] = []
    try:
        if ctype == "multipart/form-data":
            msg = BytesParser(policy=HTTP).parsebytes(
                b"Content-Type: " + content_type.encode("latin-1") + b"\r\n\r\n" + body)
            if not msg.is_multipart() or msg.defects:
                return 400, "malformed multipart body"
            for part in msg.iter_parts():
                if part.defects:
                    return 400, "malformed multipart body"
                # raw values: the HTTP policy drops a repeated parameter silently
                disp = [v for k, v in part.raw_items() if k.lower() == "content-disposition"]
                if "content-transfer-encoding" in part or len(disp) > 1 or any(map(_repeats_params, disp)):
                    return AMBIGUOUS
                name = part.get_param("name", header="content-disposition")
                if part.get_filename() is not None or any(map(_names_file, disp)) or name == "workflow_attachment":
                    return 403, NO_FILE
                if name == "workflow_url":
                    urls.append(part.get_payload(decode=True).decode("utf-8", "replace"))
        elif ctype == "application/x-www-form-urlencoded":
            form = parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
            if "workflow_attachment" in form:
                return 403, NO_FILE
            urls += form.get("workflow_url", [])
        elif ctype == "application/json":
            data = json.loads(body)
            if isinstance(data, dict):
                if "workflow_attachment" in data:
                    return 403, NO_FILE
                if "workflow_url" in data:
                    urls.append(str(data["workflow_url"]))
        else:
            return 415, f"unsupported content type: {ctype or '(none)'}"
    except (ValueError, UnicodeError, LookupError):
        return 400, "malformed request body"
    if any(not TRS_URL.fullmatch(u) for u in urls):
        return 403, NO_URL
    return None


def serve(host: str, port: int, up_host: str, up_port: int) -> ThreadingHTTPServer:
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
            ctype = self.headers.get("Content-Type")
            verdict = check(ctype or "", body)
            if verdict:
                return self._reply(*verdict)
            headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP | {"content-type"}}
            if ctype is not None:
                headers["Content-Type"] = ctype  # exactly the string that was checked
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
    ap.add_argument("--upstream", default="rest:5000")
    a = ap.parse_args()
    lh, lp = a.listen.rsplit(":", 1)
    uh, up = a.upstream.rsplit(":", 1)
    serve(lh, int(lp), uh, int(up)).serve_forever()


if __name__ == "__main__":
    main()
