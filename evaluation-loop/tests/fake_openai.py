"""A local OpenAI-compatible /v1/chat/completions server for tests: scripted answers, recorded requests."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeOpenAI:
    """`answers` is a list of callables or values, one per request: a str is the message content, a dict
    is a whole response body, an int is an HTTP error status. `requests` records (headers, body)."""

    def __init__(self, answers=None, key: str | None = "sk-test-0123456789abcdef0123456789abcdef"):
        self.answers = list(answers or [])
        self.requests: list[tuple[dict, dict]] = []
        self.key = key
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # quiet
                pass

            def _send(self, code: int, obj: dict):
                data = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path.endswith("/models"):
                    return self._send(200, {"data": [{"id": "m1"}]})
                self._send(404, {"error": "no"})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append((dict(self.headers), body))
                if outer.key and self.headers.get("Authorization") != f"Bearer {outer.key}":
                    return self._send(401, {"error": {"message": "bad key"}})
                a = outer.answers.pop(0) if outer.answers else "{}"
                if callable(a):
                    a = a(body)
                if isinstance(a, int):
                    return self._send(a, {"error": {"message": f"status {a}"}})
                if isinstance(a, dict):
                    return self._send(200, a)
                self._send(200, {"id": "r1", "model": body.get("model"),
                                 "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": a}}],
                                 "usage": {"prompt_tokens": 1, "completion_tokens": 1}})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
