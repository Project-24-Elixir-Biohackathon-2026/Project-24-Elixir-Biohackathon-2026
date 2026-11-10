"""roles/repo's spe_local_values (the vars persisted for local re-apply, group_vars/all.yml's
*Vars persisted*): every spe_local_vars name resolved, and a fixture's spe_inject_* switch with no
group_vars default of its own defaults to false instead of failing the build (task 4 fix round 1).

Reads the task's own `vars:` mapping out of roles/repo/tasks/main.yml, instead of duplicating its Jinja
here, so this test tracks the source and cannot silently drift from it.
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
TASK_NAME = "Instance vars for local re-apply (instances/local.yml in the clone, git-ignored)"


def task_vars() -> dict:
    tasks = yaml.safe_load((ANSIBLE / "roles" / "repo" / "tasks" / "main.yml").read_text())
    task = next(t for t in tasks if t.get("name") == TASK_NAME)
    return task["vars"]


def run(tmp_path, overrides):
    out = tmp_path / "out"
    out.mkdir()
    play = [{
        "hosts": "localhost", "connection": "local", "gather_facts": False,
        "tasks": [
            {"name": "resolve", "ansible.builtin.set_fact": {"spe_local_values": "{{ spe_local_values }}"},
             "vars": task_vars()},
            {"name": "dump", "ansible.builtin.copy": {
                "content": "{{ spe_local_values | to_nice_json }}\n", "dest": str(out / "local_values.json")}},
        ],
    }]
    (tmp_path / "play.yml").write_text(yaml.safe_dump(play, sort_keys=False))
    (tmp_path / "extra.json").write_text(json.dumps({
        "spe_catalog_dir": str(ANSIBLE / "catalog"), "spe_instance": "x1", **overrides}))
    env = {**os.environ, "ANSIBLE_LOCALHOST_WARNING": "False"}
    p = subprocess.run(["ansible-playbook", "-i", "localhost,", str(tmp_path / "play.yml"),
                        "-e", f"@{ANSIBLE / 'inventory' / 'group_vars' / 'all.yml'}",
                        "-e", f"@{tmp_path / 'extra.json'}"], env=env, capture_output=True, text=True)
    assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-2000:]
    return json.loads((out / "local_values.json").read_text())


def test_every_spe_local_vars_name_resolves(tmp_path):
    values = run(tmp_path, {})
    assert values["spe_instance"] == "x1"
    assert values["spe_inject_trs_description"] is False
    assert values["spe_inject_drs_description"] is False
    assert values["spe_inject_workflow_comment"] is False


def test_an_undefined_name_in_spe_local_vars_extra_still_fails_the_build(tmp_path):
    # A misspelt (or otherwise undefined) non-switch name must still fail loudly: only the
    # fixture switches get a default=false (review finding: default=false had come to cover
    # every persisted name, so a typo in spe_local_vars_extra was silently written as false).
    out = tmp_path / "out"
    out.mkdir()
    play = [{
        "hosts": "localhost", "connection": "local", "gather_facts": False,
        "tasks": [
            {"name": "resolve", "ansible.builtin.set_fact": {"spe_local_values": "{{ spe_local_values }}"},
             "vars": task_vars()},
        ],
    }]
    (tmp_path / "play.yml").write_text(yaml.safe_dump(play, sort_keys=False))
    (tmp_path / "extra.json").write_text(json.dumps({
        "spe_catalog_dir": str(ANSIBLE / "catalog"), "spe_instance": "x1",
        "spe_local_vars_extra": ["spe_local_vars_extra_typo_undefined"]}))
    env = {**os.environ, "ANSIBLE_LOCALHOST_WARNING": "False"}
    p = subprocess.run(["ansible-playbook", "-i", "localhost,", str(tmp_path / "play.yml"),
                        "-e", f"@{ANSIBLE / 'inventory' / 'group_vars' / 'all.yml'}",
                        "-e", f"@{tmp_path / 'extra.json'}"], env=env, capture_output=True, text=True)
    assert p.returncode != 0, p.stdout[-2000:] + p.stderr[-2000:]
    assert "spe_local_vars_extra_typo_undefined" in p.stdout + p.stderr


def test_a_fixture_switch_with_no_group_vars_default_is_false_not_a_build_failure(tmp_path):
    # A new catalogue fixture naming a switch nobody declared a default for yet (bug found in review:
    # query('vars', *names) without a default errors on the first undefined name).
    fixtures = json.loads((ANSIBLE / "catalog" / "injections" / "fixtures.json").read_text())["fixtures"]
    fixtures = fixtures + [{**fixtures[0], "id": "new-fixture", "switch": "spe_inject_new_undefined"}]
    values = run(tmp_path, {"spe_injection_fixtures": fixtures, "spe_inject_drs_description": True})
    assert values["spe_inject_new_undefined"] is False
    # The real switches still resolve to what was actually passed, unaffected by the synthetic one.
    assert values["spe_inject_drs_description"] is True
    assert values["spe_inject_trs_description"] is False
