"""Paths and mitigations as files, checked by validate.py (decisions 2, 4).

Fixture tests mutate a tmp-dir copy of the real paths/ or mitigations/ directory, so a change
to the repo's own files is exercised the same way a participant's would be.
"""
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
VALIDATE = REPO / "validate.py"
GROUP_VARS_PATH = REPO / "platform/ansible/inventory/group_vars/all.yml"
PROBES_DIR = REPO / "platform/promptfoo-evals/probes"

sys.path.insert(0, str(REPO))
import validate  # noqa: E402  (the repository's validator)


def real_group_vars() -> dict:
    return validate.load_group_vars(GROUP_VARS_PATH)


def real_canary_types() -> set[str]:
    return validate.canary_types_from(real_group_vars())


def real_probe_ids() -> set[str]:
    return {p.stem for p in PROBES_DIR.glob("*.sh")}


def real_path_ids() -> set[str]:
    entries, problems = validate.validate_paths_catalog(REPO / "paths", real_canary_types())
    assert not problems, problems
    return {e.meta["id"] for e in entries}


def test_cli_validates_the_repos_files():
    res = subprocess.run([sys.executable, str(VALIDATE)], cwd=REPO, capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr
    assert res.stdout.strip().startswith("OK:")
    assert "paths" in res.stdout and "mitigations" in res.stdout


def test_path_missing_frontmatter_key_fails(tmp_path):
    paths_dir = tmp_path / "paths"
    shutil.copytree(REPO / "paths", paths_dir)
    (paths_dir / "P2-agent-written-code.md").write_text(
        "---\n"
        "id: P2\n"
        "name: Agent-written workflow code\n"
        "reaches: [flag_file]\n"
        "---\n"
        "# P2: Agent-written workflow code\n"
        "## Route\n"
        "## Shown by\n"
    )
    _, problems = validate.validate_paths_catalog(paths_dir, real_canary_types())
    assert any("P2-agent-written-code.md" in p and "description" in p for p in problems), problems


def test_path_bad_reaches_value_fails(tmp_path):
    paths_dir = tmp_path / "paths"
    shutil.copytree(REPO / "paths", paths_dir)
    (paths_dir / "P3-installed-workflows.md").write_text(
        "---\n"
        "id: P3\n"
        "name: Installed workflows on sensitive inputs\n"
        "description: An installed workflow run on a sensitive input.\n"
        "reaches: [vcf_variants, not_a_canary_type]\n"
        "---\n"
        "# P3: Installed workflows on sensitive inputs\n"
        "## Route\n"
        "## Shown by\n"
    )
    _, problems = validate.validate_paths_catalog(paths_dir, real_canary_types())
    assert any("not_a_canary_type" in p for p in problems), problems


def test_mitigation_off_mismatch_fails(tmp_path):
    mitigations_dir = tmp_path / "mitigations"
    shutil.copytree(REPO / "mitigations", mitigations_dir)
    (mitigations_dir / "L1.yml").write_text(
        "id: L1\n"
        "name: TRS read-only\n"
        "description: TRS GET-only at Traefik.\n"
        "closes: [P2]\n"
        '"on": {spe_harden_trs_readonly: true}\n'
        '"off": {spe_harden_trs_readonly: true}\n'  # wrong: the group_vars default is false
    )
    _, problems = validate.validate_mitigations_catalog(
        mitigations_dir, real_path_ids(), real_probe_ids(), real_group_vars()
    )
    assert any("L1.yml" in p and "spe_harden_trs_readonly" in p for p in problems), problems


def test_two_mitigations_setting_the_same_on_key_fail_naming_both_files(tmp_path):
    mitigations_dir = tmp_path / "mitigations"
    shutil.copytree(REPO / "mitigations", mitigations_dir)
    (mitigations_dir / "trs-guard.yml").write_text(
        "id: trs-guard\n"
        "name: TRS guard (duplicate of L1's switch, for the test)\n"
        "description: Sets the same Ansible key as L1.\n"
        "closes: []\n"
        '"on": {spe_harden_trs_readonly: true}\n'
        '"off": {spe_harden_trs_readonly: false}\n'
    )
    _, problems = validate.validate_mitigations_catalog(
        mitigations_dir, real_path_ids(), real_probe_ids(), real_group_vars()
    )
    overlap = [p for p in problems if "spe_harden_trs_readonly" in p and "L1.yml" in p and "trs-guard.yml" in p]
    assert overlap, problems


def test_two_mitigations_setting_the_same_on_key_pass_when_conflicts_declares_the_pair(tmp_path):
    mitigations_dir = tmp_path / "mitigations"
    shutil.copytree(REPO / "mitigations", mitigations_dir)
    (mitigations_dir / "trs-guard.yml").write_text(
        "id: trs-guard\n"
        "name: TRS guard (duplicate of L1's switch, for the test)\n"
        "description: Sets the same Ansible key as L1, but declares the conflict.\n"
        "closes: []\n"
        "conflicts: [L1]\n"
        '"on": {spe_harden_trs_readonly: true}\n'
        '"off": {spe_harden_trs_readonly: false}\n'
    )
    _, problems = validate.validate_mitigations_catalog(
        mitigations_dir, real_path_ids(), real_probe_ids(), real_group_vars()
    )
    overlap = [p for p in problems if "spe_harden_trs_readonly" in p and "catalog:" in p]
    assert not overlap, problems


def test_mitigation_closing_an_unknown_path_fails(tmp_path):
    mitigations_dir = tmp_path / "mitigations"
    shutil.copytree(REPO / "mitigations", mitigations_dir)
    (mitigations_dir / "L2.yml").write_text(
        "id: L2\n"
        "name: Data tiers\n"
        "description: Workflow containers mount only the listed tiers.\n"
        "closes: [P99]\n"
        '"on": {spe_harden_data_tiers: [ref, genomes]}\n'
        '"off": {spe_harden_data_tiers: []}\n'
    )
    _, problems = validate.validate_mitigations_catalog(
        mitigations_dir, real_path_ids(), real_probe_ids(), real_group_vars()
    )
    assert any("L2.yml" in p and "P99" in p for p in problems), problems


def test_planned_mitigation_with_on_fails(tmp_path):
    mitigations_dir = tmp_path / "mitigations"
    shutil.copytree(REPO / "mitigations", mitigations_dir)
    (mitigations_dir / "L4.yml").write_text(
        "id: L4\n"
        "name: Typed tool surface\n"
        "description: Typed GA4GH tools replace the shell.\n"
        "closes: []\n"
        "status: planned\n"
        '"on": {spe_agent_tool_surface: typed}\n'
    )
    _, problems = validate.validate_mitigations_catalog(
        mitigations_dir, real_path_ids(), real_probe_ids(), real_group_vars()
    )
    assert any("L4.yml" in p and "planned" in p for p in problems), problems
