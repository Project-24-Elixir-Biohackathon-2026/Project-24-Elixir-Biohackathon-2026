"""lab_chat: the http transport against a stub chat server that keeps sessions like chat-ui's journal."""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lab_chat  # noqa: E402


def sse(*events):
    return "".join(f"data: {json.dumps(e)}\n\n" for e in events)


class StubChat(BaseHTTPRequestHandler):
    sessions: dict = {}
    posts: list = []
    answer = staticmethod(lambda text: f"echo: {text}")

    def do_POST(self):
        inp = json.loads(self.rfile.read(int(self.headers["content-length"])))
        StubChat.posts.append(inp)
        prior = StubChat.sessions.get(inp["threadId"], [])
        known = {m["id"] for m in prior}
        new = [m for m in inp["messages"] if m["id"] not in known and m["role"] == "user"]
        reply = {"id": f"a{len(StubChat.posts)}", "role": "assistant", "content": StubChat.answer(new[-1]["content"])}
        StubChat.sessions[inp["threadId"]] = prior + new + [reply]
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        self.wfile.write(sse({"type": "RUN_STARTED"}, {"type": "TEXT_MESSAGE_CONTENT", "delta": reply["content"]},
                             {"type": "RUN_FINISHED"}).encode())

    def do_GET(self):
        if self.path == "/api/sessions":  # the session list chat-ui serves
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"sessions": list(StubChat.sessions)}).encode())
            return
        sid = self.path.rsplit("/", 1)[-1]
        if sid not in StubChat.sessions:
            self.send_response(404); self.end_headers(); return
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"id": sid, "messages": StubChat.sessions[sid]}).encode())

    def log_message(self, *a):
        pass


@pytest.fixture
def stub_chat():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), StubChat)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    StubChat.sessions, StubChat.posts = {}, []
    yield f"http://127.0.0.1:{srv.server_port}/api/copilotkit/agent/spe/run"
    srv.shutdown()


def test_http_transport_continues_a_session(stub_chat):
    t = lab_chat.open_transport({"transport": "http", "chat_run_url": stub_chat, "timeout_s": 10})
    r1 = t.turn("one")
    r2 = t.turn("two", r1["session_id"])
    assert r1["answer"] == "echo: one" and r2["answer"] == "echo: two" and r2["session_id"] == r1["session_id"]
    assert [m["content"] for m in StubChat.posts[1]["messages"]] == ["one", "echo: one", "two"]
    assert [m["content"] for m in StubChat.sessions[r1["session_id"]]] == ["one", "echo: one", "two", "echo: two"]


def test_transport_config_errors():
    with pytest.raises(SystemExit, match="chat_run_url"):
        lab_chat.open_transport({"transport": "http"})
    with pytest.raises(SystemExit, match="not one of"):
        lab_chat.open_transport({"transport": "carrier-pigeon"})
