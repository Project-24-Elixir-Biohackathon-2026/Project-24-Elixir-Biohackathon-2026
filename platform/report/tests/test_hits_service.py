"""The participant hits page and hits.json (spec *Participant page*, *Security*; decisions 6, 10,
11): who may see a workspace's hits (`Handler.can_see_hits`), the page and its JSON twin served
from the hits directory (slice 2's watcher), against a fake Coder API like test_report.py's.
Fixtures use made-up tokens only (FCANARY-TEST01, from fixtures/canary/canaries.json)."""
from __future__ import annotations

import json
import re
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import canary_hits  # noqa: E402
import canary_record  # noqa: E402
import hits_view  # noqa: E402
import sperange_report as sr  # noqa: E402
from canary_hits import HitsFile  # noqa: E402

WID = "11111111-2222-4333-8444-555555555555"
OTHER = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
NOSIDECAR = "99999999-aaaa-4bbb-8ccc-dddddddddddd"
NOOWNER = "33333333-4444-4555-8666-777777777777"  # a sidecar with no "owner" key
USERS = {
    "tok-anna": {"username": "anna", "email": "anna@example.org", "roles": [{"name": "member"}]},
    "tok-bob": {"username": "bob", "email": "bob@example.org", "roles": []},
    "tok-root": {"username": "admin", "email": "admin@example.org", "roles": [{"name": "owner"}]},
}

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "canary"
CANARIES = canary_record.load_canaries(FIXTURES)
API_HOST = canary_record.read_hosts(FIXTURES)["api_host"]
HOSTILE = "<img src=x onerror=alert(1)>"


def _agui_hit() -> dict:
    """One AG-UI journal hit (slice 1's fixtures.canary/agui-journals/s1.jsonl), kind touched:
    the flag file's content read back by a tool."""
    reader = canary_hits.JournalReader("s1")
    lines = [json.loads(line) for line in (FIXTURES / "agui-journals" / "s1.jsonl").read_text().splitlines()
             if line.strip()]
    places = [p for line in lines for p in reader.feed(line)]
    hits = [h for p in places for h in canary_hits.hits_for(p, CANARIES, API_HOST)]
    return next(h for h in hits if h["kind"] == "touched")


def _openwebui_hit() -> dict:
    """One Open WebUI hit (slice 1's fixtures/canary/openwebui-export.json), kind touched."""
    export = json.loads((FIXTURES / "openwebui-export.json").read_text())
    places = [p for chat in export["chats"] for p in canary_hits.openwebui_places(chat, "archive")]
    hits = [h for p in places for h in canary_hits.hits_for(p, CANARIES, API_HOST)]
    return next(h for h in hits if h["kind"] == "touched")


def _record(wid: str, partial: dict) -> dict:
    return {"detected": "2026-11-10T14:03:30Z", "workspace": wid, "instance": "cw-anna-tm-test",
            "owner": "anna", **partial}


class FakeCoder(BaseHTTPRequestHandler):
    def do_GET(self):
        tok = self.headers.get("Coder-Session-Token", "")
        user = USERS.get(tok)
        if self.path == "/api/v2/users/me":
            if user is None:
                return self.reply(401, {"message": "no"})
            return self.reply(200, user)
        self.reply(404, {"message": "?"})

    def reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def coder():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeCoder)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.fixture
def server(tmp_path, coder):
    """The service over tmp_path/reports (WID's sidecar, owner anna) and tmp_path/hits, with the
    real stream timings; a test may lower them on the server object."""
    reports_dir, hits_dir = tmp_path / "reports", tmp_path / "hits"
    reports_dir.mkdir()
    hits_dir.mkdir()
    (reports_dir / f"{WID}.json").write_text(json.dumps(
        {"owner": "anna", "owner_email": "anna@example.org", "workspace": "tm-test",
         "instance": "cw-anna-tm-test", "created": "2026-11-06 15:00 UTC"}))
    srv = sr.make_server("127.0.0.1:0", str(reports_dir), coder, str(hits_dir))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", hits_dir, srv
    srv.shutdown()


@pytest.fixture
def service(server):
    base, hits_dir, _ = server
    return base, hits_dir


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def call(base, path, token=None):
    headers = {"Cookie": f"{sr.COOKIE}={token}"} if token else {}
    req = urllib.request.Request(base + path, headers=headers)
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=10) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def write_hits(hits_dir: Path, wid: str, records: list[dict]) -> None:
    hf = HitsFile(str(hits_dir / f"{wid}.jsonl"))
    for record in records:
        hf.append(dict(record))


def write_status(hits_dir: Path, wid: str, status: dict) -> None:
    (hits_dir / f"{wid}.status.json").write_text(json.dumps(status))


# --- the page -----------------------------------------------------------------------------------

def test_owner_sees_both_frontends_with_value(service):
    base, hits_dir = service
    write_hits(hits_dir, WID, [_record(WID, _agui_hit()), _record(WID, _openwebui_hit())])
    status, _, body = call(base, f"/reports/{WID}/hits", token="tok-anna")
    assert status == 200
    text = body.decode()
    assert "AG-UI" in text and "Open WebUI" in text
    assert "FCANARY-TEST01" in text


def test_admin_sees_any_workspace(service):
    base, hits_dir = service
    write_hits(hits_dir, NOSIDECAR, [_record(NOSIDECAR, _agui_hit())])
    status, _, body = call(base, f"/reports/{NOSIDECAR}/hits", token="tok-root")
    assert status == 200
    assert "FCANARY-TEST01" in body.decode()


def test_other_user_gets_403(service):
    base, hits_dir = service
    write_hits(hits_dir, WID, [_record(WID, _agui_hit())])
    assert call(base, f"/reports/{WID}/hits", token="tok-bob")[0] == 403
    assert call(base, f"/reports/{WID}/hits.json", token="tok-bob")[0] == 403


def test_sidecar_without_owner_gets_403(server):
    """`can_see_hits` reads `meta.get("owner")`, not `meta["owner"]`: a sidecar missing `owner`
    means only admins can see it (like no sidecar at all), not a KeyError (500)."""
    base, hits_dir, srv = server
    Path(srv.RequestHandlerClass.store.root, f"{NOOWNER}.json").write_text(
        json.dumps({"workspace": "tm-no-owner"}))
    write_hits(hits_dir, NOOWNER, [_record(NOOWNER, _agui_hit())])
    assert call(base, f"/reports/{NOOWNER}/hits", token="tok-bob")[0] == 403
    assert call(base, f"/reports/{NOOWNER}/hits", token="tok-root")[0] == 200


def test_logged_out_redirect_and_401(service):
    base, _ = service
    status, headers, _ = call(base, f"/reports/{WID}/hits")
    assert status == 302
    assert headers["Location"] == f"/login?redirect=%2Freports%2F{WID}%2Fhits"
    assert call(base, f"/reports/{WID}/hits.json")[0] == 401


def test_notice_on_page(service):
    base, hits_dir = service
    write_hits(hits_dir, WID, [])
    status, _, body = call(base, f"/reports/{WID}/hits", token="tok-anna")
    assert status == 200
    assert hits_view.NOTICE in body.decode()


def test_stopped_workspace_renders(service):
    base, hits_dir = service
    write_hits(hits_dir, WID, [_record(WID, _agui_hit())])
    write_status(hits_dir, WID, {"state": "stopped", "since": "2026-11-10T14:05:00Z",
                                 "last_poll": "2026-11-10T14:04:00Z"})
    status, _, body = call(base, f"/reports/{WID}/hits", token="tok-anna")
    assert status == 200
    text = body.decode()
    assert "stopped" in text
    assert "FCANARY-TEST01" in text


def test_stopped_with_archive_incomplete_note(service):
    base, hits_dir = service
    write_status(hits_dir, WID, {"state": "stopped", "since": "2026-11-10T14:05:00Z",
                                 "note": "archive incomplete"})
    status, _, body = call(base, f"/reports/{WID}/hits", token="tok-anna")
    assert status == 200
    assert "stopped · archive incomplete" in body.decode()


def test_no_hits_file_yet(service):
    base, hits_dir = service
    write_status(hits_dir, WID, {"state": "running", "last_poll": "2026-11-10T14:03:00Z"})
    status, _, body = call(base, f"/reports/{WID}/hits", token="tok-anna")
    assert status == 200
    assert "No hits yet." in body.decode()


def test_encrypted_record_says_so(service):
    base, hits_dir = service
    write_status(hits_dir, WID, {"state": "encrypted", "note": "canary record is encrypted"})
    status, _, body = call(base, f"/reports/{WID}/hits", token="tok-anna")
    assert status == 200
    assert "The canary record is encrypted: the watcher cannot match this workspace." in body.decode()


def test_not_watched_without_a_status_file(service):
    base, _ = service
    status, _, body = call(base, f"/reports/{WID}/hits", token="tok-anna")
    assert status == 200
    assert "Not watched yet." in body.decode()


def test_malformed_id_is_404(service):
    base, _ = service
    assert call(base, "/reports/not-a-uuid/hits", token="tok-anna")[0] == 404
    assert call(base, "/reports/not-a-uuid/hits.json", token="tok-anna")[0] == 404


# --- hits.json ------------------------------------------------------------------------------------

def test_hits_json_after(service):
    base, hits_dir = service
    write_hits(hits_dir, WID, [_record(WID, _agui_hit()), _record(WID, _openwebui_hit())])
    status, _, body = call(base, f"/reports/{WID}/hits.json", token="tok-anna")
    assert status == 200
    data = json.loads(body)
    assert data["workspace"] == WID
    assert len(data["hits"]) == 2
    status, _, body = call(base, f"/reports/{WID}/hits.json?after=1", token="tok-anna")
    after = json.loads(body)
    assert len(after["hits"]) == 1
    assert after["hits"][0]["id"] == 2
    assert call(base, f"/reports/{WID}/hits.json?after=x", token="tok-anna")[0] == 400


def test_hits_json_ignores_other_query_keys(service):
    base, hits_dir = service
    write_hits(hits_dir, WID, [_record(WID, _agui_hit())])
    status, _, _ = call(base, f"/reports/{WID}/hits.json?foo=bar", token="tok-anna")
    assert status == 200


def test_hits_json_status_null_without_a_status_file(service):
    base, hits_dir = service
    write_hits(hits_dir, WID, [_record(WID, _agui_hit())])
    data = json.loads(call(base, f"/reports/{WID}/hits.json", token="tok-anna")[2])
    assert data["status"] is None


# --- Review Focus 1: hostile output ---------------------------------------------------------------

def test_page_escapes_titles_and_excerpts(service):
    base, hits_dir = service
    hit = _record(WID, _agui_hit() | {
        "session": {"id": "s1", "title": HOSTILE},
        "excerpt": {"text": f"{HOSTILE} FCANARY-TEST01", "start": len(HOSTILE) + 1,
                    "end": len(HOSTILE) + 1 + len("FCANARY-TEST01")},
    })
    write_hits(hits_dir, WID, [hit])
    status, _, body = call(base, f"/reports/{WID}/hits", token="tok-anna")
    text = body.decode()
    assert status == 200
    assert "<img" not in text
    assert "&lt;img src=x onerror=alert(1)&gt;" in text
    assert "<mark>FCANARY-TEST01</mark>" in text


def test_csp_and_no_inline_script(service):
    base, hits_dir = service
    write_hits(hits_dir, WID, [_record(WID, _agui_hit())])
    status, headers, body = call(base, f"/reports/{WID}/hits", token="tok-anna")
    assert status == 200
    assert "Content-Security-Policy" in headers
    text = body.decode()
    assert "<script>" not in text
    for tag in re.findall(r"<script\b[^>]*>", text):
        assert "src=" in tag


# --- the event stream (decisions 6, 8, 10; ruling 7; Review Focus 5) ------------------------------

import http.client  # noqa: E402
import queue  # noqa: E402
import socket  # noqa: E402
import time  # noqa: E402

from conftest import SESSION, WORKSPACE, make_fake_instance  # noqa: E402

import canary_watch  # noqa: E402

READ_BACKSTOP = 30  # seconds: a stream read that never returns ends the reader thread, not the test run


class Stream:
    """An open event stream, read by a daemon thread into a queue, so a test waits on the queue with
    a deadline and never blocks on the socket (a read that times out cannot be resumed)."""

    def __init__(self, base: str, wid: str, token: str | None = "tok-anna", query: str = "",
                 last_event_id: str | None = None):
        host = urllib.parse.urlsplit(base).netloc
        self.conn = http.client.HTTPConnection(host, timeout=READ_BACKSTOP)
        headers = {"Cookie": f"{sr.COOKIE}={token}"} if token else {}
        if last_event_id is not None:
            headers["Last-Event-ID"] = last_event_id
        self.conn.request("GET", f"/reports/{wid}/hits/events{query}", headers=headers)
        self.sock = self.conn.sock  # the response's file keeps it open past conn.close()
        self.resp = self.conn.getresponse()
        self.status, self.headers = self.resp.status, dict(self.resp.getheaders())
        self.events: queue.Queue = queue.Queue()
        self.raw: list[str] = []
        if self.status == 200:
            threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        event: dict = {}
        try:
            while True:
                line = self.resp.fp.readline()
                if not line:
                    break
                text = line.decode().rstrip("\n")
                self.raw.append(text)
                if text == "":
                    if event:
                        self.events.put(event)
                    event = {}
                elif text.startswith(":"):
                    self.events.put({"comment": text[1:].strip()})
                else:
                    key, _, value = text.partition(":")
                    event[key] = value[1:] if value.startswith(" ") else value
        except (OSError, ValueError):  # ValueError: read after close() from the test's thread
            pass
        self.events.put(None)  # the stream ended

    def next(self, timeout: float, event: str | None = "hit") -> dict | None:
        """The next event of this type (comments and other events skipped) within `timeout` seconds,
        else None; also None once the stream ended."""
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                return None
            try:
                got = self.events.get(timeout=left)
            except queue.Empty:
                return None
            if got is None:
                self.events.put(None)
                return None
            if event is None or got.get("event") == event:
                return got

    def ended(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if self.events.get(timeout=max(0.01, deadline - time.monotonic())) is None:
                    return True
            except queue.Empty:
                return False
        return False

    def close(self):
        """Really closes the connection (shutdown, so the server's next writes fail)."""
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()
        self.resp.close()
        self.conn.close()


@pytest.fixture
def streams():
    opened: list[Stream] = []

    def open_stream(*args, **kwargs) -> Stream:
        s = Stream(*args, **kwargs)
        opened.append(s)
        return s
    yield open_stream
    for s in opened:
        s.close()


def append(hits_dir: Path, wid: str, record: dict) -> int:
    return HitsFile(str(hits_dir / f"{wid}.jsonl")).append(dict(record))


def test_stream_headers(service, streams):
    base, _ = service
    s = streams(base, WID)
    assert s.status == 200
    assert s.headers["Content-Type"] == "text/event-stream"
    assert s.headers["Cache-Control"] == "no-store"
    assert s.headers["X-Accel-Buffering"] == "no"
    assert s.headers["Content-Security-Policy"] == sr.CSP
    assert "Content-Length" not in s.headers


def test_new_line_reaches_stream_within_2s(service, streams):
    base, hits_dir = service
    s = streams(base, WID)
    started = time.monotonic()
    append(hits_dir, WID, _record(WID, _agui_hit()))
    event = s.next(2.0)
    assert event is not None, "no hit within 2 s"
    assert time.monotonic() - started < 2.0
    assert event["id"] == "1"
    data = json.loads(event["data"])
    hit = HitsFile(str(hits_dir / f"{WID}.jsonl")).read()[0]
    assert data == {"id": 1, "kind": "touched", "loud": True, "type": hit["canary"]["type"],
                    "frontend": "agui", "html": hits_view.hit_html(hit)}


def test_events_resume_past_end(service, streams):
    base, hits_dir = service
    write_hits(hits_dir, WID, [_record(WID, _agui_hit()), _record(WID, _openwebui_hit())])
    s = streams(base, WID, last_event_id="99")
    assert s.status == 200
    assert s.next(1.5) is None  # nothing replayed, no error
    append(hits_dir, WID, _record(WID, _agui_hit()))
    event = s.next(2.0)
    assert event is not None and event["id"] == "3"


def test_events_before_file_exists(service, streams):
    base, hits_dir = service
    s = streams(base, WID)
    assert s.status == 200
    assert s.next(1.0) is None
    append(hits_dir, WID, _record(WID, _agui_hit()))
    event = s.next(2.0)
    assert event is not None and event["id"] == "1"


def test_last_event_id_catch_up(service, streams):
    base, hits_dir = service
    write_hits(hits_dir, WID, [_record(WID, _agui_hit()), _record(WID, _openwebui_hit()),
                               _record(WID, _agui_hit())])
    s = streams(base, WID, last_event_id="1")
    assert [s.next(2.0)["id"], s.next(2.0)["id"]] == ["2", "3"]
    assert s.next(1.0) is None


def test_after_query_when_no_last_event_id(service, streams):
    base, hits_dir = service
    write_hits(hits_dir, WID, [_record(WID, _agui_hit()), _record(WID, _openwebui_hit())])
    s = streams(base, WID, query="?after=1")
    assert s.next(2.0)["id"] == "2"
    s2 = streams(base, WID, query="?after=0", last_event_id="2")  # the header wins
    assert s2.next(1.0) is None
    s3 = streams(base, WID, last_event_id="x")  # not an integer: from the start
    assert s3.next(2.0)["id"] == "1"


def test_status_event(service, streams):
    base, hits_dir = service
    s = streams(base, WID)
    now = time.time()
    last_poll = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    write_status(hits_dir, WID, {"state": "running", "since": last_poll, "last_poll": last_poll})
    event = s.next(2.0, event="status")
    assert event is not None
    data = json.loads(event["data"])
    assert data["line"].startswith("running · watched ") and data["empty"] == hits_view.NO_HITS
    write_status(hits_dir, WID, {"state": "stopped", "note": "archive incomplete"})
    event = s.next(2.0, event="status")
    assert event is not None
    assert json.loads(event["data"]) == {"line": "stopped · archive incomplete", "empty": hits_view.NO_HITS}


def test_status_event_resent_unchanged_past_refresh(server, streams):
    """A status file that never changes once watched would otherwise leave "watched N s ago"
    frozen at the age it had when first sent (review round, finding 1): past
    `stream_status_refresh`, the same file is resent anyway, with a larger age. Collects status
    events over a window rather than checking only the next one: a `stat` can occasionally report
    an unchanged file as changed (observed on this filesystem), which would resend early with the
    same age; the real refresh is the one that eventually shows the age caught up."""
    base, hits_dir, srv = server
    srv.stream_status_refresh = 2.0
    s = streams(base, WID)
    last_poll = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 10))
    write_status(hits_dir, WID, {"state": "running", "since": last_poll, "last_poll": last_poll})
    first = s.next(2.0, event="status")
    assert first is not None
    first_age = int(re.search(r"(\d+) s ago", json.loads(first["data"])["line"]).group(1))
    deadline = time.monotonic() + 8.0
    last_age = first_age
    while last_age < first_age + 2 and time.monotonic() < deadline:
        event = s.next(max(0.1, deadline - time.monotonic()), event="status")
        assert event is not None, "no further status event before the deadline"
        last_age = int(re.search(r"(\d+) s ago", json.loads(event["data"])["line"]).group(1))
    assert last_age >= first_age + 2  # a resend with the age caught up, not just the file unchanged


def test_ping_when_idle(server, streams):
    base, _, srv = server
    srv.stream_ping = 0.2
    s = streams(base, WID)
    assert s.next(2.0, event=None) == {"comment": "ping"}


def test_stream_ends_after_its_lifetime(server, streams):
    base, _, srv = server
    srv.stream_seconds = 0.5
    s = streams(base, WID)
    assert s.ended(5.0)


def test_streams_capped_503(server, streams):
    base, _, srv = server
    srv.stream_max, srv.stream_ping = 1, 0.1
    first = streams(base, WID)
    assert first.status == 200
    refused = streams(base, WID)
    assert refused.status == 503 and json.loads(refused.resp.read()) == {"error": "too many open streams"}
    first.close()
    deadline = time.monotonic() + 5
    while True:  # the slot is freed once the server's next writes (pings) fail on the closed socket
        again = streams(base, WID)
        if again.status == 200 or time.monotonic() > deadline:
            break
        time.sleep(0.2)
    assert again.status == 200


def test_write_timeout_set_before_streaming(service, streams, monkeypatch):
    """Without a write timeout, a client that stops reading blocks `wfile.write` forever (past the
    30-minute bound, holding its stream slot): `hits_events` sets one on the connection before it
    starts writing. A real stuck-client write block is OS-buffer-dependent and slow to force
    reliably, so this checks the one thing that makes the existing `TimeoutError` catch real: the
    socket gets `settimeout(stream_write_timeout)`, not the default (blocking forever)."""
    base, _ = service
    calls = []
    real_settimeout = socket.socket.settimeout
    monkeypatch.setattr(socket.socket, "settimeout", lambda self, v: (calls.append(v), real_settimeout(self, v)))
    s = streams(base, WID)
    assert s.status == 200
    assert sr.STREAM_WRITE_TIMEOUT in calls


def test_events_access_rule(service):
    base, _ = service
    assert call(base, f"/reports/{WID}/hits/events", token="tok-bob")[0] == 403
    assert call(base, f"/reports/{WID}/hits/events")[0] == 401  # no redirect
    assert call(base, "/reports/not-a-uuid/hits/events", token="tok-anna")[0] == 404


def test_no_route_takes_a_token(service, streams):
    """Decision 10: no URL carries a canary value. The routes table names no path parameter but the
    workspace id (and the service's own static files); a canary in a path is a 404, in any query key
    but `after` it is ignored."""
    routes = re.findall(r"^\s+(?:GET|PUT|POST)\s+(\S+)", sr.__doc__, re.M)
    assert f"{sr.PREFIX}/<id>/hits/events" in routes
    params = {p for r in routes for p in re.findall(r"<[^>]+>", r)}
    assert params == {"<id>", "<file>"}
    assert [r for r in routes if "<file>" in r] == [f"{sr.PREFIX}/static/<file>"]
    base, hits_dir = service
    write_hits(hits_dir, WID, [_record(WID, _agui_hit())])
    for path in (f"/reports/{WID}/hits/FCANARY-TEST01", "/reports/FCANARY-TEST01/hits",
                 "/reports/FCANARY-TEST01/hits.json", f"/reports/{WID}/hits/events/FCANARY-TEST01",
                 "/reports/FCANARY-TEST01"):
        assert call(base, path, token="tok-anna")[0] == 404, path
    plain = json.loads(call(base, f"/reports/{WID}/hits.json", token="tok-anna")[2])
    keyed = json.loads(call(base, f"/reports/{WID}/hits.json?token=FCANARY-TEST01&canary=FCANARY-TEST01",
                            token="tok-anna")[2])
    assert keyed == plain
    s = streams(base, WID, query="?token=FCANARY-TEST01")
    assert s.status == 200 and s.next(2.0)["id"] == "1"


def test_service_logs_no_token(service, streams, capfd):
    base, hits_dir = service
    write_hits(hits_dir, WID, [_record(WID, _agui_hit())])
    assert call(base, f"/reports/{WID}/hits?x=FCANARY-TEST01", token="tok-anna")[0] == 200
    assert call(base, f"/reports/{WID}/hits.json?x=FCANARY-TEST01", token="tok-anna")[0] == 200
    s = streams(base, WID, query="?x=FCANARY-TEST01")
    assert s.next(2.0) is not None
    append(hits_dir, WID, _record(WID, _openwebui_hit()))
    assert s.next(2.0) is not None
    s.close()
    time.sleep(0.6)  # one stream poll after the close
    out, err = capfd.readouterr()
    assert f"/reports/{WID}/hits/events" in out  # the log was captured
    assert "CANARY" not in out + err


def test_latency_fake_instance(tmp_path, coder, streams):
    """Decision 8: a journal line on the (fake) instance reaches the participant's open stream within
    10 s: the watcher (slice 2) ticking every second, the service reading the same hits directory."""
    transport, output_root, reports_dir, runs_dir = make_fake_instance(tmp_path)
    hits_dir = tmp_path / "hits"
    watcher = canary_watch.Watcher(str(hits_dir), str(reports_dir), str(runs_dir), str(output_root), transport)
    srv = sr.make_server("127.0.0.1:0", str(reports_dir), coder, str(hits_dir))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    stop = threading.Event()

    def ticking():
        while not stop.is_set():
            watcher.tick(time.time())
            stop.wait(1.0)
    ticker = threading.Thread(target=ticking, daemon=True)
    ticker.start()
    try:
        s = streams(f"http://127.0.0.1:{srv.server_port}", WORKSPACE, token="tok-root")
        assert s.status == 200
        journal = Path(transport.paths["sessions"]) / f"{SESSION}.jsonl"
        started = time.monotonic()
        journal.write_text((FIXTURES / "agui-journals" / "s1.jsonl").read_text())
        touched = None
        while touched is None and time.monotonic() - started < 10:
            event = s.next(10 - (time.monotonic() - started))
            if event is None:
                break
            if json.loads(event["data"])["kind"] == "touched":
                touched = event
        assert touched is not None, "no touched hit within 10 s"
        assert "FCANARY-TEST01" in json.loads(touched["data"])["html"]
    finally:
        stop.set()
        ticker.join(5)
        srv.shutdown()


# --- the stream bounded and hardened ----------------------------------------------------------------

def _line(record: dict, n: int) -> bytes:
    return (json.dumps(record | {"id": n}) + "\n").encode()


def test_partial_line_waits_until_complete(service, streams):
    base, hits_dir = service
    second = _line(_record(WID, _openwebui_hit()), 2)
    path = hits_dir / f"{WID}.jsonl"
    path.write_bytes(_line(_record(WID, _agui_hit()), 1) + second[:40])
    s = streams(base, WID)
    assert s.next(2.0)["id"] == "1"
    assert s.next(1.0) is None
    with open(path, "ab") as f:
        f.write(second[40:])
    event = s.next(2.0)
    assert event is not None and event["id"] == "2"
    assert json.loads(event["data"])["frontend"] == "openwebui"


def test_line_longer_than_a_read_is_skipped(server, streams):
    """A line over one read (1 MiB in service, 4 kB here) is passed over, not waited on forever; it
    still counts as a line, so the next hit's id is its HitsFile line number."""
    base, hits_dir, srv = server
    srv.stream_read = 4096
    path = hits_dir / f"{WID}.jsonl"
    path.write_bytes(_line(_record(WID, _agui_hit()), 1) + b'{"x": "' + b"y" * 10_000 + b'"}\n')
    s = streams(base, WID)
    assert s.next(2.0)["id"] == "1"
    assert append(hits_dir, WID, _record(WID, _agui_hit())) == 3
    event = s.next(3.0)
    assert event is not None and event["id"] == "3"


def test_catch_up_in_bounded_reads(server, streams):
    base, hits_dir, srv = server
    srv.stream_read, srv.stream_poll = 4096, 0.05
    write_hits(hits_dir, WID, [_record(WID, _agui_hit()) for _ in range(30)])
    assert (hits_dir / f"{WID}.jsonl").stat().st_size > 3 * 4096
    s = streams(base, WID, last_event_id="28")
    assert [s.next(3.0)["id"], s.next(3.0)["id"]] == ["29", "30"]
    assert s.next(0.5) is None


@pytest.mark.parametrize("change", ["cut", "replaced"])
def test_stream_ends_when_the_file_is_cut_or_replaced(service, streams, change):
    base, hits_dir = service
    write_hits(hits_dir, WID, [_record(WID, _agui_hit()), _record(WID, _openwebui_hit())])
    s = streams(base, WID)
    assert [s.next(2.0)["id"], s.next(2.0)["id"]] == ["1", "2"]
    path = hits_dir / f"{WID}.jsonl"
    if change == "cut":
        path.write_bytes(path.read_bytes()[:10])
    else:
        fresh = hits_dir / "fresh.jsonl"
        fresh.write_bytes(path.read_bytes() + b"\n")
        fresh.replace(path)
    assert s.ended(3.0)


def test_unreadable_hits_file_ends_with_one_log_line(service, streams, capfd):
    base, hits_dir = service
    (hits_dir / f"{WID}.jsonl").mkdir()  # open() fails with an OSError that is not FileNotFoundError
    s = streams(base, WID)
    assert s.ended(3.0)
    out, _ = capfd.readouterr()
    assert f"hits stream {WID}: IsADirectoryError, ended\n" in out
    assert str(hits_dir) not in out


# --- Task 11: the page script and the Coder app -------------------------------------------------

def test_page_loads_hits_script(service):
    base, hits_dir = service
    write_hits(hits_dir, WID, [_record(WID, _agui_hit())])
    status, _, body = call(base, f"/reports/{WID}/hits", token="tok-anna")
    assert status == 200
    text = body.decode()
    assert f'<script src="{sr.PREFIX}/static/hits.js">' in text
    assert f'data-wid="{WID}"' in text
    assert "Group by run" in text
    assert 'data-session="s1"' in text
    assert 'data-run="r1"' in text
    status, headers, _ = call(base, f"{sr.PREFIX}/static/hits.js")
    assert status == 200
    assert headers["Content-Type"].startswith("text/javascript")


def test_coder_app_hits():
    main_tf = Path(__file__).resolve().parents[2] / "coder" / "template" / "main.tf"
    if not main_tf.is_file():
        pytest.skip("main.tf not present in this checkout")
    text = main_tf.read_text()
    assert 'slug         = "hits"' in text
    assert "/reports/${data.coder_workspace.me.id}/hits" in text
