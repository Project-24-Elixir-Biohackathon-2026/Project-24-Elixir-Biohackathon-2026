"""`evals-view` (decisions 14-15, docs/specs/2026-11-10-experiments-design/04-viewer.md): a
read-only `promptfoo view` on `spe_experiments` builds, behind an nginx allow-list proxy.

(a) Static checks against platform/instance/compose.yml: both services only run under profile
`evals`, the port is 127.0.0.1-only, the `evals` network is joined by no other service,
`evals-promptfoo` shares `evals-view`'s network namespace instead, neither service carries an
`env_file` or a key-looking environment variable, the three DISABLE vars are set, and neither
service nor a volume of its own is restored by the isolation reset (platform/promptfoo-evals/
isolation.py: it is a bind mount, nothing to snapshot).

(b) The proxy itself (evals-view/nginx.conf), against every route promptfoo 0.125.1's server
registers: skipped when `docker` is unavailable. ROUTE_PATTERNS below is that route list, with
the comment underneath saying how it was extracted; GET_ROUTES must answer 200 through the
proxy, every other (method, route) 403 -- except socket.io's own transport (decision 15: the
server only emits, it handles no client event, so both its GET -- plain and the websocket
upgrade -- and its long-polling POST are let through). nginx proxies a stub upstream (listening
on 15500, the same port promptfoo binds to, inside one shared network namespace, as
`evals-promptfoo`'s `network_mode: "service:evals-view"` does in compose.yml) that answers 200
to anything and records every byte each connection carried, so what is under test is nginx's
method/path allow-list and what it actually puts on the wire to promptfoo, not promptfoo itself;
the real image was also checked once by hand against actual promptfoo (see the task's own report).
"""
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest
import yaml

from ansible_render import GOLDEN, load_vars, render

PLATFORM = Path(__file__).resolve().parents[2]
INSTANCE = PLATFORM / "instance"
EVALS_VIEW = INSTANCE / "evals-view"
COMPOSE = yaml.safe_load((INSTANCE / "compose.yml").read_text())
PROMPTFOO_INDEX = PLATFORM / "promptfoo-evals" / "node_modules" / "promptfoo" / "dist" / "src" / "server" / "index.js"

# --- (a) static: compose.yml ------------------------------------------------------------------


def test_both_services_only_run_under_the_evals_profile():
    assert COMPOSE["services"]["evals-view"]["profiles"] == ["evals"]
    assert COMPOSE["services"]["evals-promptfoo"]["profiles"] == ["evals"]


def test_only_evals_view_publishes_a_port_and_only_on_localhost():
    ports = COMPOSE["services"]["evals-view"]["ports"]
    assert len(ports) == 1 and ports[0].startswith("127.0.0.1:") and ports[0].endswith(":8080")
    assert "ports" not in COMPOSE["services"]["evals-promptfoo"]


def test_the_evals_network_is_joined_by_evals_view_and_no_other_service():
    for name, svc in COMPOSE["services"].items():
        networks = svc.get("networks") or []
        if name == "evals-view":
            assert networks == ["evals"]
        else:
            assert "evals" not in networks, f"{name} joins the evals network too"


def test_evals_promptfoo_shares_evals_views_network_namespace_instead():
    assert COMPOSE["services"]["evals-promptfoo"]["network_mode"] == "service:evals-view"
    assert "networks" not in COMPOSE["services"]["evals-promptfoo"]


def test_evals_promptfoo_runs_as_uid_1000_whatever_the_image():
    # The data directory's owner (role spe_eval asserts the workspace user is uid 1000).
    assert COMPOSE["services"]["evals-promptfoo"]["user"] == "1000:1000"


def test_neither_service_has_an_env_file_or_a_key_looking_variable():
    for name in ("evals-view", "evals-promptfoo"):
        svc = COMPOSE["services"][name]
        assert "env_file" not in svc
        for key in svc.get("environment") or {}:
            assert not key.endswith("_KEY"), f"{name}.environment.{key} looks like a secret"
            assert "API_KEY" not in key, f"{name}.environment.{key} looks like a secret"


def test_the_three_disable_vars_are_set():
    env = COMPOSE["services"]["evals-promptfoo"]["environment"]
    assert env["PROMPTFOO_DISABLE_SHARING"] == "1"
    assert env["PROMPTFOO_DISABLE_TELEMETRY"] == "1"
    assert env["PROMPTFOO_DISABLE_UPDATE"] == "1"


def test_neither_service_nor_a_volume_of_its_own_is_restored_by_isolation():
    # Text, not an import (isolation.py imports its sibling handoff.py by plain `import
    # handoff`, which only resolves on its own sys.path): the names simply must not occur in
    # VOLUMES or CONTAINERS (platform/promptfoo-evals/isolation.py), as
    # test_spe_eval_not_in_containers.py already does for other forbidden strings.
    text = (PLATFORM / "promptfoo-evals" / "isolation.py").read_text()
    assert "evals-view" not in text
    assert "evals-promptfoo" not in text


DOCKER = shutil.which("docker")


def test_compose_loads_without_any_spe_evals_variable(tmp_path):
    # Fix round 1, Critical 1: compose interpolates and parses every service, including one in
    # an inactive profile, so a plain spe build's .env (no SPE_EVALS_* at all -- the golden
    # frontend.env.L0 used here, profiles openwebui,agui,ui) must still parse. It did not before
    # the defaults were added to the evals-view/evals-promptfoo lines in compose.yml (an unset
    # ${SPE_EVALS_DATA_DIR} made the volume spec ":/data", "empty section between colons").
    if DOCKER is None:
        pytest.skip("needs docker")
    golden_env = (Path(__file__).resolve().parent / "golden" / "frontend.env.L0").read_text()
    assert "SPE_EVALS" not in golden_env  # the fixture this test leans on must stay evals-free
    env_vars = dict(line.split("=", 1) for line in golden_env.splitlines()
                     if line and not line.startswith("#"))
    # env_file: entries (webui.env, chat-ui.env, agent.env, terminal.env) resolve relative to
    # --project-directory and must exist for `config` to parse at all; a real build's Ansible
    # writes them next to .env, so empty stand-ins here are enough -- their contents are not
    # what this test is about.
    for name in ("webui.env", "chat-ui.env", "agent.env", "terminal.env"):
        (tmp_path / name).write_text("")
    result = subprocess.run(
        ["docker", "compose", "-f", str(INSTANCE / "compose.yml"), "--project-directory", str(tmp_path),
         "config", "-q"],
        env={**os.environ, **env_vars}, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_compose_loads_with_the_experiments_env_and_the_evals_profile_active(tmp_path):
    # Companion to the test above: a real spe_experiments build's three SPE_EVALS_* values (not
    # the placeholder defaults), profile evals active -- both services must validate completely.
    if DOCKER is None:
        pytest.skip("needs docker")
    golden_env = (GOLDEN / "frontend.env.experiments").read_text()
    env_vars = dict(line.split("=", 1) for line in golden_env.splitlines() if line and not line.startswith("#"))
    for name in ("webui.env", "chat-ui.env", "agent.env", "terminal.env"):
        (tmp_path / name).write_text("")
    env_vars["SPE_EVALS_DATA_DIR"] = str(tmp_path / "evals-data")  # a real path; need not pre-exist for config
    result = subprocess.run(
        ["docker", "compose", "-f", str(INSTANCE / "compose.yml"), "--project-directory", str(tmp_path),
         "config", "-q"],
        env={**os.environ, **env_vars}, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


# --- (a2) task 2: frontend.env.j2 (role sandbox) under spe_experiments -----------------------
# The golden-env style other switches use (test_eval_sink.py, test_harden_egress.py): render the
# real Ansible template offline (ansible_render.py) and compare against a committed fixture, so a
# change here is visible in the diff. frontend.env.L0 (off) must stay byte-identical; a new
# fixture, frontend.env.experiments, covers spe_experiments: true (no existing golden did).


def test_frontend_env_off_renders_todays_env_unchanged():
    assert render("sandbox", "frontend.env.j2") == (GOLDEN / "frontend.env.L0").read_text()


def test_frontend_env_on_experiments_adds_the_evals_profile_and_the_three_vars():
    env = render("sandbox", "frontend.env.j2", spe_experiments=True)
    assert env == (GOLDEN / "frontend.env.experiments").read_text()
    lines = env.splitlines()
    assert "COMPOSE_PROFILES=openwebui,agui,ui,evals" in lines
    assert "SPE_EVALS_PORT=8200" in lines
    assert "SPE_EVALS_VIEW_IMAGE=spe-evals-view:local" in lines
    assert "SPE_EVALS_DATA_DIR=/home/ubuntu/spe-eval/promptfoo" in lines


def test_evals_data_dir_follows_spe_eval_dir_not_a_second_literal():
    # Same derivation spe_eval.py's spe_eval_home() uses (platform/ansible/README.md, "Experiments"):
    # a different spe_ssh_user moves both spe_eval_dir and SPE_EVALS_DATA_DIR together.
    env = render("sandbox", "frontend.env.j2", spe_experiments=True, spe_ssh_user="alice")
    assert "SPE_EVALS_DATA_DIR=/home/alice/spe-eval/promptfoo" in env.splitlines()


def test_without_experiments_no_evals_variable_appears():
    env = render("sandbox", "frontend.env.j2")
    assert "SPE_EVALS" not in env
    assert ",evals" not in env and "evals," not in env


def test_nginx_image_agrees_with_group_vars_spe_prefetch_images():
    # group_vars/all.yml repeats evals-view's nginx tag as a literal in spe_prefetch_images
    # (role prefetch pulls it ahead of the first up), since nothing there reads compose.yml.
    # Nothing else ties the two together, so a bump of one here would silently drift from
    # the other without this check.
    nginx_image = COMPOSE["services"]["evals-view"]["image"]
    assert nginx_image in load_vars(spe_experiments=True)["spe_prefetch_images"]
    assert nginx_image not in load_vars(spe_experiments=False)["spe_prefetch_images"]


# --- (b) the proxy, against promptfoo 0.125.1's own routes -----------------------------------

# Extracted from node_modules/promptfoo/dist/src/server/index.js (promptfoo 0.125.1, a single
# bundled file): every `app.use("<prefix>", <name>Router)` mount gives a prefix, and every
# `<name>.(get|post|put|patch|delete)("<path>", ...)` where <name> is "app" or one of those
# mounted names (not a blanket match: "get"/"post" alone are common non-Express identifiers in
# a bundle this size) is one route, at <prefix><path>. Checked to extract exactly these 68
# entries from the real package (test_the_extractor_agrees_with_the_installed_package below).
ROUTE_PATTERNS = (
    ("DELETE", "/api/eval/"), ("DELETE", "/api/eval/:id"), ("DELETE", "/api/model-audit/scans/:id"),
    ("GET", "/*splat"), ("GET", "/api/blobs/:hash"), ("GET", "/api/blobs/library"),
    ("GET", "/api/blobs/library/evals"), ("GET", "/api/configs/"), ("GET", "/api/configs/:type"),
    ("GET", "/api/configs/:type/:id"), ("GET", "/api/datasets"), ("GET", "/api/eval/:id/metadata-keys"),
    ("GET", "/api/eval/:id/metadata-values"), ("GET", "/api/eval/:id/table"), ("GET", "/api/eval/job/:id"),
    ("GET", "/api/history"), ("GET", "/api/media/:type/:filename"), ("GET", "/api/media/info/:type/:filename"),
    ("GET", "/api/media/stats"), ("GET", "/api/model-audit/check-installed"), ("GET", "/api/model-audit/scanners"),
    ("GET", "/api/model-audit/scans"), ("GET", "/api/model-audit/scans/:id"), ("GET", "/api/model-audit/scans/latest"),
    ("GET", "/api/prompts"), ("GET", "/api/prompts/:sha256hash"), ("GET", "/api/providers/config-status"),
    ("GET", "/api/redteam/status"), ("GET", "/api/remote-health"), ("GET", "/api/results"),
    ("GET", "/api/results/:id"), ("GET", "/api/results/share/check-domain"), ("GET", "/api/traces/:traceId"),
    ("GET", "/api/traces/evaluation/:evaluationId"), ("GET", "/api/user/cloud-config"), ("GET", "/api/user/email"),
    ("GET", "/api/user/email/status"), ("GET", "/api/user/id"), ("GET", "/api/version/"), ("GET", "/health"),
    ("PATCH", "/api/eval/:id"), ("PATCH", "/api/eval/:id/author"), ("POST", "/api/configs/"),
    ("POST", "/api/dataset/generate"), ("POST", "/api/eval/"), ("POST", "/api/eval/:evalId/results/:id/rating"),
    ("POST", "/api/eval/:id/copy"), ("POST", "/api/eval/:id/results"), ("POST", "/api/eval/job"),
    ("POST", "/api/eval/replay"), ("POST", "/api/model-audit/check-path"), ("POST", "/api/model-audit/scan"),
    ("POST", "/api/providers/discover"), ("POST", "/api/providers/http-generator"), ("POST", "/api/providers/test"),
    ("POST", "/api/providers/test-request-transform"), ("POST", "/api/providers/test-response-transform"),
    ("POST", "/api/providers/test-session"), ("POST", "/api/redteam/:taskId"), ("POST", "/api/redteam/cancel"),
    ("POST", "/api/redteam/generate-test"), ("POST", "/api/redteam/run"), ("POST", "/api/results/share"),
    ("POST", "/api/telemetry"), ("POST", "/api/user/email"), ("POST", "/api/user/login"),
    ("POST", "/api/user/logout"), ("PUT", "/api/user/email/clear"),
)

MOUNT_RE = re.compile(r'app\.use\("([^"]+)",\s*(\w+)\)')
# Every Express Router method (fix round 1, Minor 6), not just the five 0.125.1 happens to use:
# `all`, `head` and `options` register a route too (a future version could add one).
ROUTE_RE = re.compile(r'\b(\w+)\.(get|post|put|patch|delete|head|options|all)\(\s*"([^"]+)"')


def extract_routes(text: str) -> set[tuple[str, str]]:
    """The same extraction described in ROUTE_PATTERNS' comment, run over real source text."""
    mounts = {name: prefix for prefix, name in MOUNT_RE.findall(text)}
    mounts["app"] = ""
    routes = set()
    for var, method, path in ROUTE_RE.findall(text):
        if var in mounts:
            routes.add((method.upper(), mounts[var] + path))
    return routes


def test_the_extractor_agrees_with_the_installed_package():
    if not PROMPTFOO_INDEX.is_file():
        pytest.skip("platform/promptfoo-evals/node_modules/promptfoo is not installed here")
    assert extract_routes(PROMPTFOO_INDEX.read_text()) == set(ROUTE_PATTERNS)


def concretize(path: str) -> str:
    """A real path for one of ROUTE_PATTERNS' route patterns: ':param' segments become 'x',
    and the one Express 5 wildcard ('/*splat', the SPA's catch-all) becomes a plain asset path."""
    if path == "/*splat":
        return "/app.js"
    return re.sub(r":[A-Za-z_][A-Za-z0-9_]*", "x", path)


GET_ROUTES = [concretize(path) for method, path in ROUTE_PATTERNS if method == "GET"]
NON_GET_ROUTES = [(method, concretize(path)) for method, path in ROUTE_PATTERNS if method != "GET"]

pytestmark_proxy = pytest.mark.skipif(DOCKER is None, reason="needs docker")
NGINX_IMAGE = "nginx:1.29-alpine"
# The stub upstream: a pinned stock Python image running STUB_SERVER below on 15500, the port
# promptfoo binds to and nginx.conf's upstream names, so nginx.conf needs no change for the test.
# Not an off-the-shelf echo server (traefik/whoami was): those parse and answer only the first
# request on a connection, so a second request smuggled behind it (fix round 2, Critical 1)
# would never show. This one answers 200 once, echoing the first request's head as its body,
# then keeps reading until nginx closes, and logs the whole connection's bytes as one JSON line.
STUB_IMAGE = "python:3.13-alpine"
STUB_SERVER = r"""
import json, socket, threading
def serve(conn):
    conn.settimeout(2)
    data = b""
    try:
        while b"\r\n\r\n" not in data:
            chunk = conn.recv(65536)
            if not chunk:
                break
            data += chunk
        head = data.split(b"\r\n\r\n", 1)[0]
        body = b"" if head.startswith(b"HEAD ") else head
        conn.sendall(b"HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Type: text/plain\r\n"
                     b"Content-Length: %d\r\n\r\n" % len(head) + body)
        while chunk := conn.recv(65536):
            data += chunk
    except OSError:
        pass
    finally:
        conn.close()
        print(json.dumps(data.decode("latin-1")), flush=True)
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", 15500))
s.listen(64)
while True:
    threading.Thread(target=serve, args=(s.accept()[0],), daemon=True).start()
"""


def _run(*args):
    subprocess.run(["docker", *args], check=True, capture_output=True, text=True)


@pytest.fixture(scope="module")
def proxy():
    if DOCKER is None:
        pytest.skip("needs docker")
    tag = uuid.uuid4().hex[:8]
    nginx_name = f"evals-view-test-nginx-{tag}"
    stub_name = f"evals-view-test-stub-{tag}"
    try:
        _run("run", "-d", "--name", nginx_name,
             "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--read-only",
             "--user", "101:101", "--tmpfs", "/tmp",
             "-p", "127.0.0.1::8080",
             "-v", f"{EVALS_VIEW / 'nginx.conf'}:/etc/nginx/nginx.conf:ro",
             NGINX_IMAGE)
        _run("run", "-d", "--name", stub_name, "--network", f"container:{nginx_name}",
             "--cap-drop", "ALL", "--read-only", "--user", "65534:65534",
             STUB_IMAGE, "python", "-c", STUB_SERVER)
        port = subprocess.run(["docker", "port", nginx_name, "8080/tcp"], check=True,
                               capture_output=True, text=True).stdout.strip().rsplit(":", 1)[1]
        base = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 15
        while True:
            try:
                urllib.request.urlopen(base + "/", timeout=2)
                break
            except (urllib.error.URLError, ConnectionError):
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.5)
        yield base, stub_name
    finally:
        subprocess.run(["docker", "rm", "-f", nginx_name, stub_name], capture_output=True, text=True)


def request(proxy, method: str, path: str, headers: dict | None = None) -> tuple[int, str]:
    req = urllib.request.Request(proxy[0] + path, method=method, headers=headers or {})
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def status(proxy, method: str, path: str) -> int:
    return request(proxy, method, path)[0]


def upstream_path(body: str) -> str | None:
    """The stub echoes the head of the request it actually received as its body, request line
    first: the path nginx forwarded, however the client phrased the one it sent (fix round 1,
    Important 2 -- the whole point of these bypass tests is to see this, not just the status,
    since the always-200 stub alone cannot show a mismatch)."""
    for line in body.splitlines():
        parts = line.split(" ")
        if len(parts) >= 2 and parts[0] in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"):
            return parts[1]
    return None


REQUEST_LINE_RE = re.compile(r"^(GET|HEAD|POST|PUT|PATCH|DELETE|OPTIONS|CONNECT|TRACE) ", re.M)


def upstream_connections(proxy, marker: str) -> list[str]:
    """Every connection the stub logged whose bytes contain `marker`, waiting briefly for it:
    the stub logs a connection only once nginx has closed it."""
    deadline = time.monotonic() + 5
    while True:
        logs = subprocess.run(["docker", "logs", proxy[1]], check=True, capture_output=True,
                              text=True).stdout
        found = [raw for raw in map(json.loads, logs.splitlines()) if marker in raw]
        if found or time.monotonic() > deadline:
            return found
        time.sleep(0.2)


@pytestmark_proxy
@pytest.mark.parametrize("path", GET_ROUTES)
def test_get_routes_answer_200(proxy, path):
    assert status(proxy, "GET", path) == 200


@pytestmark_proxy
@pytest.mark.parametrize("method,path", NON_GET_ROUTES)
def test_non_get_routes_are_refused(proxy, method, path):
    assert status(proxy, method, path) == 403


@pytestmark_proxy
def test_head_is_let_through(proxy):
    assert status(proxy, "HEAD", "/") == 200


@pytestmark_proxy
def test_socket_io_polling_get_handshake_is_let_through(proxy):
    code, body = request(proxy, "GET", "/socket.io/?EIO=4&transport=polling")
    assert code == 200 and upstream_path(body) == "/socket.io/?EIO=4&transport=polling"


@pytestmark_proxy
def test_socket_io_polling_post_is_let_through(proxy):
    code, body = request(proxy, "POST", "/socket.io/?EIO=4&transport=polling")
    assert code == 200 and upstream_path(body) == "/socket.io/?EIO=4&transport=polling"


@pytestmark_proxy
def test_socket_io_websocket_upgrade_get_is_let_through(proxy):
    code, body = request(proxy, "GET", "/socket.io/?EIO=4&transport=websocket",
                          headers={"Connection": "Upgrade", "Upgrade": "websocket"})
    assert code == 200 and upstream_path(body) == "/socket.io/?EIO=4&transport=websocket"
    assert "Connection: upgrade" in body


@pytestmark_proxy
def test_socket_io_still_refuses_every_other_method(proxy):
    assert status(proxy, "DELETE", "/socket.io/") == 403


# Fix round 1, Important 2: nginx picks a location (and so which methods it allows) from the
# decoded, dot-segment-resolved URI, but forwards the client's raw, undecoded one -- so a request
# that *normalizes* into /socket.io/ (where POST is allowed) could, forwarded raw, dispatch to
# one of promptfoo's own param routes instead (e.g. redteamRouter's "/:taskId", whose param
# swallows a traversal). nginx.conf's `/socket.io/` location therefore also requires the raw
# request URI to be exactly /socket.io/ plus a query; every case below must be refused.
BYPASS_CASES = [
    ("POST", "/api/redteam/..%2F..%2Fsocket.io%2F", None),
    ("POST", "/socket.io/../api/eval/job", None),
    ("POST", "//socket.io/", None),
    ("POST", "/socket.io/%2E%2E/api/eval/job", None),
    ("POST", "/api/eval/job", {"X-HTTP-Method-Override": "GET"}),
    ("POST", "/api/eval/x/results/..%2F..%2F..%2F..%2Fsocket.io/rating", None),
]


@pytestmark_proxy
@pytest.mark.parametrize("method,path,headers", BYPASS_CASES,
                          ids=["redteam-encoded-traversal", "socket-io-dotdot", "double-slash",
                               "socket-io-encoded-dotdot", "method-override-header",
                               "rating-encoded-traversal"])
def test_encoded_path_bypasses_are_refused(proxy, method, path, headers):
    code, body = request(proxy, method, path, headers)
    assert code == 403, f"reached upstream as {upstream_path(body)!r}"


# Fix round 2, Critical 1: forwarding nginx's *decoded* path (`proxy_pass http://promptfoo$uri`)
# put %0D%0A and %20 into the upstream request line as real CR/LF and spaces, so one client
# request became two upstream requests -- a GET carrying a smuggled POST /api/eval/job, past the
# allow-list. Each case must either be refused, or reach promptfoo as exactly one request whose
# path is the client's own raw (still encoded) path, byte for byte. The %MARKER% placeholder makes
# each case's upstream connection findable in the stub's log.
SMUGGLE_CRLF = "%20HTTP/1.1%0D%0AHost:%20x%0D%0A%0D%0APOST%20/api/eval/job-%MARKER%"
SMUGGLING_CASES = [
    ("GET", "/a" + SMUGGLE_CRLF),
    ("GET", "/api/results" + SMUGGLE_CRLF + "%20HTTP/1.1%0D%0AContent-Length:%2020%0D%0A%0D%0A"),
    ("POST", "/socket.io/" + SMUGGLE_CRLF),
    ("GET", "/socket.io/" + SMUGGLE_CRLF),
    ("GET", "/a%0Ab-%MARKER%"),
    ("GET", "/a%20b-%MARKER%"),
    ("GET", "/a%20/api/eval/job-%MARKER%"),
]


@pytestmark_proxy
@pytest.mark.parametrize("method,path", SMUGGLING_CASES,
                          ids=["get-crlf", "get-crlf-content-length", "socket-io-post-crlf",
                               "socket-io-get-crlf", "get-lf", "get-space", "get-space-path"])
def test_no_request_is_smuggled_into_the_upstream_connection(proxy, method, path):
    marker = uuid.uuid4().hex
    path = path.replace("%MARKER%", marker)
    code, _ = request(proxy, method, path)
    connections = upstream_connections(proxy, marker)
    if code == 403:
        assert connections == []
        return
    assert len(connections) == 1
    request_lines = [line for line in connections[0].split("\r\n") if REQUEST_LINE_RE.match(line)]
    assert len(request_lines) == 1, request_lines
    assert re.fullmatch(re.escape(f"{method} {path}") + r" HTTP/1\.[01]", request_lines[0])
