"""create.yml's pre_tasks: spe_mitigations checked against mitigations/<id>.yml before anything is
created (spec docs/specs/2026-11-10-experiments-design/02-coder-template.md, *Into Ansible*): an
unknown or planned id, an unmet `requires`, a `conflicts` pair both selected, and selected ladder
mitigations not contiguous from L1, are all refused; empty spe_mitigations (the default) reads no
file, so a build without spe_experiments is unchanged.

Loads the task from playbooks/create.yml by name (as test_repo_local_vars.py does for roles/repo),
instead of duplicating its Jinja here, so this test tracks the source and cannot silently drift
from it.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ANSIBLE = Path(__file__).resolve().parents[2] / "ansible"
REPO_ROOT = ANSIBLE.parent.parent
REAL_MITIGATIONS = REPO_ROOT / "mitigations"
pytestmark = pytest.mark.skipif(shutil.which("ansible-playbook") is None, reason="needs ansible-playbook")
TASK_NAME = "Mitigation selection checked before anything is created"


def mitigation_check_task() -> dict:
    play = yaml.safe_load((ANSIBLE / "playbooks" / "create.yml").read_text())
    pre_tasks = play[0]["pre_tasks"]
    return next(t for t in pre_tasks if t.get("name") == TASK_NAME)


def write_mitigation(dir: Path, mitigation_id: str, **fields) -> None:
    (dir / f"{mitigation_id}.yml").write_text(yaml.safe_dump({"id": mitigation_id, "name": mitigation_id,
                                                               "description": "d", "closes": [], **fields},
                                                              sort_keys=False))


def run(tmp_path: Path, mitigations_root: Path | None, spe_mitigations: list[str],
        play_dir: Path | None = None) -> subprocess.CompletedProcess:
    play = [{"hosts": "localhost", "connection": "local", "gather_facts": False, "pre_tasks": [mitigation_check_task()]}]
    play_dir = play_dir or tmp_path
    (play_dir / "play.yml").write_text(yaml.safe_dump(play, sort_keys=False))
    extra = {"spe_instance": "t-01", "spe_mitigations": spe_mitigations}
    if mitigations_root is not None:
        # Overrides the task's own vars entry (extra vars win precedence), as test_hardening.py
        # does for spe_catalog_dir: playbook_dir here is tmp_path, not platform/ansible/playbooks.
        extra["spe_mitigations_root"] = str(mitigations_root)
    (tmp_path / "extra.json").write_text(json.dumps(extra))
    env = {**os.environ, "ANSIBLE_LOCALHOST_WARNING": "False"}
    return subprocess.run(["ansible-playbook", "-i", "localhost,", str(play_dir / "play.yml"),
                           "-e", f"@{ANSIBLE / 'inventory' / 'group_vars' / 'all.yml'}",
                           "-e", f"@{tmp_path / 'extra.json'}"], env=env, capture_output=True, text=True)


def test_empty_spe_mitigations_reads_no_file(tmp_path):
    # A directory that does not exist: if the task read anything, it would fail to glob or parse.
    p = run(tmp_path, tmp_path / "does-not-exist", [])
    assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-2000:]


def test_known_non_planned_mitigations_pass(tmp_path):
    p = run(tmp_path, REAL_MITIGATIONS, ["L1", "L2"])
    assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-2000:]


def test_unknown_id_refused(tmp_path):
    p = run(tmp_path, REAL_MITIGATIONS, ["not-a-mitigation"])
    assert p.returncode != 0
    assert "unknown or planned" in p.stdout and "not-a-mitigation" in p.stdout


def test_planned_id_refused(tmp_path):
    p = run(tmp_path, REAL_MITIGATIONS, ["L4"])  # status: planned, mitigations/L4.yml
    assert p.returncode != 0
    assert "unknown or planned" in p.stdout and "L4" in p.stdout


def test_unmet_requires_refused(tmp_path):
    d = tmp_path / "mitigations"
    d.mkdir()
    write_mitigation(d, "a", **{"on": {"x": True}, "off": {"x": False}})
    write_mitigation(d, "b", requires=["a"], **{"on": {"y": True}, "off": {"y": False}})
    p = run(tmp_path, d, ["b"])
    assert p.returncode != 0
    assert "b requires a" in p.stdout


def test_met_requires_passes(tmp_path):
    d = tmp_path / "mitigations"
    d.mkdir()
    write_mitigation(d, "a", **{"on": {"x": True}, "off": {"x": False}})
    write_mitigation(d, "b", requires=["a"], **{"on": {"y": True}, "off": {"y": False}})
    p = run(tmp_path, d, ["a", "b"])
    assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-2000:]


def test_conflicting_pair_both_selected_refused(tmp_path):
    d = tmp_path / "mitigations"
    d.mkdir()
    write_mitigation(d, "a", conflicts=["b"], **{"on": {"x": True}, "off": {"x": False}})
    write_mitigation(d, "b", **{"on": {"y": True}, "off": {"y": False}})
    p = run(tmp_path, d, ["a", "b"])
    assert p.returncode != 0
    assert "a conflicts with b" in p.stdout


def test_conflicting_mitigation_not_selected_passes(tmp_path):
    d = tmp_path / "mitigations"
    d.mkdir()
    write_mitigation(d, "a", conflicts=["b"], **{"on": {"x": True}, "off": {"x": False}})
    write_mitigation(d, "b", **{"on": {"y": True}, "off": {"y": False}})
    p = run(tmp_path, d, ["a"])
    assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-2000:]


@pytest.mark.parametrize("selected", [["L2"], ["L1", "L3"]])
def test_non_contiguous_ladder_refused(tmp_path, selected):
    p = run(tmp_path, REAL_MITIGATIONS, selected)
    assert p.returncode != 0
    assert "non-contiguous" in p.stdout


def test_contiguous_ladder_passes(tmp_path):
    p = run(tmp_path, REAL_MITIGATIONS, ["L1", "L2"])
    assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-2000:]


def test_the_default_root_is_the_repositorys_mitigations(tmp_path):
    # No override: the task's own default, relative to playbook_dir, from a play at create.yml's
    # depth (platform/ansible/playbooks/) in a tree whose root holds the real mitigations.
    assert (ANSIBLE / "playbooks" / "create.yml").is_file()
    play_dir = tmp_path / "platform/ansible/playbooks"
    play_dir.mkdir(parents=True)
    (tmp_path / "mitigations").symlink_to(REAL_MITIGATIONS)
    p = run(tmp_path, None, ["L1"], play_dir)
    assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-2000:]
