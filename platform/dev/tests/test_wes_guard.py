"""wes_guard.py: WES writes carry no attachment and only TRS URIs of the stack's TRS."""
import http.client
import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from ansible_render import ANSIBLE

TRS = "trs://trs-filer.weskit.internal:8080/wes-drs-smoke/1.0/NFL/main.nf"


@pytest.fixture(scope="module")
def guard():
    spec = importlib.util.spec_from_file_location("wes_guard", ANSIBLE / "roles/workflow_stack/files/wes_guard.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def multipart(fields, files=()):
    b = "b0undary"
    out = "".join(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n' for k, v in fields.items())
    out += "".join(f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{n}"\r\n'
                   f"Content-Type: text/plain\r\n\r\n{c}\r\n" for k, n, c in files)
    return f"multipart/form-data; boundary={b}", (out + f"--{b}--\r\n").encode()


def test_trs_run_passes(guard):
    assert guard.check(*multipart({"workflow_url": TRS, "workflow_type": "NFL"})) is None


@pytest.mark.parametrize("files", [[("workflow_attachment", "nextflow.config", "x")],
                                   [("other", "a.txt", "x")]])
def test_any_file_part_is_refused(guard, files):
    status, reason = guard.check(*multipart({"workflow_url": TRS}, files))
    assert status == 403 and "attachment" in reason


@pytest.mark.parametrize("disp", ["filename*=UTF-8''", "filename*=''", "filename*0=a.txt"])
def test_rfc2231_file_parts_are_refused(guard, disp):
    # werkzeug files these parts as uploads although get_filename() gives None
    ctype, body = multipart({"workflow_url": TRS})
    body = body.replace(b"--b0undary--", b'--b0undary\r\nContent-Disposition: form-data; name="foo"; '
                        + disp.encode() + b"\r\n\r\nx\r\n--b0undary--")
    status, reason = guard.check(ctype, body)
    assert status == 403 and "attachment" in reason


@pytest.mark.parametrize("url", ["main.nf", "file:main.nf", "https://evil.example/m.nf",
                                 "trs://other.host:8080/t/1/NFL/main.nf", TRS + "?x=1"])
def test_non_trs_urls_are_refused(guard, url):
    assert guard.check(*multipart({"workflow_url": url}))[0] == 403
    assert guard.check("application/json", json.dumps({"workflow_url": url}).encode())[0] == 403
    assert guard.check("application/x-www-form-urlencoded", f"workflow_url={url}".encode())[0] == 403


def test_malformed_and_unknown_bodies_fail_closed(guard):
    assert guard.check("multipart/form-data", b"--x\r\nno boundary")[0] == 400
    assert guard.check("application/json", b"{not json")[0] == 400
    assert guard.check("text/plain", b"workflow_url=main.nf")[0] == 415
    assert guard.check("", b"") is None  # POST /runs/ID/cancel has no body


def raw_multipart(boundary, parts):
    """parts: list of (header lines, value) under one boundary."""
    out = "".join(f"--{boundary}\r\n" + "".join(h + "\r\n" for h in hs) + f"\r\n{v}\r\n" for hs, v in parts)
    return (out + f"--{boundary}--\r\n").encode()


def test_duplicate_content_type_params_are_refused(guard):
    # Python's email parser takes the first boundary, werkzeug the last: an attachment
    # under AA would reach WESkit unseen.
    body = raw_multipart("AA", [(['Content-Disposition: form-data; name="workflow_url"'], TRS)])
    assert guard.check("multipart/form-data; boundary=AA; boundary=ZZ", body)[0] == 400
    assert guard.check("application/json; charset=utf-8; charset=latin-1", b"{}")[0] == 400


def test_duplicate_disposition_params_are_refused(guard):
    body = raw_multipart("b", [(['Content-Disposition: form-data; name="x"; name="workflow_url"'], "main.nf")])
    assert guard.check("multipart/form-data; boundary=b", body)[0] == 400


def test_part_with_transfer_encoding_is_refused(guard):
    import base64
    body = raw_multipart("b", [(['Content-Disposition: form-data; name="workflow_url"',
                                 "Content-Transfer-Encoding: base64"], base64.b64encode(TRS.encode()).decode())])
    assert guard.check("multipart/form-data; boundary=b", body)[0] == 400


@pytest.fixture
def proxy(guard):
    seen = []

    class Upstream(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append((self.path, self.rfile.read(int(self.headers["Content-Length"] or 0)),
                         self.headers.get_all("Content-Type")))
            body = b'{"run_id": "r1"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    up = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    gs = guard.serve("127.0.0.1", 0, "127.0.0.1", up.server_address[1])
    for s in (up, gs):
        threading.Thread(target=s.serve_forever, daemon=True).start()
    try:
        yield gs.server_address[1], seen
    finally:
        gs.shutdown()
        up.shutdown()


def send(port, headers, body):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.putrequest("POST", "/ga4gh/wes/v1/runs", skip_accept_encoding=True)
    for k, v in headers:
        c.putheader(k, v)
    c.endheaders(body)
    r = c.getresponse()
    out = r.status, json.loads(r.read())
    c.close()
    return out


def test_proxy_forwards_allowed_and_blocks_refused(proxy):
    port, seen = proxy

    def post(ctype, body):
        return send(port, [("Content-Type", ctype), ("Content-Length", str(len(body)))], body)
    assert post(*multipart({"workflow_url": TRS})) == (200, {"run_id": "r1"})
    status, body = post(*multipart({"workflow_url": "main.nf"}))
    assert status == 403 and body["status_code"] == 403
    assert len(seen) == 1 and seen[0][0] == "/ga4gh/wes/v1/runs"
    assert seen[0][2] == ["multipart/form-data; boundary=b0undary"]


@pytest.mark.parametrize("dup", ["Content-Type", "Content-Length", "Transfer-Encoding"])
def test_proxy_refuses_duplicate_framing_headers(proxy, dup):
    # The guard read the first Content-Type, the forwarded dict kept the last: a
    # urlencoded check let a multipart attachment through to WESkit.
    port, seen = proxy
    mp_type, mp_body = multipart({"workflow_url": TRS}, [("workflow_attachment", "nextflow.config", "x")])
    first = {"Content-Type": "application/x-www-form-urlencoded", "Content-Length": str(len(mp_body)),
             "Transfer-Encoding": "identity"}
    second = dict(first, **{"Content-Type": mp_type})
    headers = [("Content-Type", first["Content-Type"]), ("Content-Length", first["Content-Length"])]
    if dup == "Transfer-Encoding":
        headers.append((dup, first[dup]))
    headers.append((dup, second[dup]))
    status, _ = send(port, headers, mp_body)
    assert status == 400 and seen == []
