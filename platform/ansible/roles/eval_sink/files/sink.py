"""The ladder's test receiver: logs every request as one JSON line and answers 200. Standard library only.

It stands for a host outside the SPE (spec part 04, *The test receiver*). Evaluation only: never in a deployment
that holds real data.
"""
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock

MAX_BODY = 1 << 20


def read_body(headers, rfile) -> tuple[bytes, bool]:
    """The request body, at most MAX_BODY bytes, and whether it was cut there.

    Chunked bodies are decoded; a missing or invalid Content-Length reads as no body, so the request line is
    still logged. A malformed chunk ends the body with what was read before it.
    """
    if "chunked" in headers.get("Transfer-Encoding", "").lower():
        body = b""
        while True:
            size_line = rfile.readline(65537)
            try:
                size = int(size_line.split(b";", 1)[0].strip(), 16)
            except ValueError:
                return body, False
            if size == 0:
                while rfile.readline(65537).strip():  # trailers, up to the blank line
                    pass
                return body, False
            if len(body) + size > MAX_BODY:
                return body + rfile.read(MAX_BODY - len(body)), True
            body += rfile.read(size)
            rfile.readline(65537)  # the CRLF after the chunk
    try:
        length = int(headers.get("Content-Length") or 0)
    except ValueError:
        return b"", False
    if length <= 0:
        return b"", False
    return rfile.read(min(length, MAX_BODY)), length > MAX_BODY


def make_server(address, log: Path) -> ThreadingHTTPServer:
    # The log exists, empty, from the start: the evaluation reads a missing log as "no receiver"
    # (isolation.SINK_LOG) and an empty one as "a receiver, no requests yet".
    Path(log).touch()
    lock = Lock()

    class Handler(BaseHTTPRequestHandler):
        def _any(self):
            raw, truncated = read_body(self.headers, self.rfile)
            # `at` is the VM's clock (epoch seconds): the canary hit watcher places a hit in an
            # evaluation's window (spe-eval's windows.jsonl) by it, to tell an eval hit from a chat one.
            entry = {"method": self.command, "host": self.headers.get("Host", ""), "path": self.path,
                     "body": raw.decode("utf-8", "replace"), "at": time.time()}
            if truncated:
                entry["truncated"] = True  # only when cut at MAX_BODY: other lines stay as they were
            line = json.dumps(entry, ensure_ascii=False)
            with lock, open(log, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())
            self.send_response(200)
            self.send_header("Content-Length", "3")
            self.end_headers()
            self.wfile.write(b"ok\n")

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _any

        def log_message(self, *args):
            pass

    return ThreadingHTTPServer(address, Handler)


if __name__ == "__main__":
    make_server(("0.0.0.0", 8099), Path(sys.argv[1] if len(sys.argv) > 1 else "/log/requests.jsonl")).serve_forever()
