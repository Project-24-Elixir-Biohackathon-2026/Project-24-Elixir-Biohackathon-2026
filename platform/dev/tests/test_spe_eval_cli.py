"""The `spe-eval` command line (experiments spec part 03, decisions 7, 9, 11, 18, 22; part 07's
command table): `arm`, `run` (with `--detach`), `status`, `wait`, `runs`. Fakes `spe-apply`,
`run.sh` and `systemd-run` so no real Ansible, Docker or model call happens; a tiny two-experiment
catalogue (`one-arm`, `two-arm`) keeps each test fast and independent of the real `experiments/`/
`mitigations/` files (those are exercised against the real catalogue by `test_spe_eval.py`).

The health wait (task 4 review, Critical 1) probes a real `http.server` on `127.0.0.1`, not a
fake `spe-apply status` line: the real script prints the `/healthz` response *body*
(`{"status": "ok", ...}`), not a bare status code, so a fake that invented `agent /healthz: 200`
was asserting a contract the real script does not have.
"""
import http.server
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).resolve().parents[2]  # platform/dev/tests -> platform
SPE_EVAL = HERE / "instance" / "spe-eval"

FAKE_SPE_APPLY = """#!/bin/sh
echo "$*" >> "$FAKE_SPE_APPLY_LOG"
exit "${FAKE_SPE_APPLY_EXIT:-0}"
"""

# Mirrors run.sh's own --reports-dir contract (gate-notes.json always written, run.json only on
# success: experiments spec 03), without any real promptfoo/model call.
FAKE_RUN_SH = """#!/bin/sh
echo "$*" >> "$FAKE_RUN_SH_LOG"
shift 2
reports_dir=""
while [ $# -gt 0 ]; do
  case "$1" in
    --suite) shift 2 ;;
    --reports-dir) reports_dir=$2; shift 2 ;;
    --description) shift 2 ;;
    *) shift ;;
  esac
done
if [ -n "${FAKE_RUN_SH_SLEEP:-}" ]; then sleep "$FAKE_RUN_SH_SLEEP"; fi
code=${FAKE_RUN_SH_EXIT:-0}
if [ -n "$reports_dir" ]; then
  mkdir -p "$reports_dir"
  echo '{"results": {"results": []}}' > "$reports_dir/controls.json"
  echo '{"results": {"results": []}}' > "$reports_dir/agent.json"
  echo '[]' > "$reports_dir/gate-notes.json"
  if [ "$code" = 0 ]; then
    echo '{"started": "2026-11-10T12:00:00Z", "canaries_sha256": "abc"}' > "$reports_dir/run.json"
  fi
fi
exit "$code"
"""

# Starts, in the background, logs its call and returns at once (as the real systemd-run does:
# task 4 review, Important 3 needs the *child* to take the lock asynchronously so --detach's own
# poll loop has something real to wait for). Unless FAKE_SYSTEMD_RUN_NO_ACQUIRE is set, the
# background subshell takes the lock file's flock itself (mirroring spe_eval.Lock's own format:
# the token alone, written once the flock succeeds) and holds it for FAKE_SYSTEMD_RUN_HOLD
# seconds, simulating the detached `spe-eval run` child actually running.
FAKE_SYSTEMD_RUN = """#!/bin/sh
echo "$*" >> "$FAKE_SYSTEMD_RUN_LOG"
if [ -n "${FAKE_SYSTEMD_RUN_ENV_LOG:-}" ]; then
  echo "XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-}" >> "$FAKE_SYSTEMD_RUN_ENV_LOG"
  echo "DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-}" >> "$FAKE_SYSTEMD_RUN_ENV_LOG"
fi
if [ -n "${FAKE_SYSTEMD_RUN_NO_ACQUIRE:-}" ]; then exit 0; fi
token=""
for a in "$@"; do
  case "$a" in
    --setenv=SPE_EVAL_RUN_ID=*) token=${a#--setenv=SPE_EVAL_RUN_ID=} ;;
  esac
done
lock_file="$HOME/spe-eval/lock"
mkdir -p "$(dirname "$lock_file")"
# Detached from this script's own stdin/stdout/stderr (as the real systemd-run also would, and
# unlike an inline "&" background job): otherwise, since those are `subprocess.run(capture_output=
# True)`'s own pipes, the backgrounded subshell inheriting them keeps the write end open for its
# whole FAKE_SYSTEMD_RUN_HOLD, so the *caller's* subprocess.run does not return until the hold is
# already over -- by which time a holder() that checks the real flock (task 5 review, Important
# 4a) correctly finds it already released, instead of "still running".
(
  exec 9>"$lock_file"
  flock 9
  printf '%s' "$token" >&9
  sleep "${FAKE_SYSTEMD_RUN_HOLD:-0.5}"
) >/dev/null 2>&1 </dev/null &
exit 0
"""


class _HealthServer:
    """A real HTTP server answering `/healthz` on `127.0.0.1`, for `_wait_for_stack`'s direct
    probe. `status_code`/`body` mirror what the real agent's `/healthz` sends (200
    `{"status": "ok", ...}` when ready, 503 `{"status": "starting", ...}` otherwise)."""

    def __init__(self, status_code: int = 200, body: bytes = b'{"status": "ok", "tools": 1}'):
        status, payload = status_code, body

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 (BaseHTTPRequestHandler's own naming)
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):  # keep test output clean
                pass

        self._httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_port}/healthz"

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


@pytest.fixture
def setup(tmp_path):
    repo = tmp_path / "repo"
    (repo / "experiments").mkdir(parents=True)
    (repo / "mitigations").mkdir(parents=True)
    (repo / "platform" / "ansible" / "instances").mkdir(parents=True)
    (repo / "platform" / "ansible" / "catalog" / "injections").mkdir(parents=True)
    (repo / "platform" / "promptfoo-evals").mkdir(parents=True)

    (repo / "platform" / "ansible" / "catalog" / "injections" / "fixtures.json").write_text(
        json.dumps({"fixtures": []}))

    common_params = {"samples": ["HG002"], "tiers": ["ref"], "workflows": ["wk1"], "smoke_test": False}
    (repo / "experiments" / "one-arm.yml").write_text(yaml.safe_dump({
        "parameters": {"experiment": "one-arm", "mitigations": [], **common_params},
        "experiment": {"mitigation": None, "base": [], "injections": [], "tests": []},
        "vars": {},
    }))
    (repo / "experiments" / "two-arm.yml").write_text(yaml.safe_dump({
        "parameters": {"experiment": "two-arm", "mitigations": [], **common_params},
        "experiment": {"mitigation": "M1", "base": [], "injections": [], "tests": []},
        "vars": {},
    }))
    (repo / "mitigations" / "M1.yml").write_text(yaml.safe_dump({
        "id": "M1", "on": {"spe_test_switch": True}, "off": {"spe_test_switch": False}, "probes": [],
    }))
    (repo / "platform" / "ansible" / "instances" / "local.yml").write_text(yaml.safe_dump({
        "spe_experiment": "one-arm", "spe_mitigations": [],
        "spe_samples": ["HG002"], "spe_tiers": ["ref"], "spe_workflows": ["wk1"], "spe_run_smoke_test": False,
        "spe_agent_model_provider": "anthropic", "spe_agent_model": "claude-haiku-5-5",
    }))
    (repo / "platform" / "promptfoo-evals" / "agent.yaml").write_text("tests: []\n")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, content in (("spe-apply", FAKE_SPE_APPLY), ("systemd-run", FAKE_SYSTEMD_RUN)):
        path = bin_dir / name
        path.write_text(content)
        path.chmod(0o755)
    run_sh = repo / "platform" / "promptfoo-evals" / "run.sh"
    run_sh.write_text(FAKE_RUN_SH)
    run_sh.chmod(0o755)

    home = tmp_path / "home"
    home.mkdir()
    log_apply = tmp_path / "spe-apply.log"
    log_run_sh = tmp_path / "run-sh.log"
    log_systemd = tmp_path / "systemd-run.log"
    health = _HealthServer(200)  # the default: every arm's apply is answered at once

    def base_env(env):
        return {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "HOME": str(home),
                "SPE_REPO_DIR": str(repo), "FAKE_SPE_APPLY_LOG": str(log_apply),
                "FAKE_RUN_SH_LOG": str(log_run_sh), "FAKE_SYSTEMD_RUN_LOG": str(log_systemd),
                "SPE_EVAL_HEALTH_URL": health.url, "SPE_EVAL_HEALTH_INTERVAL": "0.01",
                "SPE_EVAL_HEALTH_TIMEOUT": "0.3", "SPE_EVAL_WAIT_INTERVAL": "0.05",
                "SPE_EVAL_DETACH_WAIT_TIMEOUT": "3", "SPE_EVAL_DETACH_WAIT_INTERVAL": "0.02",
                **(env or {})}

    def run(*args, env=None, timeout=20):
        return subprocess.run([sys.executable, str(SPE_EVAL), *args], env=base_env(env), capture_output=True,
                               text=True, timeout=timeout)

    def popen(*args, env=None):
        return subprocess.Popen([sys.executable, str(SPE_EVAL), *args], env=base_env(env),
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def calls(log_path: Path) -> list[str]:
        return log_path.read_text().splitlines() if log_path.exists() else []

    try:
        yield run, popen, calls, repo, home, {"apply": log_apply, "run_sh": log_run_sh, "systemd": log_systemd}
    finally:
        health.close()


def wait_until_locked(home: Path, timeout: float = 5.0) -> None:
    lock = home / "spe-eval" / "lock"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if lock.exists() and lock.read_text().strip():
            return
        time.sleep(0.02)
    raise AssertionError("lock never appeared")


# --- arm ---------------------------------------------------------------------------------------

def test_arm_one_arm_experiment_applies_and_waits(setup):
    run, _popen, calls, _repo, _home, logs = setup
    p = run("arm", "one-arm", "baseline")
    assert p.returncode == 0, p.stderr
    assert "applied" in p.stdout
    apply_calls = calls(logs["apply"])
    assert any(c.startswith("all -e @") for c in apply_calls)


def test_arm_exits_1_when_the_stack_never_answers(setup):
    # task 4 review, Critical 1: a real (never-ready) health server, not a fake spe-apply line.
    run, _popen, _calls, _repo, _home, _logs = setup
    unhealthy = _HealthServer(503, b'{"status": "starting", "reason": "still loading"}')
    try:
        p = run("arm", "one-arm", "baseline", env={"SPE_EVAL_HEALTH_URL": unhealthy.url})
        assert p.returncode == 1, p.stdout
        assert "did not answer in time" in p.stderr
    finally:
        unhealthy.close()


def test_arm_unknown_arm_name_is_a_configuration_error(setup):
    # one-arm has baseline only: "mitigated" raises ValueError (arm_mitigations), mapped to exit 2
    # by main() (task 3 review, minor 2).
    run, _popen, _calls, _repo, _home, _logs = setup
    p = run("arm", "one-arm", "mitigated")
    assert p.returncode == 2, p.stdout
    assert "not an arm" in p.stderr


def test_arm_refuses_while_locked(setup):
    run, popen, _calls, _repo, home, _logs = setup
    holder = popen("run", "one-arm", env={"FAKE_RUN_SH_SLEEP": "1"})
    try:
        wait_until_locked(home)
        p = run("arm", "one-arm", "baseline")
        assert p.returncode == 2, p.stdout
        assert "holds the lock" in p.stderr
    finally:
        holder.communicate(timeout=10)


# --- run ---------------------------------------------------------------------------------------

def test_run_json_keeps_canaries_sha256_from_run_sh(setup):
    # task 5 review, Important 3: spe-eval's own run.json write (state/ended/gate_notes), in
    # cmd_run's `finally`, must merge into the run.json run.sh already wrote on success rather
    # than overwrite it outright, or matrix.counts/replay.py never find canaries_sha256 again.
    run, _popen, _calls, _repo, home, _logs = setup
    p = run("run", "one-arm", env={"SPE_EVAL_RUN_ID": "20261110T190000Z"})
    assert p.returncode == 0, p.stderr
    record = json.loads((home / "spe-eval" / "reports" / "one-arm" / "20261110T190000Z" / "baseline" /
                          "run.json").read_text())
    assert record["canaries_sha256"] == "abc"  # FAKE_RUN_SH's own run.json, on success
    assert record["started"]
    assert record["state"] == "ok"


def test_run_two_arm_order_and_return_to_build_arm(setup):
    run, _popen, calls, _repo, home, logs = setup
    p = run("run", "two-arm", env={"SPE_EVAL_RUN_ID": "20261110T100000Z"})
    assert p.returncode == 0, p.stderr

    apply_calls = [c for c in calls(logs["apply"]) if c.startswith("all")]
    # baseline applied, mitigated applied, then the build's own arm reapplied with no override.
    assert len(apply_calls) == 3
    assert apply_calls[0].startswith("all -e @")
    assert apply_calls[1].startswith("all -e @")
    assert apply_calls[2] == "all"

    for arm in ("baseline", "mitigated"):
        record = json.loads((home / "spe-eval" / "reports" / "two-arm" / "20261110T100000Z" / arm /
                              "run.json").read_text())
        assert record["state"] == "ok"
        assert record["experiment"] == "two-arm"
        assert record["run"] == "20261110T100000Z"
    baseline = json.loads((home / "spe-eval" / "reports" / "two-arm" / "20261110T100000Z" / "baseline" /
                            "run.json").read_text())
    mitigated = json.loads((home / "spe-eval" / "reports" / "two-arm" / "20261110T100000Z" / "mitigated" /
                             "run.json").read_text())
    assert baseline["mitigations"] == []
    assert mitigated["mitigations"] == ["M1"]

    windows = (home / "spe-eval" / "windows.jsonl").read_text().splitlines()
    assert len(windows) == 1
    window = json.loads(windows[0])
    assert window["run"] == "20261110T100000Z" and window["experiment"] == "two-arm"


def test_run_gate_refused_is_recorded_and_exits_1(setup):
    run, _popen, _calls, _repo, home, _logs = setup
    p = run("run", "one-arm", env={"SPE_EVAL_RUN_ID": "20261110T110000Z", "FAKE_RUN_SH_EXIT": "3"})
    assert p.returncode == 1, p.stdout
    record = json.loads((home / "spe-eval" / "reports" / "one-arm" / "20261110T110000Z" / "baseline" /
                          "run.json").read_text())
    assert record["state"] == "gate refused"


def test_run_existing_reports_dir_is_refused(setup):
    run, _popen, _calls, _repo, home, _logs = setup
    existing = home / "spe-eval" / "reports" / "one-arm" / "20261110T120000Z" / "baseline"
    existing.mkdir(parents=True)
    p = run("run", "one-arm", env={"SPE_EVAL_RUN_ID": "20261110T120000Z"})
    assert p.returncode == 2, p.stdout
    assert "already exists" in p.stderr


@pytest.mark.parametrize("repeat", ["0", "-1", "x"])
def test_run_bad_repeat_is_rejected_up_front(setup, repeat):
    # task 5 review, Minor: run.sh's own usage check only runs after a full `spe-apply all`,
    # marking the arm `failed`; argparse must catch a bad --repeat before any of that.
    run, _popen, calls, _repo, _home, logs = setup
    p = run("run", "one-arm", "--repeat", repeat)
    assert p.returncode == 2, p.stdout
    assert calls(logs["apply"]) == []


def test_run_refuses_while_another_run_holds_the_lock(setup):
    run, popen, _calls, _repo, home, _logs = setup
    holder = popen("run", "one-arm", env={"FAKE_RUN_SH_SLEEP": "1", "SPE_EVAL_RUN_ID": "20261110T130000Z"})
    try:
        wait_until_locked(home)
        p = run("run", "one-arm")
        assert p.returncode == 2, p.stdout
        assert "20261110T130000Z holds the lock" in p.stderr
    finally:
        holder.communicate(timeout=10)


def test_run_sigterm_mid_run_sh_marks_stopped_and_still_cleans_up(setup):
    # task 4 review, Important 2: a stop mid-run.sh still writes a terminal run.json, the
    # windows.jsonl line, and still returns to the build's own arm, all before the lock frees.
    run, popen, calls, _repo, home, logs = setup
    proc = popen("run", "one-arm", env={"SPE_EVAL_RUN_ID": "20261111T100000Z", "FAKE_RUN_SH_SLEEP": "2"})
    try:
        wait_until_locked(home)
        time.sleep(0.3)  # let the fake apply/health-wait finish and run.sh actually start sleeping
        proc.send_signal(signal.SIGTERM)
        _out, err = proc.communicate(timeout=10)
        assert proc.returncode == 1, err
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=5)

    record = json.loads((home / "spe-eval" / "reports" / "one-arm" / "20261111T100000Z" / "baseline" /
                          "run.json").read_text())
    assert record["state"] == "stopped"
    assert record["ended"]

    windows = (home / "spe-eval" / "windows.jsonl").read_text().splitlines()
    assert len(windows) == 1
    window = json.loads(windows[0])
    assert window["run"] == "20261111T100000Z"

    apply_calls = [c for c in calls(logs["apply"]) if c.startswith("all")]
    assert apply_calls[-1] == "all"  # the return-to-build-arm reapply still ran


def test_run_detach_prints_the_run_id_and_returns_at_once(setup):
    run, _popen, calls, _repo, _home, logs = setup
    started = time.monotonic()
    p = run("run", "one-arm", "--detach", env={"FAKE_SYSTEMD_RUN_HOLD": "2"})
    elapsed = time.monotonic() - started
    assert p.returncode == 0, p.stderr
    run_id = p.stdout.strip().splitlines()[-1]
    assert re.fullmatch(r"\d{8}T\d{6}Z", run_id)
    assert elapsed < 5
    systemd_calls = calls(logs["systemd"])
    assert len(systemd_calls) == 1
    assert f"--unit=spe-eval-{run_id}" in systemd_calls[0]
    assert f"SPE_EVAL_RUN_ID={run_id}" in systemd_calls[0]
    assert "run one-arm --repeat 1" in systemd_calls[0]


def test_run_detach_validates_before_starting_the_unit(setup):
    # task 4 review, Important 3: a typo'd experiment never reaches systemd-run.
    run, _popen, calls, _repo, _home, logs = setup
    p = run("run", "no-such-experiment", "--detach")
    assert p.returncode == 2, p.stdout
    assert calls(logs["systemd"]) == []


def test_run_detach_refuses_while_locked(setup):
    run, popen, calls, _repo, home, logs = setup
    holder = popen("run", "one-arm", env={"FAKE_RUN_SH_SLEEP": "1", "SPE_EVAL_RUN_ID": "20261111T110000Z"})
    try:
        wait_until_locked(home)
        p = run("run", "one-arm", "--detach")
        assert p.returncode == 2, p.stdout
        assert "holds the lock" in p.stderr
        assert calls(logs["systemd"]) == []
    finally:
        holder.communicate(timeout=10)


def test_run_detach_waits_for_the_child_to_hold_the_lock(setup):
    # task 4 review, Important 3: --detach does not return until the (simulated) child has
    # actually taken the lock, so a `wait` right after sees a run in progress, not "no run".
    run, _popen, _calls, _repo, home, _logs = setup
    p = run("run", "one-arm", "--detach", env={"FAKE_SYSTEMD_RUN_HOLD": "2"})
    assert p.returncode == 0, p.stderr
    run_id = p.stdout.strip().splitlines()[-1]
    lock = home / "spe-eval" / "lock"
    assert lock.read_text().strip() == run_id


def test_run_detach_exits_1_if_the_child_never_takes_the_lock(setup):
    run, _popen, _calls, _repo, _home, _logs = setup
    p = run("run", "one-arm", "--detach", env={"FAKE_SYSTEMD_RUN_NO_ACQUIRE": "1",
                                                "SPE_EVAL_DETACH_WAIT_TIMEOUT": "0.2"})
    assert p.returncode == 1, p.stdout
    assert "did not take the lock" in p.stderr


def test_run_detach_defaults_the_user_bus_when_unset(setup, tmp_path):
    # task 5 review, Important 4b: the Coder agent is a system unit with no PAM session, so its
    # shells have neither XDG_RUNTIME_DIR nor DBUS_SESSION_BUS_ADDRESS; systemd-run --user then
    # fails to connect to the bus. spe-eval must default both, from /run/user/<uid>, rather than
    # pass them through unset.
    run, _popen, _calls, _repo, _home, logs = setup
    env_log = tmp_path / "systemd-env.log"
    p = run("run", "one-arm", "--detach",
            env={"FAKE_SYSTEMD_RUN_ENV_LOG": str(env_log), "XDG_RUNTIME_DIR": "", "DBUS_SESSION_BUS_ADDRESS": ""})
    assert p.returncode == 0, p.stderr
    lines = env_log.read_text().splitlines()
    uid = os.getuid()
    assert lines == [f"XDG_RUNTIME_DIR=/run/user/{uid}",
                     f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus"]


def test_run_detach_keeps_an_already_set_user_bus(setup, tmp_path):
    run, _popen, _calls, _repo, _home, logs = setup
    env_log = tmp_path / "systemd-env.log"
    p = run("run", "one-arm", "--detach",
            env={"FAKE_SYSTEMD_RUN_ENV_LOG": str(env_log), "XDG_RUNTIME_DIR": "/custom/run",
                 "DBUS_SESSION_BUS_ADDRESS": "unix:path=/custom/run/bus"})
    assert p.returncode == 0, p.stderr
    assert env_log.read_text().splitlines() == ["XDG_RUNTIME_DIR=/custom/run",
                                                "DBUS_SESSION_BUS_ADDRESS=unix:path=/custom/run/bus"]


# --- status / wait / runs ----------------------------------------------------------------------

def test_status_json_reports_the_run_in_progress(setup):
    run, popen, _calls, _repo, home, _logs = setup
    holder = popen("run", "one-arm", env={"FAKE_RUN_SH_SLEEP": "1", "SPE_EVAL_RUN_ID": "20261110T140000Z"})
    try:
        wait_until_locked(home)
        p = run("status", "--json")
        assert p.returncode == 0, p.stderr
        info = json.loads(p.stdout)
        assert info["locked"] is True
        assert info["holder"] == "20261110T140000Z"
        assert info["run"] == "20261110T140000Z"
        assert info["experiment"] == "one-arm"
        assert info["arm"] == "baseline"
        assert info["state"] == "running"
    finally:
        holder.communicate(timeout=10)


def test_status_json_with_no_run_yet(setup):
    run, _popen, _calls, _repo, _home, _logs = setup
    p = run("status", "--json")
    assert p.returncode == 0, p.stderr
    info = json.loads(p.stdout)
    assert info == {"locked": False, "holder": None, "run": None, "experiment": None, "arm": None,
                     "state": None, "done": None, "total": None, "last_error": None}


def test_status_while_held_by_arm_leaves_run_arm_state_null(setup):
    # task 4 review, minor 6: a holder with no report of its own (here, `arm`) must not be shown
    # next to some earlier run's details.
    run, popen, _calls, _repo, home, _logs = setup
    prior = run("run", "one-arm", env={"SPE_EVAL_RUN_ID": "20261111T120000Z"})
    assert prior.returncode == 0, prior.stderr

    unhealthy = _HealthServer(503, b'{"status": "starting"}')
    try:
        # A generous health timeout (well past another subprocess's startup time under load),
        # so the lock is reliably still held when `status` is checked below.
        holder = popen("arm", "one-arm", "baseline",
                        env={"SPE_EVAL_HEALTH_URL": unhealthy.url, "SPE_EVAL_HEALTH_TIMEOUT": "5"})
        try:
            wait_until_locked(home)
            p = run("status", "--json")
            assert p.returncode == 0, p.stderr
            info = json.loads(p.stdout)
            assert info["locked"] is True
            assert info["run"] is None
            assert info["arm"] is None
            assert info["state"] is None
        finally:
            holder.communicate(timeout=10)
    finally:
        unhealthy.close()


def test_wait_timeout_exits_1_and_says_so(setup):
    run, popen, _calls, _repo, home, _logs = setup
    holder = popen("run", "one-arm", env={"FAKE_RUN_SH_SLEEP": "2", "SPE_EVAL_RUN_ID": "20261110T150000Z"})
    try:
        wait_until_locked(home)
        started = time.monotonic()
        p = run("wait", "--timeout", "0.2")
        elapsed = time.monotonic() - started
        assert p.returncode == 1, p.stdout
        assert "did not finish within" in p.stderr
        assert elapsed < 2
    finally:
        holder.communicate(timeout=10)


def test_wait_returns_the_run_s_outcome_once_the_lock_frees(setup):
    run, popen, _calls, _repo, home, _logs = setup
    holder = popen("run", "one-arm", env={"FAKE_RUN_SH_SLEEP": "0.3", "SPE_EVAL_RUN_ID": "20261110T160000Z"})
    try:
        wait_until_locked(home)
        p = run("wait", "--timeout", "5")
        assert p.returncode == 0, p.stdout
        assert "baseline: ok" in p.stdout
    finally:
        holder.communicate(timeout=10)


def test_wait_with_no_run_at_all(setup):
    run, _popen, _calls, _repo, _home, _logs = setup
    p = run("wait")
    assert p.returncode == 0, p.stderr
    assert "no run has happened yet" in p.stdout


def test_wait_when_lock_already_free_judges_the_newest_run(setup):
    # task 4 review, Important 3: wait must not exit 0 unconditionally just because the lock
    # happens to be free when it is called -- `run --detach && wait` racing past the run's own
    # end must still see that run's real outcome.
    run, _popen, _calls, _repo, _home, _logs = setup
    first = run("run", "one-arm", env={"SPE_EVAL_RUN_ID": "20261111T130000Z", "FAKE_RUN_SH_EXIT": "3"})
    assert first.returncode == 1, first.stderr
    p = run("wait")
    assert p.returncode == 1, p.stdout
    assert "baseline: gate refused" in p.stdout


def test_wait_for_an_arm_holder_with_no_report_exits_0(setup):
    # task 4 review, minor 7: no report is not evidence of a failed *run* when the holder was an
    # `arm` (which keeps none by design). A never-ready health server keeps the lock held for
    # SPE_EVAL_HEALTH_TIMEOUT so `wait` reliably calls in while it is still held.
    #
    # Whole-branch review, the flaky test: the fixture's default 0.3s timeout raced `wait`'s own
    # process start (a fresh Python interpreter importing yaml/validate/injections_schema before
    # it ever calls holder()), which under CPU load can take longer than 0.3s -- `wait` would then
    # find the lock already free and report "no run has happened yet" instead. Give the holder a
    # long hold (~4s, well past that startup cost even under load) and `wait` a bounded timeout
    # above it (10s), so the real race is between "wait sees the run in progress" and a generous
    # deadline, not between two near-equal durations.
    run, popen, _calls, _repo, home, _logs = setup
    unhealthy = _HealthServer(503, b'{"status": "starting"}')
    try:
        holder = popen("arm", "one-arm", "baseline",
                       env={"SPE_EVAL_HEALTH_URL": unhealthy.url, "SPE_EVAL_HEALTH_TIMEOUT": "4"})
        try:
            wait_until_locked(home)
            p = run("wait", "--timeout", "10")
            assert p.returncode == 0, p.stdout
            assert "no report found" in p.stdout
        finally:
            holder.communicate(timeout=10)
    finally:
        unhealthy.close()


def test_runs_ordering_and_json_fields(setup):
    run, _popen, _calls, _repo, _home, _logs = setup
    first = run("run", "one-arm", env={"SPE_EVAL_RUN_ID": "20261110T170000Z"})
    assert first.returncode == 0, first.stderr
    second = run("run", "one-arm", env={"SPE_EVAL_RUN_ID": "20261110T180000Z"})
    assert second.returncode == 0, second.stderr

    p = run("runs", "--json")
    assert p.returncode == 0, p.stderr
    entries = json.loads(p.stdout)
    assert [e["run"] for e in entries] == ["20261110T180000Z", "20261110T170000Z"]  # newest first
    assert entries[0]["experiment"] == "one-arm"
    assert entries[0]["arms"]["baseline"]["state"] == "ok"
    assert entries[0]["arms"]["baseline"]["model"] == "anthropic:claude-haiku-5-5"  # decision 22


def test_runs_text_output_with_none_yet(setup):
    run, _popen, _calls, _repo, _home, _logs = setup
    p = run("runs")
    assert p.returncode == 0, p.stderr
    assert "none yet" in p.stdout
