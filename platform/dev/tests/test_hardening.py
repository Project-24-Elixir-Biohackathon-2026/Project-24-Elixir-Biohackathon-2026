"""roles/handoff hardening.json: switches from group_vars, level = leading switches on, the repo's commit."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ANSIBLE = Path(__file__).resolve().parents[2] / "ansible"
pytestmark = pytest.mark.skipif(shutil.which("ansible-playbook") is None, reason="needs ansible-playbook")
PLAY = """- hosts: localhost
  connection: local
  gather_facts: false
  tasks:
    - ansible.builtin.include_role: {name: handoff, tasks_from: hardening}
"""
OFF = {"spe_harden_trs_readonly": False, "spe_harden_data_tiers": [], "spe_harden_egress": False,
       "spe_agent_tool_surface": "shell", "spe_harden_airlock": False}


def build(tmp_path, overrides):
    out = tmp_path / "out"
    out.mkdir()
    (tmp_path / "play.yml").write_text(PLAY)
    (tmp_path / "extra.json").write_text(json.dumps({
        "spe_instance": "t-01", "spe_output_dir": str(out), "spe_frontends": ["agui"],
        "spe_agent_model_provider": "openai_compatible", "spe_agent_model": "test-model",
        # hardening.yml reads the injection fixtures catalogue; playbook_dir here is tmp_path, not ansible/,
        # so spe_catalog_dir's own default (relative to playbook_dir) would miss it.
        "spe_catalog_dir": str(ANSIBLE / "catalog"), **overrides}))
    env = {**os.environ, "ANSIBLE_ROLES_PATH": str(ANSIBLE / "roles"), "ANSIBLE_LOCALHOST_WARNING": "False"}
    p = subprocess.run(["ansible-playbook", "-i", "localhost,", str(tmp_path / "play.yml"),
                        "-e", f"@{ANSIBLE / 'inventory' / 'group_vars' / 'all.yml'}",
                        "-e", f"@{tmp_path / 'extra.json'}"], env=env, capture_output=True, text=True)
    assert p.returncode == 0, p.stdout[-2000:]
    return json.loads((out / "hardening.json").read_text())


@pytest.mark.parametrize("overrides,level", [
    ({}, 0), ({"spe_harden_trs_readonly": True}, 1),
    ({"spe_harden_trs_readonly": True, "spe_harden_data_tiers": ["ref", "genomes"]}, 2),
    ({"spe_harden_data_tiers": ["ref"]}, 0), ({"spe_harden_egress": True}, 0),
    ({"spe_harden_trs_readonly": True, "spe_harden_data_tiers": ["ref", "genomes"], "spe_harden_egress": True,
      "spe_agent_tool_surface": "typed", "spe_harden_airlock": True}, 5)])
def test_hardening_json(tmp_path, overrides, level):
    rec = build(tmp_path, overrides)
    head = subprocess.run(["git", "-C", str(ANSIBLE), "rev-parse", "HEAD"], capture_output=True, text=True).stdout
    assert rec == {"schema_version": 1, "instance": "t-01", "level": level, "switches": {**OFF, **overrides},
                   "frontend": "agui", "model_provider": "openai_compatible", "model": "test-model",
                   "commit": head.strip(), "restore_seconds": None, "injections": False}


def test_injections_all_on(tmp_path):
    # The spe_inject_* switches (group_vars, off by default: the clean condition, spec part 06) set together.
    on = {k: True for k in ("spe_inject_trs_description", "spe_inject_drs_description",
                            "spe_inject_workflow_comment")}
    assert build(tmp_path, on)["injections"] is True


def test_injections_mixed(tmp_path):
    # One switch on, the others off: neither ladder condition; check_hardening refuses it (spec part 06).
    assert build(tmp_path, {"spe_inject_trs_description": True})["injections"] == "mixed"
