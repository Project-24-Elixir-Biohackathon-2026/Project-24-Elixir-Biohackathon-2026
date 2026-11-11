"""roles/handoff/tasks/vm_hardening.yml: hardening.json rewritten on the VM itself for whichever
arm `spe-apply all` just applied (experiments spec part 03, decision 9 / R4, task 5 review item 5).
Mirrors test_hardening.py's own build() for hardening.yml, the file this one's content mirrors;
the differences this test checks: the destination (`{{ spe_eval_dir }}/handoff/hardening.json`,
not `spe_output_dir`), the commit read from `spe_repo_dir` (the VM's own clone) rather than
`role_path`, and that this file runs standing alone (no spe_output_dir, no other role's facts).
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ANSIBLE = Path(__file__).resolve().parents[2] / "ansible"
REPO_ROOT = ANSIBLE.parent.parent
pytestmark = pytest.mark.skipif(shutil.which("ansible-playbook") is None, reason="needs ansible-playbook")
PLAY = """- hosts: localhost
  connection: local
  gather_facts: false
  tasks:
    - ansible.builtin.include_role: {name: handoff, tasks_from: vm_hardening}
"""
OFF = {"spe_harden_trs_readonly": False, "spe_harden_data_tiers": [], "spe_harden_egress": False,
       "spe_agent_tool_surface": "shell", "spe_harden_airlock": False}


def build(tmp_path, overrides):
    spe_eval_dir = tmp_path / "spe-eval"
    (spe_eval_dir / "handoff").mkdir(parents=True)  # vm_handoff.yml's own job at build time
    (tmp_path / "play.yml").write_text(PLAY)
    (tmp_path / "extra.json").write_text(json.dumps({
        "spe_instance": "t-01", "spe_eval_dir": str(spe_eval_dir), "spe_frontends": ["agui"],
        "spe_repo_dir": str(REPO_ROOT), "spe_ssh_user": os.environ.get("USER", "agentvm"),
        "spe_agent_model_provider": "openai_compatible", "spe_agent_model": "test-model",
        "spe_catalog_dir": str(ANSIBLE / "catalog"), **overrides}))
    env = {**os.environ, "ANSIBLE_ROLES_PATH": str(ANSIBLE / "roles"), "ANSIBLE_LOCALHOST_WARNING": "False"}
    p = subprocess.run(["ansible-playbook", "-i", "localhost,", str(tmp_path / "play.yml"),
                        "-e", f"@{ANSIBLE / 'inventory' / 'group_vars' / 'all.yml'}",
                        "-e", f"@{tmp_path / 'extra.json'}"],
                       env=env, cwd=ANSIBLE, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-2000:]
    return json.loads((spe_eval_dir / "handoff" / "hardening.json").read_text())


@pytest.mark.parametrize("overrides,level", [
    ({}, 0), ({"spe_harden_trs_readonly": True}, 1),
    ({"spe_harden_trs_readonly": True, "spe_harden_data_tiers": ["ref", "genomes"]}, 2),
    ({"spe_harden_data_tiers": ["ref"]}, 0), ({"spe_harden_egress": True}, 0),
    ({"spe_harden_trs_readonly": True, "spe_harden_data_tiers": ["ref", "genomes"], "spe_harden_egress": True,
      "spe_agent_tool_surface": "typed", "spe_harden_airlock": True}, 5),
    ({"spe_mitigations": ["L1", "L2"]}, 0), ({"spe_experiment": "ladder-l2"}, 0),
    ({"spe_harden_trs_readonly": True, "spe_mitigations": ["L1"], "spe_experiment": "ladder-l1"}, 1)])
def test_vm_hardening_json(tmp_path, overrides, level):
    rec = build(tmp_path, overrides)
    head = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout
    switch_overrides = {k: v for k, v in overrides.items() if k in OFF}
    assert rec == {"schema_version": 1, "instance": "t-01", "level": level, "switches": {**OFF, **switch_overrides},
                   "frontend": "agui", "model_provider": "openai_compatible", "model": "test-model",
                   "commit": head.strip(), "restore_seconds": None, "injections": False,
                   "mitigations": overrides.get("spe_mitigations", []), "experiment": overrides.get("spe_experiment", "")}


def test_vm_hardening_injections_all_on(tmp_path):
    on = {k: True for k in ("spe_inject_trs_description", "spe_inject_drs_description",
                            "spe_inject_workflow_comment")}
    assert build(tmp_path, on)["injections"] is True


def test_vm_hardening_injections_mixed(tmp_path):
    assert build(tmp_path, {"spe_inject_trs_description": True})["injections"] == "mixed"


def test_vm_hardening_writes_under_spe_eval_dir_not_spe_output_dir(tmp_path):
    # Decision 9 / R4: this is the VM's own copy, never the controller's spe_output_dir (which
    # this file never even reads).
    spe_eval_dir = tmp_path / "spe-eval"
    (spe_eval_dir / "handoff").mkdir(parents=True)
    (tmp_path / "play.yml").write_text(PLAY)
    (tmp_path / "extra.json").write_text(json.dumps({
        "spe_instance": "t-01", "spe_eval_dir": str(spe_eval_dir), "spe_frontends": ["agui"],
        "spe_repo_dir": str(REPO_ROOT), "spe_ssh_user": os.environ.get("USER", "agentvm"),
        "spe_agent_model_provider": "openai_compatible", "spe_agent_model": "test-model",
        "spe_catalog_dir": str(ANSIBLE / "catalog"), "spe_output_dir": str(tmp_path / "unused-output-dir")}))
    env = {**os.environ, "ANSIBLE_ROLES_PATH": str(ANSIBLE / "roles"), "ANSIBLE_LOCALHOST_WARNING": "False"}
    p = subprocess.run(["ansible-playbook", "-i", "localhost,", str(tmp_path / "play.yml"),
                        "-e", f"@{ANSIBLE / 'inventory' / 'group_vars' / 'all.yml'}",
                        "-e", f"@{tmp_path / 'extra.json'}"],
                       env=env, cwd=ANSIBLE, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-2000:]
    assert (spe_eval_dir / "handoff" / "hardening.json").is_file()
    assert not (tmp_path / "unused-output-dir").exists()
