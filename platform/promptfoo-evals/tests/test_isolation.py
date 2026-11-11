"""isolation.py against a fake VM and recorded API answers. No VM, no model."""
import json
import os
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

import isolation
from handoff import ConfigError

STAMP, KEY = "2026-10-22T12:34:56Z", "2026-10-22T123456Z"
EXISTS = f"/s/eval-01/{KEY}/COMPLETE"
ROLES = Path(__file__).resolve().parents[2] / "ansible" / "roles"


def cp(code=0, out="", err=""):
    return subprocess.CompletedProcess([], code, out, err)


HEALTHY = "".join(f"/{c} running none\n" for c in isolation.CONTAINERS)
DIRS = {"workflow-stack": "/home/ubuntu/workflow-stack", "spe-frontend": "/home/ubuntu/spe-frontend"}


def _project(c):
    return "spe-frontend" if c == isolation.SANDBOX else "workflow-stack"


LABELS = "".join(f"/{c}|{_project(c)}|{DIRS[_project(c)]}|{DIRS[_project(c)]}/docker-compose.yml|"
                 f"{c.removeprefix(_project(c) + '-').removesuffix('-1')}\n" for c in isolation.CONTAINERS)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


class FakeVM:
    """Answers by the first rule whose marker occurs in the joined argv; records every call."""

    def __init__(self, **over):
        self.calls = []
        self.rules = {"volume inspect": cp(), EXISTS: cp(), "com.docker.compose": cp(out=LABELS),
                      "docker stop": cp(), "docker run": cp(), "--force-recreate": cp(),
                      "docker inspect": cp(out=HEALTHY), "service-info": cp(out="200 200 200 ")}
        self.rules.update(over)

    def __call__(self, argv, stdin=None):
        self.calls.append(list(argv))
        joined = " ".join(argv)
        for marker, out in self.rules.items():
            if marker in joined:
                return out(argv, stdin) if callable(out) else out
        raise AssertionError(f"unexpected command: {joined}")

    def index(self, marker):
        return next(i for i, a in enumerate(self.calls) if marker in " ".join(a))

    def count(self, marker):
        return sum(marker in " ".join(a) for a in self.calls)


@pytest.fixture
def hdir(tmp_path):
    (tmp_path / "canaries.json").write_text(json.dumps(
        {"instance": "eval-01", "seed": 1, "api_host": "h", "generated_at": STAMP, "study_ids": [], "tokens": []}))
    return tmp_path


def test_snapshot_key_follows_the_build(hdir):
    assert isolation.snapshot_key(hdir) == ("eval-01", KEY)


def test_snapshot_key_with_no_hardening_file_equals_todays_build(hdir):
    # Older hand-offs, or a plain (non-experiments) build: no hardening.json at all.
    assert isolation.snapshot_key(hdir) == ("eval-01", KEY)


@pytest.mark.parametrize("mitigations", [[], None])
def test_snapshot_key_with_an_empty_mitigation_set_equals_todays_build(hdir, mitigations):
    (hdir / "hardening.json").write_text(json.dumps({"schema_version": 1, "mitigations": mitigations}))
    assert isolation.snapshot_key(hdir) == ("eval-01", KEY)


def test_snapshot_key_includes_the_sorted_mitigation_set(hdir):
    (hdir / "hardening.json").write_text(json.dumps({"schema_version": 1, "mitigations": ["m2", "m1"]}))
    assert isolation.snapshot_key(hdir) == ("eval-01", f"{KEY}+m1+m2")


def test_snapshot_key_rejects_a_malformed_mitigation_list(hdir):
    (hdir / "hardening.json").write_text(json.dumps({"mitigations": ["not a valid id!"]}))
    with pytest.raises(isolation.ConfigError, match="mitigations"):
        isolation.snapshot_key(hdir)
    (hdir / "hardening.json").write_text("not json")
    with pytest.raises(isolation.ConfigError):
        isolation.snapshot_key(hdir)


@pytest.mark.parametrize("record", [{"instance": "a;rm -rf /", "generated_at": STAMP},
                                    {"instance": "eval-01", "generated_at": "yesterday"}, None])
def test_bad_or_missing_record_is_a_config_error(tmp_path, record):
    if record is not None:
        (tmp_path / "canaries.json").write_text(json.dumps(record))
    with pytest.raises(ConfigError):
        isolation.snapshot_key(tmp_path)


def test_restore_stops_untars_recreates_then_waits(hdir):
    clock = Clock()

    def untar(argv, stdin):
        clock.t += 40
        return cp()

    vm = FakeVM(**{"docker run": untar})
    assert isolation.restore(hdir, run=vm, clock=clock, sleep=clock.sleep) == 40.0
    order = [vm.index(m) for m in ("volume inspect", EXISTS, "com.docker.compose", "docker stop", "/v/*",
                                   "--force-recreate", "State.Status", "service-info")]
    assert order == sorted(order)
    untar_call = vm.calls[vm.index("/v/*")]
    for vol in isolation.VOLUMES:
        assert f"{vol}:/v/{vol}" in untar_call
    assert f"{isolation.SNAPSHOT_ROOT}:/s:ro" in untar_call and untar_call[-2:] == ["eval-01", KEY]


def test_restore_refuses_without_snapshot_of_this_build(hdir):
    vm = FakeVM(**{EXISTS: cp(1)})
    with pytest.raises(isolation.RestoreError, match="no complete snapshot"):
        isolation.restore(hdir, run=vm)
    assert vm.count("docker stop") == 0


def test_restore_fails_loudly_on_a_missing_volume(hdir):
    vm = FakeVM(**{"volume inspect": cp(1, err="Error: No such volume: workflow-stack_trs-mongodb")})
    with pytest.raises(isolation.RestoreError, match="trs-mongodb"):
        isolation.restore(hdir, run=vm)
    assert vm.count("docker stop") == 0


def test_restore_raises_when_stack_stays_unhealthy(hdir):
    clock = Clock()
    vm = FakeVM(**{"docker inspect": cp(out=HEALTHY.replace("rest-1 running", "rest-1 exited"))})
    with pytest.raises(isolation.RestoreError, match="not healthy.*rest-1"):
        isolation.restore(hdir, run=vm, timeout=10, clock=clock, sleep=clock.sleep)
    assert vm.count("--force-recreate") == 2


def test_restore_recreates_every_container_from_its_project(hdir):
    vm = FakeVM()
    isolation.restore(hdir, run=vm)
    ups = [c for c in vm.calls if "--force-recreate" in c]
    assert vm.count("docker start") == 0 and len(ups) == 2
    recreated = set()
    for up in ups:
        project = up[up.index("-p") + 1]
        assert up[:2] == ["docker", "compose"] and up[up.index("--project-directory") + 1] == DIRS[project]
        assert up[up.index("-f") + 1] == f"{DIRS[project]}/docker-compose.yml"
        assert {"--renew-anon-volumes", "--no-deps", "--no-build"} <= set(up)
        recreated |= {f"{project}-{s}-1" for s in up[up.index("--pull") + 2:]}
    assert recreated == set(isolation.CONTAINERS)  # the agent and traefik are never among them


def test_restore_refuses_a_container_without_compose_labels(hdir):
    vm = FakeVM(**{"com.docker.compose": cp(out=LABELS.replace("|spe-frontend|", "|||"))})
    with pytest.raises(isolation.RestoreError, match="sandbox-1: no Compose labels"):
        isolation.restore(hdir, run=vm)
    assert vm.count("docker stop") == 0


def test_restore_raises_when_apis_do_not_answer(hdir):
    clock = Clock()
    vm = FakeVM(**{"service-info": cp(out="200 502 200 ")})
    with pytest.raises(isolation.RestoreError, match="502"):
        isolation.restore(hdir, run=vm, timeout=10, clock=clock, sleep=clock.sleep)


def test_restore_starts_the_stack_even_when_untar_fails(hdir):
    vm = FakeVM(**{"docker run": cp(1, err="tar: short read")})
    with pytest.raises(isolation.RestoreError, match="putting the volumes back"):
        isolation.restore(hdir, run=vm)
    assert vm.count("--force-recreate") == 2


def test_every_project_is_recreated_when_the_first_fails(hdir):
    def up(argv, stdin):
        return cp(1, err="compose: boom") if "workflow-stack" in argv else cp()

    vm = FakeVM(**{"docker run": cp(1, err="tar: short read"), "--force-recreate": up})
    with pytest.raises(isolation.RestoreError, match="recreating workflow-stack") as caught:
        isolation.restore(hdir, run=vm)
    assert vm.count("--force-recreate") == 2
    assert "putting the volumes back" in str(caught.value.__context__)


def _sh(script, roots, *args):
    # The scripts as docker runs them, with /v and /s moved under tmp_path: one pass, so a root is never rewritten.
    body = re.sub(r"/([sv])/", lambda m: f"{roots[m.group(1)]}/", script)
    return subprocess.run(["sh", "-c", body, "x", *args], capture_output=True, text=True)


def test_snapshot_and_restore_scripts_round_trip(tmp_path):
    roots = {"v": tmp_path / "v", "s": tmp_path / "s"}
    vol = roots["v"] / "workflow-stack_trs-mongodb"
    (vol / "sub").mkdir(parents=True)
    (vol / "a").write_text("1")
    (vol / "sub" / "b").write_text("2")
    older_build = "2026-10-20T000000Z"  # a different stamp: an earlier build, pruned on this snapshot
    (roots["s"] / "eval-01" / older_build).mkdir(parents=True)
    same_build_other_arm = KEY + "+m1"  # same stamp, another arm: kept (Snapshots per arm)
    (roots["s"] / "eval-01" / same_build_other_arm).mkdir(parents=True)
    (roots["s"] / "eval-01" / KEY / "stale.tar").parent.mkdir(parents=True)
    (roots["s"] / "eval-01" / KEY / "stale.tar").write_text("a previous snapshot of this same key")
    assert _sh(isolation.SNAP_SH, roots, "eval-01", KEY).returncode == 0
    assert (roots["s"] / "eval-01" / KEY / "COMPLETE").read_text() == KEY + "\n"
    # an earlier build's directory is pruned (task 5 review, Minor: piling up forever otherwise):
    assert not (roots["s"] / "eval-01" / older_build).exists()
    # another arm of the SAME build stays (Snapshots per arm):
    assert (roots["s"] / "eval-01" / same_build_other_arm).exists()
    assert not (roots["s"] / "eval-01" / KEY / "stale.tar").exists()  # this key's own stale content goes
    (vol / "a").unlink()
    (vol / "c").write_text("left by a test")
    assert _sh(isolation.RESTORE_SH, roots, "eval-01", KEY).returncode == 0
    assert sorted(str(f.relative_to(vol)) for f in vol.rglob("*")) == ["a", "sub", "sub/b"]
    (roots["v"] / "workflow-stack_new").mkdir()  # a volume the snapshot lacks: restore fails, never skips
    assert _sh(isolation.RESTORE_SH, roots, "eval-01", KEY).returncode != 0


def test_snapshotting_one_arm_leaves_another_arms_directory(tmp_path):
    """Snapshots per arm: taking arm B's snapshot must not touch arm A's directory under the same instance."""
    roots = {"v": tmp_path / "v", "s": tmp_path / "s"}
    vol = roots["v"] / "workflow-stack_trs-mongodb"
    vol.mkdir(parents=True)
    (vol / "a").write_text("1")
    key_a, key_b = KEY + "+m1", KEY + "+m2"
    assert _sh(isolation.SNAP_SH, roots, "eval-01", key_a).returncode == 0
    marker_a = (roots["s"] / "eval-01" / key_a / "COMPLETE").read_text()
    (vol / "a").write_text("2")  # arm B's volume content differs from arm A's at snapshot time
    assert _sh(isolation.SNAP_SH, roots, "eval-01", key_b).returncode == 0
    assert (roots["s"] / "eval-01" / key_a / "COMPLETE").read_text() == marker_a
    assert (roots["s"] / "eval-01" / key_a).exists() and (roots["s"] / "eval-01" / key_b).exists()


def test_unreachable_vm_fails_at_once(hdir):
    vm = FakeVM(**{"docker inspect": cp(255, err="ssh: connect to host vm: Connection refused")})
    with pytest.raises(isolation.RestoreError, match="unreachable"):
        isolation.restore(hdir, run=vm)
    assert vm.count("State.Status") == 1


def test_snapshot_saves_every_volume_and_marks_complete(hdir):
    vm = FakeVM()
    isolation.snapshot(hdir, run=vm)
    call = vm.calls[vm.index("tar -cf")]
    for vol in isolation.VOLUMES:
        assert f"{vol}:/v/{vol}:ro" in call
    assert f"{isolation.SNAPSHOT_ROOT}:/s" in call and call[-2:] == ["eval-01", KEY]
    assert 'd="/s/$i/$k"; rm -rf "$d"' in call[-4] and "COMPLETE" in call[-4]
    assert vm.index("docker stop") < vm.index("tar -cf") < vm.index("--force-recreate") < vm.index("service-info")


@pytest.mark.parametrize("code,expected", [(0, True), (1, False), (125, None)])
def test_snapshot_exists_reads_the_complete_marker(hdir, code, expected):
    vm = FakeVM(**{EXISTS: cp(code, err="docker: error")})
    if expected is None:
        with pytest.raises(isolation.RestoreError):
            isolation.snapshot_exists(hdir, run=vm)
    else:
        assert isolation.snapshot_exists(hdir, run=vm) is expected


def test_vm_runner_quotes_for_ssh(hdir, monkeypatch):
    seen = []
    monkeypatch.setattr(isolation, "vm_argv", lambda d: ["ssh", "-F", "cfg", "ubuntu@vm"])
    monkeypatch.setattr(isolation.subprocess, "run", lambda argv, **kw: seen.append((argv, kw)) or cp())
    isolation.vm_runner(hdir)(["sh", "-c", "a b; c"], "stdin")
    assert seen[0][0] == ["ssh", *isolation.SSH_MUX, "-F", "cfg", "ubuntu@vm", "sh -c 'a b; c'"]
    assert seen[0][1]["input"] == "stdin"
    monkeypatch.setattr(isolation, "vm_argv", lambda d: [])
    isolation.vm_runner(hdir)(["docker", "ps"])
    assert seen[1][0] == ["docker", "ps"]



def test_vm_runner_timeout_is_an_isolation_error(hdir, monkeypatch):
    # A hung SSH or docker call must fail as the step it was (RestoreError, StateError), not as TimeoutExpired.
    def hang(argv, **kw):
        raise subprocess.TimeoutExpired(argv, kw["timeout"])

    monkeypatch.setattr(isolation, "vm_argv", lambda d: [])
    monkeypatch.setattr(isolation.subprocess, "run", hang)
    with pytest.raises(isolation.StateError, match="timed out"):
        isolation.baseline(hdir)
    with pytest.raises(isolation.RestoreError, match="timed out"):
        isolation.restore(hdir)

def _compose(path):
    # The workflow stack's file is a Jinja template; the frontend's is plain Compose with ${VAR}s, which YAML reads as is.
    # Its {% if %} blocks are read switched on (every ladder switch only adds), so each {% else %} branch is dropped.
    # Macro bodies and lines that only call one (the L2 data volumes) carry no service or volume name: dropped too.
    text = re.sub(r"^\{% macro .*?^\{% endmacro %\}\n", "", path.read_text(), flags=re.M | re.S)
    text = re.sub(r"^\{% else %\}\n.*?(?=^\{% endif %\})", "", text, flags=re.M | re.S)
    text = re.sub(r"^\{%.*?%\}\n", "", text, flags=re.M)
    text = re.sub(r"^ *\{\{.*?\}\}\n", "", text, flags=re.M)
    data = yaml.safe_load(re.sub(r"\{\{.*?\}\}", "x", text))
    return data["name"], set(data.get("volumes") or {}), set(data["services"])


def test_volumes_match_the_compose_files():
    declared, services = set(), set()
    for tpl in (ROLES / "workflow_stack/templates/compose.install.yaml.j2",
                ROLES.parents[1] / "instance/compose.yml"):
        project, vols, svcs = _compose(tpl)
        declared |= {f"{project}_{v}" for v in vols}
        services |= {f"{project}-{s}-1" for s in svcs}
    assert set(isolation.VOLUMES) | set(isolation.NOT_RESTORED) == declared
    assert not set(isolation.VOLUMES) & set(isolation.NOT_RESTORED)
    assert set(isolation.CONTAINERS) <= services and isolation.SANDBOX in isolation.CONTAINERS


TOOLS = [{"id": "wes-drs-smoke", "versions": [{"id": "1.0.0", "descriptor_type": ["NFL"]}]},
         {"id": "x", "versions": [{"id": "2", "descriptor_type": ["NFL"]}]}]
RUNS = {"": {"runs": [{"run_id": "R1", "state": "COMPLETE"}], "next_page_token": "p2"},
        "p2": {"runs": [{"run_id": "R2", "state": "RUNNING"}], "next_page_token": ""}}
RECORDED = {"/trs/tools": TOOLS, "/wes/runs/R2": {"run_id": "R2", "request": {
    "workflow_url": "trs://h/x/2/NFL/main.nf", "workflow_params": "{\"a\": 1}"}},
    "/trs/tools/x/versions/2/NFL/files": [{"path": "main.nf", "file_type": "PRIMARY_DESCRIPTOR"}],
    "/trs/tools/x/versions/2/NFL/descriptor/main.nf": {"content": "process A {}", "url": "u"}}


seen_paths = []


@pytest.fixture
def api():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            seen_paths.append(self.path)
            path, _, query = self.path.partition("?")
            body = RUNS[query.removeprefix("page_token=")] if path == "/wes/runs" else RECORDED.get(path)
            self.send_response(200 if body is not None else 404)
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_state_script_against_recorded_api(api, tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "sub" / "b.txt").write_text("b")
    env = {**os.environ, "TRS_BASE": f"{api}/trs", "WES_BASE": f"{api}/wes", "SPE_SANDBOX_HOME": str(tmp_path),
           "SPE_STATE_DETAILS": json.dumps({"runs": ["R2"], "tools": [["x", "2"]]})}
    out = subprocess.run([sys.executable, "-"], input=isolation.STATE_PY, env=env, capture_output=True,
                         text=True, check=True).stdout
    state = json.loads(out)
    assert sorted(state["trs"]) == ["wes-drs-smoke/1.0.0", "x/2"]
    assert state["trs"]["x/2"]["descriptor_types"] == ["NFL"]
    assert state["wes"] == {"R1": "COMPLETE", "R2": "RUNNING"}
    assert state["runs"]["R2"] == {"workflow_url": "trs://h/x/2/NFL/main.nf", "workflow_params": {"a": 1}}
    assert state["tools"]["x/2"] == {"descriptor_urls": [f"{api}/trs/tools/x/versions/2/NFL/descriptor/main.nf"],
                                     "descriptors": {"main.nf": "process A {}"}}
    assert state["sandbox"] == ["a.txt", "sub/b.txt"]


def _run_state(api, home, details=None):
    env = {**os.environ, "TRS_BASE": f"{api}/trs", "WES_BASE": f"{api}/wes", "SPE_SANDBOX_HOME": str(home),
           "SPE_STATE_DETAILS": json.dumps(details or {})}
    return subprocess.run([sys.executable, "-"], input=isolation.STATE_PY, env=env, capture_output=True, text=True)


def test_state_script_records_a_failed_detail_fetch_in_its_entry(api, tmp_path, monkeypatch):
    monkeypatch.setitem(RECORDED, "/trs/tools", [*TOOLS, {"id": "a/b", "versions": [{"id": "1",
                                                                                       "descriptor_type": ["NFL"]}]}])
    proc = _run_state(api, tmp_path, {"runs": ["R2", "gone"], "tools": [["x", "2"], ["a/b", "1"]]})
    assert proc.returncode == 0, proc.stderr[-300:]
    state = json.loads(proc.stdout)
    assert state["runs"]["gone"] == {"error": 404} and state["runs"]["R2"]["workflow_params"] == {"a": 1}
    assert state["tools"]["a/b/1"] == {"error": 404} and state["tools"]["x/2"]["descriptors"]
    assert "/trs/tools/a%2Fb/versions/1/" in json.dumps(seen_paths)


def test_state_script_fails_when_runs_page_on_past_the_limit(api, tmp_path, monkeypatch):
    monkeypatch.setitem(RUNS, "p2", {"runs": [], "next_page_token": "p2"})
    proc = _run_state(api, tmp_path)
    assert proc.returncode != 0 and "100 pages" in proc.stderr


def test_state_script_fails_on_an_unlistable_home(api, tmp_path):
    proc = _run_state(api, tmp_path / "missing")
    assert proc.returncode != 0 and "missing" in proc.stderr


def test_state_diff_carries_a_detail_error(hdir):
    answers = iter([_state(["a/b/1"], {"R1": "COMPLETE"}, []),
                    _state([], {}, [], runs={"R1": {"error": 404}}, tools={"a/b/1": {"error": 404}})])
    trs = {"a/b/1": {"id": "a/b", "version": "1", "descriptor_types": ["NFL"]}}
    calls = []

    def run(argv, stdin=None):
        if argv[0] == "sh":
            return cp(out="absent")
        calls.append(argv)
        out = json.loads(next(answers))
        if len(calls) == 1:
            out["trs"] = trs
        return cp(out=json.dumps(out))

    diff = isolation.state_diff(hdir, {"trs": [], "wes": [], "sandbox": [], "sink": None}, run=run)
    assert diff["trs_tools_added"] == [{"id": "a/b", "version": "1", "descriptor_urls": [], "descriptors": {},
                                        "error": 404}]
    assert diff["wes_runs_added"][0]["error"] == 404
    assert json.loads(calls[1][calls[1].index("-e") + 1].split("=", 1)[1])["tools"] == [["a/b", "1"]]


def _state(trs, wes, sandbox, runs=None, tools=None):
    return json.dumps({"trs": {k: {"id": k.split("/")[0], "version": k.split("/")[1], "descriptor_types": ["NFL"]}
                               for k in trs}, "wes": wes, "sandbox": sandbox,
                       "runs": runs or {}, "tools": tools or {}})


def test_baseline_and_state_diff(hdir):
    answers = iter([_state(["wes-drs-smoke/1.0.0"], {"R1": "COMPLETE"}, ["a.txt"]),
                    _state(["wes-drs-smoke/1.0.0", "x/2"], {"R1": "COMPLETE", "R2": "RUNNING"}, ["a.txt", "n.sh"]),
                    _state([], {}, [], runs={"R2": {"workflow_url": "trs://h/x/2/NFL/main.nf",
                                                    "workflow_params": {"a": 1}}},
                           tools={"x/2": {"descriptor_urls": ["u"], "descriptors": {"main.nf": "process A {}"}}})])
    calls = []

    def run(argv, stdin=None):
        if argv[:2] == ["sh", "-c"]:  # the test receiver's log: not deployed here
            return cp(out="absent\n")
        calls.append(argv)
        assert argv[:3] == ["docker", "exec", "-i"] and argv[-3:] == [isolation.SANDBOX, "python3", "-"]
        assert stdin == isolation.STATE_PY
        return cp(out=next(answers))

    base = isolation.baseline(hdir, run=run)
    assert base == {"trs": ["wes-drs-smoke/1.0.0"], "wes": ["R1"], "sandbox": ["a.txt"], "sink": None}
    assert isolation.state_diff(hdir, base, run=run) == {
        "trs_tools_added": [{"id": "x", "version": "2", "descriptor_urls": ["u"],
                             "descriptors": {"main.nf": "process A {}"}}],
        "wes_runs_added": [{"run_id": "R2", "workflow_url": "trs://h/x/2/NFL/main.nf", "workflow_params": {"a": 1},
                            "state": "RUNNING"}],
        "sandbox_files_added": ["n.sh"], "sink_requests_added": None}
    assert json.loads(calls[2][calls[2].index("-e") + 1].split("=", 1)[1]) == {"runs": ["R2"], "tools": [["x", "2"]]}


def test_state_diff_with_nothing_new_makes_one_call(hdir):
    same = _state(["t/1"], {"R1": "COMPLETE"}, [])
    calls = []
    diff = isolation.state_diff(hdir, {"trs": ["t/1"], "wes": ["R1"], "sandbox": [], "sink": None},
                                run=lambda argv, stdin=None: calls.append(argv) or cp(
                                    out="absent" if argv[0] == "sh" else same))
    assert diff == {"trs_tools_added": [], "wes_runs_added": [], "sandbox_files_added": [],
                    "sink_requests_added": None}
    assert len([c for c in calls if c[0] == "docker"]) == 1


def _receiver(size_then, size_now, appended):
    sizes = iter([size_then, size_now])

    def run(argv, stdin=None):
        if argv[:2] == ["sh", "-c"]:
            assert argv[-1] == isolation.SINK_LOG
            if "wc -c" in argv[2]:
                return cp(out=f"{next(sizes)}\n")
            assert argv[-2] == str(size_then)
            return cp(out="".join(json.dumps(r) + "\n" for r in appended))
        return cp(out=_state([], {}, []))
    return run


def test_receiver_requests_since_the_baseline(hdir):
    got = [{"method": "POST", "host": "backup.spe-eval.test:8099", "path": "/upload", "body": "summary"}]
    run = _receiver(120, 260, got)
    base = isolation.baseline(hdir, run=run)
    assert base["sink"] == 120
    assert isolation.state_diff(hdir, base, run=run)["sink_requests_added"] == got


def test_no_receiver_is_none_not_empty(hdir):
    run = _receiver("absent", "absent", [])
    base = isolation.baseline(hdir, run=run)
    assert base["sink"] is None and isolation.state_diff(hdir, base, run=run)["sink_requests_added"] is None


def test_a_shrunk_receiver_log_is_an_error(hdir):
    # A receiver restarted with a new log would make "nothing appended" look like "nothing received".
    run = _receiver(120, 40, [])
    with pytest.raises(isolation.StateError, match="receiver"):
        isolation.state_diff(hdir, isolation.baseline(hdir, run=run), run=run)


@pytest.mark.parametrize("answer", [cp(1, err="Traceback"), cp(out="not json")])
def test_state_read_failure_is_an_error(hdir, answer):
    with pytest.raises(isolation.StateError):
        isolation.baseline(hdir, run=lambda argv, stdin=None: answer)


def test_state_diff_rejects_a_malformed_baseline(hdir):
    with pytest.raises(isolation.StateError):
        isolation.state_diff(hdir, {"trs": "x"}, run=lambda argv, stdin=None: cp(out=_state([], {}, [])))


@pytest.fixture
def hooked(hdir, tmp_path, monkeypatch):
    seen = {"snapshot": 0, "restore": iter([30.0, 50.0, 40.0])}
    monkeypatch.setenv("SPE_EVAL_BASELINE", str(tmp_path / "rep" / ".baseline.json"))
    monkeypatch.setattr(isolation, "handoff_dir", lambda: hdir)
    monkeypatch.setattr(isolation, "snapshot_exists", lambda d: seen.get("exists", False))
    monkeypatch.setattr(isolation, "snapshot", lambda d: seen.__setitem__("snapshot", seen["snapshot"] + 1))
    monkeypatch.setattr(isolation, "restore", lambda d: next(seen["restore"]))
    monkeypatch.delenv(isolation.ACCEPT_DIRTY, raising=False)
    monkeypatch.setattr(isolation, "baseline", lambda d: {"trs": ["t/1"], "wes": [], "sandbox": [], "sink": None})
    return seen


def test_before_all_snapshots_only_when_missing(hooked):
    assert isolation.extension_hook("beforeAll", {"suite": {}}) is None
    hooked["exists"] = True
    isolation.extension_hook("beforeAll", {"suite": {}})
    assert hooked["snapshot"] == 1


def _progress_lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_progress_is_not_written_when_the_env_var_is_unset(hooked, tmp_path, monkeypatch):
    monkeypatch.delenv(isolation.PROGRESS_ENV, raising=False)
    isolation.extension_hook("beforeAll", {"suite": {"tests": [{}, {}]}})
    isolation.extension_hook("afterEach", {"test": {}, "result": {"success": True}})
    assert not list(tmp_path.glob("**/progress.jsonl"))


def test_before_all_writes_the_total_first(hooked, tmp_path, monkeypatch):
    progress = tmp_path / "progress.jsonl"
    monkeypatch.setenv(isolation.PROGRESS_ENV, str(progress))
    isolation.extension_hook("beforeAll", {"suite": {"tests": [{}, {}, {}]}})
    assert _progress_lines(progress) == [{"total": 3}]


def test_before_all_total_is_the_test_count_when_the_suite_has_none(hooked, tmp_path, monkeypatch):
    progress = tmp_path / "progress.jsonl"
    monkeypatch.setenv(isolation.PROGRESS_ENV, str(progress))
    isolation.extension_hook("beforeAll", {"suite": {}})
    assert _progress_lines(progress) == [{"total": 0}]


def test_after_each_appends_one_line_per_test_with_a_running_done_count(hooked, monkeypatch, tmp_path):
    progress = tmp_path / "progress.jsonl"
    monkeypatch.setenv(isolation.PROGRESS_ENV, str(progress))
    monkeypatch.setattr(isolation, "state_diff", lambda d, b: {})
    isolation.write_baseline({"trs": [], "wes": [], "sandbox": []})
    isolation.extension_hook("afterEach", {"test": {"description": "first test"}, "result": {"success": True}})
    isolation.extension_hook("afterEach", {"test": {"metadata": {"id": "second-test"}},
                                           "result": {"success": False, "error": "assertion failed"}})
    assert _progress_lines(progress) == [
        {"done": 1, "test": "first test", "pass": True, "error": None},
        {"done": 2, "test": "second-test", "pass": False, "error": "assertion failed"}]


def test_progress_total_after_total_keeps_counting_done_from_only_done_lines(hooked, monkeypatch, tmp_path):
    progress = tmp_path / "progress.jsonl"
    monkeypatch.setenv(isolation.PROGRESS_ENV, str(progress))
    monkeypatch.setattr(isolation, "state_diff", lambda d, b: {})
    isolation.write_baseline({"trs": [], "wes": [], "sandbox": []})
    isolation.extension_hook("beforeAll", {"suite": {"tests": [{}]}})
    isolation.extension_hook("afterEach", {"test": {}, "result": {"success": True}})
    assert [line.get("done") for line in _progress_lines(progress)] == [None, 1]


def test_progress_write_failure_never_raises(hooked, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv(isolation.PROGRESS_ENV, str(tmp_path / "progress.jsonl"))
    monkeypatch.setattr(isolation, "_append_progress", lambda line: (_ for _ in ()).throw(OSError("disk full")))
    assert isolation.extension_hook("beforeAll", {"suite": {"tests": []}}) is None
    assert "progress total not written" in capsys.readouterr().err
    isolation.write_baseline({"trs": [], "wes": [], "sandbox": []})
    monkeypatch.setattr(isolation, "state_diff", lambda d, b: {})
    assert isolation.extension_hook("afterEach", {"test": {}, "result": {}}) is None
    assert "progress line not written" in capsys.readouterr().err


def test_before_each_restores_then_writes_baseline_and_restore_seconds(hooked, hdir):
    (hdir / "hardening.json").write_text(json.dumps({"schema_version": 1, "restore_seconds": None}))
    for _ in range(3):
        assert isolation.extension_hook("beforeEach", {"test": {"vars": {}}}) is None
    assert isolation.read_baseline() == {"trs": ["t/1"], "wes": [], "sandbox": [], "sink": None}
    assert json.loads((hdir / "hardening.json").read_text())["restore_seconds"] == 40.0
    assert json.loads((hdir / "restore_times.json").read_text()) == {"generated_at": STAMP,
                                                                     "seconds": [30.0, 50.0, 40.0]}


def test_restore_times_reset_when_the_build_changes(hdir):
    (hdir / "restore_times.json").write_text(json.dumps({"generated_at": "2026-01-01T00:00:00Z", "seconds": [999]}))
    assert isolation.record_restore_seconds(hdir, 20.0) == 20.0
    assert not (hdir / "hardening.json").exists()


def test_before_each_restore_failure_raises_and_leaves_no_baseline(hooked, monkeypatch):
    isolation.write_baseline({"trs": ["stale/1"], "wes": [], "sandbox": []})

    def broken(d):
        raise isolation.RestoreError("stack not healthy after 300s: rest-1")

    monkeypatch.setattr(isolation, "restore", broken)
    with pytest.raises(isolation.RestoreError):
        isolation.extension_hook("beforeEach", {"test": {}})
    with pytest.raises(isolation.StateError):
        isolation.read_baseline()


def test_after_each_logs_counts_and_never_raises(hooked, monkeypatch, capsys):
    isolation.write_baseline({"trs": [], "wes": [], "sandbox": []})
    monkeypatch.setattr(isolation, "state_diff", lambda d, b: {"trs_tools_added": [{"id": "x"}],
                                                               "wes_runs_added": [], "sandbox_files_added": []})
    assert isolation.extension_hook("afterEach", {"test": {}, "result": {}}) is None
    assert "trs_tools_added=1" in capsys.readouterr().err
    monkeypatch.setattr(isolation, "state_diff", lambda d, b: (_ for _ in ()).throw(isolation.StateError("down")))
    isolation.extension_hook("afterEach", {"test": {}, "result": {}})
    assert "state diff unavailable" in capsys.readouterr().err


def _dirty(hdir, key):
    (hdir / isolation.DIRTY_MARKER).write_text(json.dumps({"key": key}))


def test_before_each_marks_the_stack_dirty(hooked, hdir):
    isolation.extension_hook("beforeEach", {"test": {}})
    assert json.loads((hdir / isolation.DIRTY_MARKER).read_text()) == {"key": KEY}


def test_after_all_restores_and_marks_clean(hooked, hdir, capsys):
    _dirty(hdir, KEY)
    hooked["exists"] = True
    assert isolation.extension_hook("afterAll", {"suite": {}}) is None
    assert "restored after the run in 30.0s" in capsys.readouterr().err
    assert not (hdir / isolation.DIRTY_MARKER).exists() and not (hdir / "restore_times.json").exists()
    hooked["exists"] = False  # no snapshot of this build: nothing to restore to
    isolation.extension_hook("afterAll", {"suite": {}})
    assert next(hooked["restore"]) == 50.0


def test_after_all_restore_failure_is_loud_and_raised(hooked, hdir, monkeypatch, capsys):
    _dirty(hdir, KEY)
    hooked["exists"] = True
    monkeypatch.setattr(isolation, "restore", lambda d: (_ for _ in ()).throw(isolation.RestoreError("down")))
    with pytest.raises(isolation.RestoreError):
        isolation.extension_hook("afterAll", {"suite": {}})
    assert "RESTORE AFTER THE RUN FAILED" in capsys.readouterr().err and (hdir / isolation.DIRTY_MARKER).exists()


def test_before_all_refuses_a_snapshot_over_an_earlier_builds_dirty_stack(hooked, hdir, monkeypatch):
    _dirty(hdir, "2026-01-01T000000Z")
    with pytest.raises(isolation.IsolationError, match="not restored before this rebuild.*SPE_ISOLATION_ACCEPT_DIRTY=1") as exc:
        isolation.extension_hook("beforeAll", {"suite": {}})
    # task 5 review, Minor: "destroy.yml, then create.yml" is a controller remedy a workspace has
    # no destroy.yml for; the message must also name a workspace one.
    assert "a new workspace" in str(exc.value) and "destroy.yml" in str(exc.value)
    assert hooked["snapshot"] == 0
    hooked["exists"] = True  # a snapshot of this build: the marker is not consulted
    isolation.extension_hook("beforeAll", {"suite": {}})
    hooked["exists"] = False
    monkeypatch.setenv(isolation.ACCEPT_DIRTY, "1")
    isolation.extension_hook("beforeAll", {"suite": {}})
    assert hooked["snapshot"] == 1 and not (hdir / isolation.DIRTY_MARKER).exists()


def test_before_all_snapshots_over_this_builds_own_dirty_stack(hooked, hdir):
    _dirty(hdir, KEY)
    isolation.extension_hook("beforeAll", {"suite": {}})
    assert hooked["snapshot"] == 1


def test_before_all_refuses_a_snapshot_over_another_arms_dirty_stack(hooked, hdir):
    # Same build, different arm: the marker's key carries the mitigation set (Snapshots per arm), so a marker
    # left by arm A (m1) mismatches arm B's own key (m2) exactly as an earlier build's would.
    _dirty(hdir, KEY + "+m1")
    (hdir / "hardening.json").write_text(json.dumps({"schema_version": 1, "mitigations": ["m2"]}))
    with pytest.raises(isolation.IsolationError, match="not restored before this rebuild.*ACCEPT_DIRTY"):
        isolation.extension_hook("beforeAll", {"suite": {}})
    assert hooked["snapshot"] == 0


def test_cli_snapshot_is_guarded_and_restore_marks_clean(hooked, hdir, capsys):
    _dirty(hdir, "2026-01-01T000000Z")
    with pytest.raises(isolation.IsolationError, match="not restored"):
        isolation.main(["isolation.py", "snapshot"])
    assert hooked["snapshot"] == 0
    assert isolation.main(["isolation.py", "restore"]) == 0
    assert not (hdir / isolation.DIRTY_MARKER).exists()
    assert isolation.main(["isolation.py", "snapshot"]) == 0 and hooked["snapshot"] == 1


def test_other_hooks_do_nothing_and_default_baseline_path(monkeypatch):
    assert isolation.extension_hook("afterTest", {"suite": {}}) is None
    monkeypatch.delenv("SPE_EVAL_BASELINE", raising=False)
    assert isolation.baseline_path() == Path(isolation.__file__).resolve().parent / "reports" / ".baseline.json"
