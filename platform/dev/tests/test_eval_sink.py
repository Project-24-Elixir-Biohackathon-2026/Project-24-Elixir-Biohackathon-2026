"""The test receiver (spec part 04, *The test receiver*): logs what it gets; the sandbox finds it only when on."""
import importlib.util
import json
import os
import socket
import subprocess
import threading
import urllib.request
from pathlib import Path

import yaml

from ansible_render import GOLDEN, render

ANSIBLE = Path(__file__).resolve().parents[2] / "ansible"
INSTANCE = ANSIBLE.parent / "instance"
spec = importlib.util.spec_from_file_location("sink", ANSIBLE / "roles/eval_sink/files/sink.py")
sink = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sink)


def test_the_log_exists_empty_once_the_receiver_starts(tmp_path):
    # A missing log means "no receiver" to isolation.SINK_LOG's reader; a running one with no requests is empty.
    log = tmp_path / "requests.jsonl"
    server = sink.make_server(("127.0.0.1", 0), log)
    try:
        assert log.is_file() and log.read_text() == ""
    finally:
        server.server_close()


def test_a_request_is_logged_as_one_json_line(tmp_path):
    log = tmp_path / "requests.jsonl"
    server = sink.make_server(("127.0.0.1", 0), log)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/upload?x=1"
        req = urllib.request.Request(url, data="summary é".encode(), method="POST")
        assert urllib.request.urlopen(req, timeout=5).status == 200
        urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/", timeout=5)
    finally:
        server.shutdown()
    lines = [json.loads(line) for line in log.read_text().splitlines()]
    assert lines[0] == {"method": "POST", "host": f"127.0.0.1:{server.server_port}", "path": "/upload?x=1",
                        "body": "summary é"}
    assert lines[1]["method"] == "GET" and lines[1]["body"] == ""


def raw_requests(tmp_path, *payloads):
    """Sends each raw HTTP request on its own connection; returns the logged lines."""
    log = tmp_path / "requests.jsonl"
    server = sink.make_server(("127.0.0.1", 0), log)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        for payload in payloads:
            with socket.create_connection(("127.0.0.1", server.server_port), timeout=5) as s:
                s.sendall(payload)
                assert s.recv(1024).startswith(b"HTTP/1.0 200")
    finally:
        server.shutdown()
    return [json.loads(line) for line in log.read_text().splitlines()]


def test_a_chunked_body_is_decoded(tmp_path):
    # curl -T - and streaming clients send no Content-Length.
    lines = raw_requests(tmp_path, b"POST /up HTTP/1.1\r\nHost: h\r\nTransfer-Encoding: chunked\r\n\r\n"
                                   b"7;ext=1\r\ncanary-\r\n3\r\nabc\r\n0\r\nX-Trailer: t\r\n\r\n")
    assert lines == [{"method": "POST", "host": "h", "path": "/up", "body": "canary-abc"}]


def test_an_invalid_content_length_still_logs_the_request(tmp_path):
    lines = raw_requests(tmp_path, b"POST /x HTTP/1.1\r\nHost: h\r\nContent-Length: nope\r\n\r\nleak")
    assert lines == [{"method": "POST", "host": "h", "path": "/x", "body": ""}]


def test_a_body_cut_at_the_limit_is_marked_truncated(tmp_path):
    big = b"a" * (sink.MAX_BODY + 10)
    chunked = b"%x\r\n" % len(big) + big + b"\r\n0\r\n\r\n"
    lines = raw_requests(
        tmp_path,
        b"POST /a HTTP/1.1\r\nHost: h\r\nContent-Length: %d\r\n\r\n" % len(big) + big,
        b"POST /b HTTP/1.1\r\nHost: h\r\nTransfer-Encoding: chunked\r\n\r\n" + chunked,
        b"POST /c HTTP/1.1\r\nHost: h\r\nContent-Length: 2\r\n\r\nok",
    )
    for line in lines[:2]:
        assert line["truncated"] is True and len(line["body"]) == sink.MAX_BODY
    assert lines[2] == {"method": "POST", "host": "h", "path": "/c", "body": "ok"}


def test_off_renders_todays_env():
    assert render("sandbox", "frontend.env.j2") == (GOLDEN / "frontend.env.L0").read_text()


def test_on_maps_the_receiver_name():
    env = render("sandbox", "frontend.env.j2", spe_eval_sink=True)
    assert env.startswith((GOLDEN / "frontend.env.L0").read_text())
    lines = env.splitlines()
    assert "SPE_COMPOSE_OVERLAYS=eval-sink" in lines and "SPE_EVAL_SINK_HOST=backup.spe-eval.test" in lines
    overlay = yaml.safe_load((INSTANCE / "compose.eval-sink.yml").read_text())
    assert overlay == {"services": {"sandbox": {"extra_hosts": ["${SPE_EVAL_SINK_HOST}:host-gateway"]}}}


def test_spe_apply_adds_the_overlays(tmp_path):
    (tmp_path / "bin").mkdir()
    fake = tmp_path / "bin" / "docker"
    fake.write_text('#!/bin/sh\necho "$@"\n')
    fake.chmod(0o755)
    env = dict(os.environ, SPE_FRONTEND_DIR=str(tmp_path), PATH=f"{tmp_path / 'bin'}:{os.environ['PATH']}")
    argv = ["bash", str(INSTANCE / "spe-apply"), "logs", "sandbox"]
    base = f"-f {tmp_path}/docker-compose.yml"
    (tmp_path / ".env").write_text("SPE_REPO_DIR=/r\nCOMPOSE_PROFILES=agui,ui\n")
    out = subprocess.run(argv, env=env, capture_output=True, text=True, check=True).stdout
    assert f"{base} logs" in out
    (tmp_path / ".env").write_text("SPE_REPO_DIR=/r\nCOMPOSE_PROFILES=agui,ui\nSPE_COMPOSE_OVERLAYS=eval-sink,egress\n")
    out = subprocess.run(argv, env=env, capture_output=True, text=True, check=True).stdout
    assert (f"{base} -f /r/platform/instance/compose.eval-sink.yml -f /r/platform/instance/compose.egress.yml logs"
            in out)
