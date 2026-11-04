"""archive.yml's AG-UI export (roles/run_archive/tasks/export.yml) against a stub docker.

A live archive copies from the running services and stops nothing; only the final archive (destroy.yml,
spe_archive_final: true) stops chat-ui, then the agent, checks that both exited 0, and starts nothing again.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

ANSIBLE = Path(__file__).resolve().parents[2] / "ansible"

pytestmark = pytest.mark.skipif(shutil.which("ansible-playbook") is None, reason="ansible-playbook not installed")

STUB = r'''#!/usr/bin/env python3
# A docker stand-in: logs each call as one JSON line, answers what export.yml asks.
import json, os, sys
from pathlib import Path

args = sys.argv[1:]
with open(os.environ["STUB_LOG"], "a") as log:
    log.write(json.dumps(args) + "\n")
if args[:1] == ["compose"]:
    rest = args[1:]
    while rest[:1] and rest[0] in ("-p", "-f"):
        rest = rest[2:]
    sub = rest[0] if rest else ""
    if sub == "ps" and "-q" in rest:
        print("" if os.environ.get("STUB_NO_CHAT_UI") else "c0ffee")
    elif sub == "ps" and "--services" in rest:
        print("chat-ui\nagent")
    elif sub == "ps" and "{{.Image}}" in rest:
        print("spe-frontend-chat-ui:0123abcd")
    elif sub == "ps" and "--format" in rest:
        print(f"chat-ui {os.environ.get('STUB_CHAT_UI_EXIT', '0')}\nagent 0")
    elif sub == "cp":
        src, dest = rest[-2], Path(rest[-1])
        if src.endswith("runs.jsonl"):
            if os.environ.get("STUB_NO_RUN_LOG"):
                sys.stderr.write("Error response from daemon: Could not find the file /var/lib/spe-agent/runs.jsonl\n")
                sys.exit(1)
            dest.write_text('{"run_id": "r1", "status": "completed"}\n')
        else:
            if os.environ.get("STUB_CP_FAILS"):
                sys.stderr.write("Error response from daemon: no space left on device\n")
                sys.exit(1)
            dest.mkdir(parents=True)
            (dest / "00000000-0000-4000-8000-000000000000.jsonl").write_text('{"type": "created"}\n')
elif args[:1] == ["run"]:
    for i, a in enumerate(args[:-1]):
        if a == "-v" and args[i + 1].split(":")[1] == "/out":
            out = Path(args[i + 1].split(":")[0], "bundle.json")
            out.write_text(json.dumps({"spe_archive_mode": args[-1], "chats": [], "tags": [], "notes": []}))
'''

PLAY = """- hosts: localhost
  gather_facts: false
  tasks:
    - ansible.builtin.include_role:
        name: run_archive
        tasks_from: export
"""


def verbs(calls: list[list[str]]) -> list[str]:
    """Each docker call as one string, `docker compose -p … -f …` shortened to `compose`."""
    out = []
    for call in calls:
        if call[:1] == ["compose"]:
            rest = call[1:]
            while rest[:1] and rest[0] in ("-p", "-f"):
                rest = rest[2:]
            out.append(" ".join(["compose", *rest]))
        else:
            out.append(" ".join(call))
    return out


def export(tmp_path: Path, final: bool, **stub_env: str):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(STUB)
    docker.chmod(0o755)
    (tmp_path / "frontend").mkdir()
    out = tmp_path / "out"
    out.mkdir()
    play = tmp_path / "play.yml"
    play.write_text(PLAY)
    log = tmp_path / "docker.log"
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "STUB_LOG": str(log),
           "ANSIBLE_ROLES_PATH": str(ANSIBLE / "roles"), "ANSIBLE_NOCOLOR": "1", **stub_env}
    proc = subprocess.run(
        ["ansible-playbook", str(play), "-e", json.dumps({"spe_frontends": ["agui"]}), "-e", f"spe_frontend_dir={tmp_path / 'frontend'}",
         "-e", f"spe_output_dir={out}", "-e", json.dumps({"spe_archive_final": final})],
        cwd=ANSIBLE, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)
    calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    return proc, verbs(calls), [c[-1] for c in calls if c[:1] == ["run"]], out


def bundle_names(out: Path) -> list[str]:
    with tarfile.open(out / "archive-bundle-agui.tar.gz") as tar:
        return tar.getnames()


def test_live_archive_copies_and_stops_nothing(tmp_path):
    proc, v, modes, out = export(tmp_path, final=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not [x for x in v if x.startswith(("compose stop", "compose start", "compose restart", "compose kill"))], v
    assert any(x.startswith("compose cp chat-ui:/data/sessions ") for x in v), v
    assert any(x.startswith("compose cp agent:/var/lib/spe-agent/runs.jsonl ") for x in v), v
    assert modes == ["live"], v
    names = bundle_names(out)
    assert any(n.endswith("agent-runs.jsonl") for n in names), names
    assert any("agui-journals/" in n and n.endswith(".jsonl") for n in names), names


def test_final_archive_stops_chat_ui_then_the_agent_and_starts_nothing(tmp_path):
    proc, v, modes, out = export(tmp_path, final=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert [x for x in v if x.startswith("compose stop")] == ["compose stop -t 30 chat-ui",
                                                              "compose stop -t 30 agent"], v
    assert not [x for x in v if x.startswith(("compose start", "compose restart", "compose up"))], v
    first_copy = next(i for i, x in enumerate(v) if x.startswith("compose cp"))
    assert v.index("compose stop -t 30 agent") < first_copy, v
    assert modes == ["final"], v
    assert (out / "archive-bundle-agui.tar.gz").is_file()


def test_final_archive_fails_when_a_service_did_not_exit_0(tmp_path):
    proc, v, modes, out = export(tmp_path, final=True, STUB_CHAT_UI_EXIT="1")
    assert proc.returncode != 0
    assert "Stopping did not end cleanly" in proc.stdout, proc.stdout
    assert not [x for x in v if x.startswith(("compose cp", "compose start", "compose restart"))], v
    assert modes == [] and not (out / "archive-bundle-agui.tar.gz").exists()


def test_a_failure_after_the_final_barrier_says_the_services_stay_stopped(tmp_path):
    proc, v, modes, out = export(tmp_path, final=True, STUB_CP_FAILS="1")
    assert proc.returncode != 0
    assert "the services stay stopped" in proc.stdout, proc.stdout
    assert "no space left on device" in proc.stdout, proc.stdout
    assert not [x for x in v if x.startswith(("compose start", "compose restart", "compose up"))], v
    assert modes == [] and not (out / "archive-bundle-agui.tar.gz").exists()


@pytest.mark.parametrize("final", [False, True])
def test_a_missing_chat_ui_container_fails_the_export(tmp_path, final):
    proc, v, modes, out = export(tmp_path, final=final, STUB_NO_CHAT_UI="1")
    assert proc.returncode != 0 and "The chat-ui container exists" in proc.stdout, proc.stdout
    assert not [x for x in v if x.startswith(("compose stop", "compose cp"))], v
    assert not (out / "archive-bundle-agui.tar.gz").exists()


def test_an_absent_run_log_is_allowed(tmp_path):
    proc, v, modes, out = export(tmp_path, final=False, STUB_NO_RUN_LOG="1")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not any(n.endswith("agent-runs.jsonl") for n in bundle_names(out))


def playbook(tmp_path: Path, name: str, *extra: str) -> subprocess.CompletedProcess:
    """A playbook for an instance that does not exist: nothing is archived or reset."""
    return subprocess.run(
        ["ansible-playbook", f"playbooks/{name}.yml", "-e", "spe_instance=spe-test-no-such-instance",
         "-e", "spe_provision=existing", "-e", f"spe_output_dir={tmp_path}", *extra],
        cwd=ANSIBLE, env={**os.environ, "ANSIBLE_NOCOLOR": "1"}, stdin=subprocess.DEVNULL,
        capture_output=True, text=True, timeout=300)


def test_archive_alone_is_live(tmp_path):
    proc = playbook(tmp_path, "archive")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "live: copied from the running services, nothing is stopped" in proc.stdout, proc.stdout


def test_destroy_refused_before_the_final_archive(tmp_path):
    proc = playbook(tmp_path, "destroy")
    # No spe_confirm_reset: refused before the archive, which would leave the services stopped.
    assert proc.returncode != 0 and "Confirmation given" in proc.stdout, proc.stdout
    assert "Archive mode" not in proc.stdout, proc.stdout


def test_destroy_runs_the_final_archive(tmp_path):
    (tmp_path / "hosts.yml").write_text(
        # .invalid never resolves: the reset play after the archive fails unreachable, touching nothing.
        "instance: spe-test-no-such-instance\nprovision: existing\nssh_target: spe-test.invalid\n")
    proc = playbook(tmp_path, "destroy", "-e", "spe_confirm_reset=spe-test-no-such-instance",
                    "-e", "spe_archive_skip=true")
    assert "final: chat-ui and the agent are stopped first and not started again" in proc.stdout, proc.stdout
    assert "UNREACHABLE" in proc.stdout, proc.stdout
