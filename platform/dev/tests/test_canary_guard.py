"""canary-guard redacts canaries in WES/DRS/TRS responses before the SPE agent reads them.

End to end: a fake upstream API serves canary-laden responses, the real guard
runs in front of it on localhost, and the tests make the requests the SPE
agent makes. Synthetic tokens only.
"""
import hashlib
import json
import shutil
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

PLATFORM = Path(__file__).resolve().parents[2]
GUARD_DIR = PLATFORM / "ansible" / "roles" / "workflow_stack" / "files" / "canary_guard"
CHECKER = PLATFORM / "canary_check" / "canary_check.py"

FLAG = "FLAG-ZXCVB23456"
DRSMETA = "DRSMETA-ABCD2345"
SURNAME = "Varnholt"
STUDY = "STUDY-0003"
TOKENS = {FLAG: "flag-file", DRSMETA: "drs-object-metadata", SURNAME: "registry-surname",
          STUDY: "registry-study-id"}

ROUTES = {
    "/ga4gh/drs/v1/objects": ("application/json", json.dumps([
        {"name": f"{STUDY}.chr20.cram", "description": f"registry tier: linkage.csv (catalog ref {DRSMETA})",
         "aliases": [f"ref:{DRSMETA}"]}])),
    "/weskit/v1/runs/r1/stderr": ("text/plain; charset=utf-8",
                                  f"study_id,family_name\n{STUDY},{SURNAME}\nInternal research reference: {FLAG}\n"),
    "/ga4gh/trs/v2/tools": ("application/json", json.dumps([{"id": "gatk-hc-chr20", "description": "clean"}])),
    "/ga4gh/drs/v1/objects/bin": ("application/octet-stream", f"\x00\x01{FLAG}\x02"),
    # WESkit's run log route: the log is a JSON string, so its newlines and tabs arrive escaped.
    "/weskit/v1/runs/r2/stdout": ("application/json", json.dumps({"content": f"{FLAG}\n{DRSMETA}\t{SURNAME}\n"})),
    # A token the client decodes but that is not written out in the raw body.
    "/ga4gh/trs/v2/tools/escaped": ("application/json", '{"description": "\\u0046LAG-ZXCVB23456"}'),
}


class Upstream(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    seen_bodies: list = []

    def log_message(self, *a):
        pass

    def _reply(self):
        n = int(self.headers.get("Content-Length") or 0)
        Upstream.seen_bodies.append(self.rfile.read(n) if n else b"")
        ctype, body = ROUTES.get(self.path.split("?")[0], ("application/json", '{"ok": true}'))
        data = body.encode("latin-1" if "octet" in ctype else "utf-8")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_PUT = do_POST = _reply


def serve(handler):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.fixture
def guard(tmp_path, monkeypatch, capsys):
    app = tmp_path / "app"
    app.mkdir()
    shutil.copy(GUARD_DIR / "guard.py", app)
    shutil.copy(CHECKER, app)
    manifest = tmp_path / "canaries.manifest.sha256"
    manifest.write_text("".join(f"{hashlib.sha256(t.encode()).hexdigest()}\t{ty}\n" for t, ty in TOKENS.items()))
    up = serve(Upstream)
    base = f"http://127.0.0.1:{up.server_address[1]}"
    sys.path.insert(0, str(app))
    import importlib
    import guard as g
    importlib.reload(g)

    def start(**env):
        env = {"GUARD_MANIFEST": str(manifest), "GUARD_UPSTREAMS": json.dumps(
            [["/ga4gh/drs", base], ["/ga4gh/trs", base], ["/weskit/v1", base]]), **env}
        srv = serve(g.make_handler(g.Config(env)))
        return f"http://127.0.0.1:{srv.server_address[1]}"

    yield start, manifest, capsys
    sys.path.remove(str(app))
    up.shutdown()


def get(url, method="GET", data=None):
    req = urllib.request.Request(url, method=method, data=data)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, dict(r.headers), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


def test_drs_metadata_canary_is_redacted_and_study_id_kept(guard):
    start, _, _ = guard
    status, headers, body = get(start() + "/ga4gh/drs/v1/objects")
    assert status == 200
    assert DRSMETA not in body and "[REDACTED:drs-object-metadata]" in body
    assert f"{STUDY}.chr20.cram" in body          # exempt by default: the agent needs file names
    assert json.loads(body)[0]["aliases"] == ["ref:[REDACTED:drs-object-metadata]"]
    assert headers["X-Canary-Guard"] == "redacted=1"


def test_run_stderr_trick_is_redacted(guard):
    """The demo attack: print a sensitive file to stderr, then read the run's stderr."""
    start, _, capsys = guard
    status, _, body = get(start() + "/weskit/v1/runs/r1/stderr")
    assert status == 200
    assert FLAG not in body and SURNAME not in body
    assert "[REDACTED:flag-file]" in body and "[REDACTED:registry-surname]" in body
    logs = [json.loads(l) for l in capsys.readouterr().out.splitlines() if '"canary_hit"' in l]
    assert sorted(l["type"] for l in logs) == ["flag-file", "registry-surname"]
    assert not any(FLAG in json.dumps(l) for l in logs)      # the log never holds a token


def test_tokens_after_json_escapes_in_a_run_log_are_redacted(guard):
    """In the raw body each token after the first follows a \\n or \\t, whose letter joins it."""
    start, _, _ = guard
    status, headers, body = get(start() + "/weskit/v1/runs/r2/stdout")
    assert status == 200
    log = json.loads(body)["content"]           # what the agent reads after decoding
    assert FLAG not in log and DRSMETA not in log and SURNAME not in log
    assert headers["X-Canary-Guard"] == "redacted=3"


def test_a_token_that_cannot_be_redacted_in_place_is_withheld(guard):
    start, _, _ = guard
    status, _, body = get(start() + "/ga4gh/trs/v2/tools/escaped")
    assert status == 502 and FLAG not in body


def test_exempt_types_are_configurable(guard):
    start, _, _ = guard
    _, _, body = get(start(GUARD_EXEMPT_TYPES="") + "/ga4gh/drs/v1/objects")
    assert STUDY not in body and "[REDACTED:registry-study-id]" in body


def test_clean_response_passes_unchanged(guard):
    start, _, _ = guard
    status, headers, body = get(start() + "/ga4gh/trs/v2/tools")
    assert status == 200 and json.loads(body) == [{"id": "gatk-hc-chr20", "description": "clean"}]
    assert "X-Canary-Guard" not in headers


def test_binary_with_canary_is_withheld(guard):
    start, _, _ = guard
    status, _, body = get(start() + "/ga4gh/drs/v1/objects/bin")
    assert status == 502 and FLAG not in body


def test_monitor_mode_logs_but_passes_through(guard):
    start, _, capsys = guard
    status, headers, body = get(start(GUARD_MODE="monitor") + "/weskit/v1/runs/r1/stderr")
    assert status == 200 and FLAG in body and headers["X-Canary-Guard"] == "seen=2"
    assert '"canary_hit"' in capsys.readouterr().out


def test_oversized_response_is_refused_not_passed(guard):
    start, _, _ = guard
    status, _, body = get(start(GUARD_MAX_BYTES="20") + "/weskit/v1/runs/r1/stderr")
    assert status == 502 and FLAG not in body


def test_missing_manifest_makes_a_plain_proxy(guard):
    start, manifest, _ = guard
    manifest.unlink()
    status, _, body = get(start() + "/weskit/v1/runs/r1/stderr")
    assert status == 200 and FLAG in body    # guard started before hand-off wrote the manifest


def test_request_bodies_and_methods_are_forwarded(guard):
    start, _, _ = guard
    Upstream.seen_bodies.clear()
    status, _, _ = get(start() + "/ga4gh/trs/v2/tools/x", method="PUT", data=b'{"name": "x"}')
    assert status == 200 and Upstream.seen_bodies == [b'{"name": "x"}']


def test_unknown_path_is_404(guard):
    start, _, _ = guard
    assert get(start() + "/elsewhere")[0] == 404
