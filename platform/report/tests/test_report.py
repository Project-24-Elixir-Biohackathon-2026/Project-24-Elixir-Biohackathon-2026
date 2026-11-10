"""The report service against a fake Coder API: login, read for anyone, write for the owner and admins,
If-Match conflicts, the size limit, sanitized rendering and the headers every page carries."""
from __future__ import annotations

import hashlib
import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sperange_report as sr  # noqa: E402

WID = "11111111-2222-4333-8444-555555555555"
OTHER = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
USERS = {
    "tok-anna": {"username": "anna", "email": "anna@example.org", "roles": [{"name": "member"}]},
    "tok-bob": {"username": "bob", "email": "bob@example.org", "roles": []},
    "tok-root": {"username": "admin", "email": "admin@example.org", "roles": [{"name": "owner"}]},
}


class FakeCoder(BaseHTTPRequestHandler):
    def do_GET(self):
        tok = self.headers.get("Coder-Session-Token", "")
        if "Cookie" in self.headers:
            FakeCoder.saw_cookie = True
        user = USERS.get(tok)
        if self.path == "/api/v2/users/me":
            if user is None:
                return self.reply(401, {"message": "no"})
            return self.reply(200, user)
        if self.path.startswith("/api/v2/workspaces/"):
            if user is None:
                return self.reply(401, {"message": "no"})
            wid = self.path.rsplit("/", 1)[1]
            if wid == WID and user["username"] in ("anna", "admin"):
                return self.reply(200, {"id": wid, "latest_build": {"status": "running"}})
            return self.reply(404, {"message": "not found"})
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


FakeCoder.saw_cookie = False


@pytest.fixture(scope="module")
def coder():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeCoder)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.fixture
def service(tmp_path, coder):
    (tmp_path / f"{WID}.md").write_text("# Run report\n\n## Goal\n\n*What did you try?*\n")
    (tmp_path / f"{WID}.json").write_text(json.dumps({
        "owner": "anna", "owner_email": "anna@example.org", "workspace": "tm-test", "instance": "cw-anna-tm-test",
        "created": "2026-11-06 15:00 UTC",
        "template_sha256": hashlib.sha256((tmp_path / f"{WID}.md").read_bytes()).hexdigest(),
    }))
    srv = sr.make_server("127.0.0.1:0", str(tmp_path), coder)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", tmp_path
    srv.shutdown()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def call(base, path, token=None, method="GET", body=None, headers=None):
    h = dict(headers or {})
    if token:
        h["Cookie"] = f"{sr.COOKIE}={token}"
    h.setdefault("Host", "portal.example.org")
    req = urllib.request.Request(base + path, data=body, method=method, headers=h)
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=10) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def put(base, path, token, text, etag, origin=None):
    h = {"If-Match": etag, "Content-Type": "text/markdown"}
    if origin:
        h["Origin"] = origin
    return call(base, path, token, "PUT", text.encode(), h)


# --- login ------------------------------------------------------------------------------------------------

def test_without_a_session_a_page_redirects_to_coders_login_with_the_page_as_return_address(service):
    base, _ = service
    status, headers, _ = call(base, f"/reports/{WID}")
    assert status == 302
    assert headers["Location"] == f"/login?redirect=%2Freports%2F{WID}"


def test_without_a_session_the_markdown_routes_answer_401_not_a_redirect(service):
    base, _ = service
    assert call(base, f"/reports/{WID}.md")[0] == 401
    assert put(base, f"/reports/{WID}.md", None, "x", '"e"')[0] == 401
    assert call(base, "/reports/preview", None, "POST", b"# hi")[0] == 401


def test_an_unknown_token_is_no_session(service):
    base, _ = service
    assert call(base, "/reports/", token="tok-nobody")[0] == 302


def test_the_cookie_value_goes_to_coder_as_a_header_only(service):
    base, _ = service
    FakeCoder.saw_cookie = False
    assert call(base, "/reports/", token="tok-anna")[0] == 200
    assert FakeCoder.saw_cookie is False


def test_healthz_and_static_need_no_login(service):
    base, _ = service
    assert call(base, "/reports/healthz")[0] == 200
    status, headers, body = call(base, "/reports/static/report.js")
    assert status == 200 and headers["Content-Type"].startswith("text/javascript") and b"If-Match" in body
    for name, ctype in (("easymde.min.js", "text/javascript"), ("easymde.min.css", "text/css"),
                        ("font-awesome.min.css", "text/css"), ("fontawesome-webfont.woff2", "font/woff2")):
        status, headers, _ = call(base, f"/reports/static/{name}")
        assert status == 200 and headers["Content-Type"].startswith(ctype), name
    assert call(base, "/reports/static/../sperange_report.py")[0] == 404
    assert call(base, "/reports/static/report.txt")[0] == 404


# --- reading ----------------------------------------------------------------------------------------------

def test_everyone_logged_in_reads_the_list_and_any_report(service):
    base, _ = service
    status, _, body = call(base, "/reports/", token="tok-bob")
    assert status == 200 and f"/reports/{WID}" in body.decode() and "tm-test" in body.decode() and "anna" in body.decode()
    status, headers, body = call(base, f"/reports/{WID}.md", token="tok-bob")
    assert status == 200 and body.startswith(b"# Run report") and headers["ETag"] == sr.etag_of(body)
    status, _, body = call(base, f"/reports/{WID}", token="tok-bob")
    page = body.decode()
    assert status == 200 and 'data-can-edit="0"' in page and "Read-only" in page
    assert "(running)" not in page  # bob cannot see anna's workspace in Coder
    # readers get the rendered report, not an editor
    assert "<h1>Run report</h1>" in page and "<h2>Goal</h2>" in page
    assert "<textarea" not in page and "easymde" not in page
    assert f'href="/reports/{WID}.md"' in page


def test_the_owner_and_an_admin_get_the_editable_page_with_the_workspace_state(service):
    base, _ = service
    for tok in ("tok-anna", "tok-root"):
        status, _, body = call(base, f"/reports/{WID}", token=tok)
        page = body.decode()
        assert status == 200 and 'data-can-edit="1"' in page and 'id="save"' in page and "<textarea" in page
        assert "tm-test (running)" in page
        assert "/reports/static/easymde.min.js" in page and "/reports/static/font-awesome.min.css" in page


def test_every_page_carries_the_csp_and_no_inline_script(service):
    base, _ = service
    for path in ("/reports/", f"/reports/{WID}"):
        status, headers, body = call(base, path, token="tok-anna")
        assert status == 200
        assert headers["Content-Security-Policy"].startswith("default-src 'self'; script-src 'self'; style-src")
        assert "'unsafe-inline'" not in headers["Content-Security-Policy"].split("style-src")[0]
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert "<script>" not in body.decode()


def test_unknown_or_malformed_ids_are_404(service):
    base, _ = service
    assert call(base, f"/reports/{OTHER}", token="tok-anna")[0] == 404
    assert call(base, f"/reports/{OTHER}.md", token="tok-anna")[0] == 404
    assert call(base, "/reports/..%2Fsecret", token="tok-anna")[0] == 404
    assert call(base, "/reports/not-a-uuid.md", token="tok-anna")[0] == 404
    assert call(base, "/other", token="tok-anna")[0] == 404


def test_a_sidecar_without_a_report_is_not_listed(service):
    base, root = service
    (root / f"{OTHER}.json").write_text(json.dumps({"owner": "bob", "workspace": "orphan"}))
    _, _, body = call(base, "/reports/", token="tok-anna")
    assert "orphan" not in body.decode()


# --- writing ----------------------------------------------------------------------------------------------

def test_the_owner_saves_with_if_match_and_gets_the_new_etag(service):
    base, root = service
    _, headers, _ = call(base, f"/reports/{WID}.md", token="tok-anna")
    status, headers2, body = put(base, f"/reports/{WID}.md", "tok-anna", "# Run report\n\nfound it\n", headers["ETag"],
                                 origin="https://portal.example.org")
    assert status == 200
    res = json.loads(body)
    assert res["etag"] == headers2["ETag"] == sr.etag_of(b"# Run report\n\nfound it\n") and res["saved"]
    assert (root / f"{WID}.md").read_text() == "# Run report\n\nfound it\n"
    assert not (root / f"{WID}.md.tmp").exists()


def test_an_admin_may_save_a_participants_report(service):
    base, _ = service
    _, headers, _ = call(base, f"/reports/{WID}.md", token="tok-root")
    assert put(base, f"/reports/{WID}.md", "tok-root", "admin edit\n", headers["ETag"])[0] == 200


def test_another_user_may_not_save(service):
    base, root = service
    before = (root / f"{WID}.md").read_text()
    _, headers, _ = call(base, f"/reports/{WID}.md", token="tok-bob")
    status, _, body = put(base, f"/reports/{WID}.md", "tok-bob", "bob was here\n", headers["ETag"])
    assert status == 403 and b"owner" in body
    assert (root / f"{WID}.md").read_text() == before


def test_a_stale_etag_is_a_conflict_and_changes_nothing(service):
    base, root = service
    _, headers, _ = call(base, f"/reports/{WID}.md", token="tok-anna")
    (root / f"{WID}.md").write_text("edited over the terminal\n")
    status, _, body = put(base, f"/reports/{WID}.md", "tok-anna", "my version\n", headers["ETag"])
    assert status == 412 and json.loads(body)["etag"] == sr.etag_of(b"edited over the terminal\n")
    assert (root / f"{WID}.md").read_text() == "edited over the terminal\n"


def test_if_match_is_required(service):
    base, _ = service
    status, _, _ = call(base, f"/reports/{WID}.md", "tok-anna", "PUT", b"x", {"If-Match": ""})
    assert status == 428


def test_a_cross_origin_save_is_refused_before_anything_else(service):
    base, root = service
    before = (root / f"{WID}.md").read_text()
    _, headers, _ = call(base, f"/reports/{WID}.md", token="tok-anna")
    status, _, _ = put(base, f"/reports/{WID}.md", "tok-anna", "evil\n", headers["ETag"], origin="https://evil.example")
    assert status == 403 and (root / f"{WID}.md").read_text() == before


def test_the_size_limit_and_the_encoding(service):
    base, _ = service
    _, headers, _ = call(base, f"/reports/{WID}.md", token="tok-anna")
    assert put(base, f"/reports/{WID}.md", "tok-anna", "x" * (sr.MAX_BYTES + 1), headers["ETag"])[0] == 413
    status, _, _ = call(base, f"/reports/{WID}.md", "tok-anna", "PUT", b"\xff\xfe", {"If-Match": headers["ETag"]})
    assert status == 400


def test_saving_a_report_that_does_not_exist_is_404(service):
    base, _ = service
    assert put(base, f"/reports/{OTHER}.md", "tok-anna", "x", '"e"')[0] == 404


# --- rendering --------------------------------------------------------------------------------------------

def test_preview_renders_markdown_and_disarms_html(service):
    base, _ = service
    md = ("# Title\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n<script>alert(1)</script>\n\n"
          "[x](javascript:alert(1)) [ok](https://example.org) <img src=x onerror=alert(1)>\n\n```sh\nls <dir>\n```\n")
    status, headers, body = call(base, "/reports/preview", "tok-anna", "POST", md.encode(),
                                 {"Content-Type": "text/markdown", "Origin": "https://portal.example.org"})
    assert status == 200 and headers["Content-Type"].startswith("text/html")
    out = body.decode()
    assert "<h1>Title</h1>" in out and "<table>" in out and "<td>2</td>" in out
    assert "<script" not in out and "&lt;script&gt;" in out
    assert "javascript:" not in out and 'href="https://example.org"' in out
    assert "onerror" not in out
    assert "ls &lt;dir&gt;" in out and "<pre><code" in out


@pytest.mark.parametrize("md,expect", [
    ("<a href='https://e.org' onclick='x()'>t</a>", '<a href="https://e.org">t</a>'),
    ("<iframe src='https://e.org'></iframe>", "&lt;iframe src=&#x27;https://e.org&#x27;&gt;&lt;/iframe&gt;"),
    ("<img src='data:text/html;base64,AAA'>", "<img>"),
    ("<!-- hidden --> text", "text"),
    ("<details><summary>s</summary>d</details>", "<details><summary>s</summary>d</details>"),
])
def test_sanitizer_allowlist(md, expect):
    assert expect in sr.render_markdown(md)


def test_listing_is_sorted_by_last_saved(tmp_path):
    import os
    import time
    for i, wid in enumerate(("00000000-0000-4000-8000-000000000001", "00000000-0000-4000-8000-000000000002")):
        (tmp_path / f"{wid}.md").write_text("x")
        (tmp_path / f"{wid}.json").write_text(json.dumps({"owner": "o", "workspace": f"w{i}"}))
        os.utime(tmp_path / f"{wid}.md", (time.time() - 1000 + i * 600,) * 2)  # minutes apart: last_saved is to the minute
    rows = sr.Store(str(tmp_path)).listing()
    assert [r["workspace"] for r in rows] == ["w1", "w0"]
