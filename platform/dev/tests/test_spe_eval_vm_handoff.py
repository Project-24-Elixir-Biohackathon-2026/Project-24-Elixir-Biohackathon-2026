"""roles/handoff/tasks/vm_handoff.yml's own hosts.yml (experiments spec part 03, *The hand-off on
the VM*, task 5 review item 5): `provision: existing`, `ssh_target: localhost` (so
`isolation.vm_runner` runs commands locally), and `agent_api_key_file` under `spe_eval_dir`.

Loads just the "Connection details" task by name (as test_create_mitigations.py does for
create.yml's own pre_task), rather than running the whole file: the other tasks there write the
canary record, DRS/TRS inventories, the certificate and the injection manifest, none of which this
task's own `vars:` block (self-contained: it reads only its own input vars, no registered fact of
an earlier task) needs, and three of them (the handoff/, reports/, promptfoo/ directory tasks) set
`group: "{{ spe_ssh_user }}"`, which only resolves on a real workspace user account.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ANSIBLE = Path(__file__).resolve().parents[2] / "ansible"
pytestmark = pytest.mark.skipif(shutil.which("ansible-playbook") is None, reason="needs ansible-playbook")
TASK_NAME = "Connection details (VM copy; provision existing, ssh_target localhost -- isolation.vm_runner runs locally)"


def connection_details_task() -> dict:
    tasks = yaml.safe_load((ANSIBLE / "roles" / "handoff" / "tasks" / "vm_handoff.yml").read_text())
    return next(t for t in tasks if t.get("name") == TASK_NAME)


def build(tmp_path, **overrides):
    spe_eval_dir = tmp_path / "spe-eval"
    (spe_eval_dir / "handoff").mkdir(parents=True)
    play = [{"hosts": "localhost", "connection": "local", "gather_facts": False,
             "tasks": [connection_details_task()]}]
    (tmp_path / "play.yml").write_text(yaml.safe_dump(play, sort_keys=False))
    extra = {
        "spe_instance": "t-01", "spe_eval_dir": str(spe_eval_dir), "spe_ssh_user": os.environ.get("USER", "agentvm"),
        "spe_api_host": "10.0.2.245", "spe_frontends": ["agui"], "spe_agui_agent_port": 8100,
        "spe_weskit_image": "weskit:test", "spe_agent_model_provider": "openai_compatible",
        "spe_agent_model": "test-model", **overrides,
    }
    (tmp_path / "extra.json").write_text(json.dumps(extra))
    env = {**os.environ, "ANSIBLE_ROLES_PATH": str(ANSIBLE / "roles"), "ANSIBLE_LOCALHOST_WARNING": "False"}
    p = subprocess.run(["ansible-playbook", "-i", "localhost,", str(tmp_path / "play.yml"),
                        "-e", f"@{tmp_path / 'extra.json'}"],
                       env=env, cwd=ANSIBLE, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-2000:]
    return yaml.safe_load((spe_eval_dir / "handoff" / "hosts.yml").read_text())


def test_provision_existing_and_ssh_target_localhost(tmp_path):
    hosts = build(tmp_path)
    assert hosts["provision"] == "existing"
    assert hosts["ssh_target"] == "localhost"


def test_agent_api_key_file_under_spe_eval_dir(tmp_path):
    spe_eval_dir = tmp_path / "spe-eval"
    hosts = build(tmp_path)
    assert hosts["agent_api_key_file"] == f"{spe_eval_dir}/handoff/agent_api_key"


def test_agent_url_from_the_agui_port(tmp_path):
    hosts = build(tmp_path, spe_agui_agent_port=18100)
    assert hosts["agent_url"] == "http://127.0.0.1:18100/agent"


def test_no_agui_keys_without_the_agui_frontend(tmp_path):
    hosts = build(tmp_path, spe_frontends=["openwebui"])
    assert "agent_url" not in hosts
    assert "agent_api_key_file" not in hosts
    assert "agent_model" not in hosts


def test_instance_and_api_host_carried_through(tmp_path):
    hosts = build(tmp_path, spe_instance="experiment-run-7", spe_api_host="203.0.113.5")
    assert hosts["instance"] == "experiment-run-7"
    assert hosts["api_host"] == "203.0.113.5"
    assert hosts["server"] == "experiment-run-7-api"
