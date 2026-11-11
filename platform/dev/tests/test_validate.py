"""Paths and mitigations as files, checked by validate.py (decisions 2, 4).

Fixture tests mutate a tmp-dir copy of the real paths/ or mitigations/ directory, so a change
to the repo's own files is exercised the same way a participant's would be.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
VALIDATE = REPO / "validate.py"
GROUP_VARS_PATH = REPO / "platform/ansible/inventory/group_vars/all.yml"
PROBES_DIR = REPO / "platform/promptfoo-evals/probes"
EXPERIMENTS_MAIN_TF = REPO / "platform/coder/experiments-template/main.tf"

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


def real_threat_ids() -> set[str]:
    entries, problems = validate.validate_catalog(REPO / "threats", validate.load_vocabulary(REPO / "vocabulary.yaml"))
    assert not problems, problems
    return {e.meta["id"] for e in entries}


def real_mitigations_by_id() -> dict:
    mitigations, problems = validate.validate_mitigations_catalog(
        REPO / "mitigations", real_path_ids(), real_probe_ids(), real_group_vars()
    )
    assert not problems, problems
    return {m.meta["id"]: m.meta for m in mitigations}


def real_fixtures() -> list[dict]:
    return validate.load_fixtures(REPO / "platform/ansible/catalog/injections/fixtures.json")


def real_test_ids() -> set[str]:
    return validate.test_ids_from(REPO / "platform/promptfoo-evals/tests")


def real_reserved_vars() -> set[str]:
    return validate.experiment_reserved_ansible_names(real_canary_types())


def validate_experiments(d: Path, mitigations: dict | None = None):
    return validate.validate_experiments_catalog(
        d, real_threat_ids(), real_path_ids(), mitigations if mitigations is not None else real_mitigations_by_id(),
        real_fixtures(), real_test_ids(), real_reserved_vars(),
    )


def write_experiment(tmp_path: Path, text: str, name: str = "test-experiment.yml") -> Path:
    d = tmp_path / "experiments"
    d.mkdir(exist_ok=True)
    (d / name).write_text(text)
    return d


# A valid experiment: base L1, mitigation under test L2, one real injection, no own tests.
GOOD_EXPERIMENT = """
name: Test experiment
description: A fixture experiment for validate.py's tests.
parameters:
  experiment: test-experiment
  mitigations: [L1]
  samples: [HG002]
  tiers: [ref]
  workflows: [wes-drs-smoke]
  canaries: [flag_file]
  flavor: de.NBI mini
  smoke_test: true
experiment:
  threat: TM-001
  paths: [P2]
  mitigation: L2
  base: [L1]
  injections: [registry-preflight]
  tests: []
vars:
  spe_eval_sink: true
"""


def test_cli_validates_the_repos_files():
    res = subprocess.run([sys.executable, str(VALIDATE)], cwd=REPO, capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr
    assert res.stdout.strip().startswith("OK:")
    assert "paths" in res.stdout and "mitigations" in res.stdout and "experiments" in res.stdout


def test_four_ladder_experiments_pass():
    entries, problems = validate_experiments(REPO / "experiments")
    assert not problems, problems
    assert {e.path.stem for e in entries} == {"ladder-l0", "ladder-l1", "ladder-l2", "ladder-l3"}


def test_absent_experiments_dir_is_fine(tmp_path):
    entries, problems = validate_experiments(tmp_path / "no-such-dir")
    assert entries == [] and problems == []


def test_a_good_experiment_passes(tmp_path):
    # Named ladder-l0.yml: the catalog-level check below requires it whenever the directory
    # holds anything at all, and this is the one test that asserts zero problems.
    d = write_experiment(
        tmp_path, GOOD_EXPERIMENT.replace("experiment: test-experiment", "experiment: ladder-l0"),
        name="ladder-l0.yml",
    )
    entries, problems = validate_experiments(d)
    assert not problems, problems
    assert [e.path.stem for e in entries] == ["ladder-l0"]


def coder_parameter_names() -> set[str]:
    return set(re.findall(r'data "coder_parameter" "(\w+)"', EXPERIMENTS_MAIN_TF.read_text()))


def test_known_parameter_keys_match_the_templates_coder_parameters():
    # validate.py keeps its own EXPERIMENT_PARAMETER_ANSIBLE_NAMES list rather than parsing main.tf
    # at run time, and this test keeps the two from drifting. 'seed' is the one coder_parameter the
    # template defines that is never a key of an experiment's 'parameters' (the seed is secret, so
    # it is never set from an experiment file): excluded here, not from the dict.
    assert coder_parameter_names() - {"seed"} == set(validate.EXPERIMENT_PARAMETER_ANSIBLE_NAMES)


def test_experiment_unknown_parameters_key_fails(tmp_path):
    d = write_experiment(tmp_path, GOOD_EXPERIMENT.replace(
        "  smoke_test: true\n", "  smoke_test: true\n  bogus: 1\n"
    ))
    _, problems = validate_experiments(d)
    assert any("bogus" in p and "parameters key" in p for p in problems), problems


def test_two_experiments_with_the_same_name_fail(tmp_path):
    a = GOOD_EXPERIMENT.replace("experiment: test-experiment", "experiment: test-experiment-a")
    b = GOOD_EXPERIMENT.replace("experiment: test-experiment", "experiment: test-experiment-b")
    d = write_experiment(tmp_path, a, name="test-experiment-a.yml")
    write_experiment(tmp_path, b, name="test-experiment-b.yml")
    _, problems = validate_experiments(d)
    assert any("duplicate name" in p and "Test experiment" in p for p in problems), problems


def test_two_experiments_with_default_true_fail(tmp_path):
    a = (GOOD_EXPERIMENT.replace("experiment: test-experiment", "experiment: test-experiment-a")
         .replace("name: Test experiment\n", "name: Test experiment A\ndefault: true\n"))
    b = (GOOD_EXPERIMENT.replace("experiment: test-experiment", "experiment: test-experiment-b")
         .replace("name: Test experiment\n", "name: Test experiment B\ndefault: true\n"))
    d = write_experiment(tmp_path, a, name="test-experiment-a.yml")
    write_experiment(tmp_path, b, name="test-experiment-b.yml")
    _, problems = validate_experiments(d)
    assert any("more than one experiment has 'default: true'" in p for p in problems), problems


def test_ladder_l0_missing_fails_when_the_dir_has_any_file(tmp_path):
    d = write_experiment(tmp_path, GOOD_EXPERIMENT)  # written as test-experiment.yml, not ladder-l0.yml
    _, problems = validate_experiments(d)
    assert any("ladder-l0.yml" in p and "missing" in p for p in problems), problems


def test_experiment_vars_key_set_by_spe_instance_fails(tmp_path):
    d = write_experiment(tmp_path, GOOD_EXPERIMENT.replace(
        "vars:\n  spe_eval_sink: true", "vars:\n  spe_instance: foo"
    ))
    _, problems = validate_experiments(d)
    assert any("spe_instance" in p for p in problems), problems


def test_experiment_vars_key_set_by_spe_coder_identity_key_fails(tmp_path):
    d = write_experiment(tmp_path, GOOD_EXPERIMENT.replace(
        "vars:\n  spe_eval_sink: true", "vars:\n  spe_coder_owner: foo"
    ))
    _, problems = validate_experiments(d)
    assert any("spe_coder_owner" in p for p in problems), problems


def test_experiment_parameters_experiment_mismatch_fails(tmp_path):
    d = write_experiment(tmp_path, GOOD_EXPERIMENT.replace("experiment: test-experiment", "experiment: wrong-name"))
    _, problems = validate_experiments(d)
    assert any("parameters.experiment" in p and "wrong-name" in p for p in problems), problems


def test_experiment_unknown_threat_fails(tmp_path):
    d = write_experiment(tmp_path, GOOD_EXPERIMENT.replace("threat: TM-001", "threat: TM-999"))
    _, problems = validate_experiments(d)
    assert any("TM-999" in p for p in problems), problems


def test_experiment_unknown_path_fails(tmp_path):
    d = write_experiment(tmp_path, GOOD_EXPERIMENT.replace("paths: [P2]", "paths: [P99]"))
    _, problems = validate_experiments(d)
    assert any("P99" in p for p in problems), problems


def test_experiment_planned_mitigation_under_test_fails(tmp_path):
    # L4 exists but is status: planned (no on/off yet).
    d = write_experiment(tmp_path, GOOD_EXPERIMENT.replace("mitigation: L2", "mitigation: L4"))
    _, problems = validate_experiments(d)
    assert any("L4" in p and "planned" in p for p in problems), problems


def test_experiment_unknown_mitigation_in_base_fails(tmp_path):
    d = write_experiment(tmp_path, GOOD_EXPERIMENT.replace("base: [L1]", "base: [not-a-mitigation]"))
    _, problems = validate_experiments(d)
    assert any("not-a-mitigation" in p for p in problems), problems


def test_experiment_mitigation_under_test_also_in_base_fails(tmp_path):
    d = write_experiment(tmp_path, GOOD_EXPERIMENT.replace("mitigation: L2", "mitigation: L1"))
    _, problems = validate_experiments(d)
    assert any("L1" in p and "also in base" in p for p in problems), problems


def test_experiment_parameters_mitigations_mismatch_base_fails(tmp_path):
    d = write_experiment(tmp_path, GOOD_EXPERIMENT.replace("mitigations: [L1]", "mitigations: []"))
    _, problems = validate_experiments(d)
    assert any("parameters.mitigations" in p for p in problems), problems


def test_experiment_unknown_injection_fails(tmp_path):
    d = write_experiment(tmp_path, GOOD_EXPERIMENT.replace(
        "injections: [registry-preflight]", "injections: [not-a-fixture]"
    ))
    _, problems = validate_experiments(d)
    assert any("not-a-fixture" in p for p in problems), problems


def test_experiment_unknown_test_fails(tmp_path):
    d = write_experiment(tmp_path, GOOD_EXPERIMENT.replace("tests: []", "tests: [not-a-test]"))
    _, problems = validate_experiments(d)
    assert any("not-a-test" in p for p in problems), problems


def test_experiment_requires_not_satisfied_in_arm_fails(tmp_path):
    mitigations = dict(real_mitigations_by_id())
    mitigations["L2"] = {**mitigations["L2"], "requires": ["L3"]}
    d = write_experiment(tmp_path, GOOD_EXPERIMENT)
    _, problems = validate_experiments(d, mitigations)
    assert any("requires" in p and "L3" in p for p in problems), problems


def test_experiment_conflicts_violated_in_arm_fails(tmp_path):
    mitigations = dict(real_mitigations_by_id())
    mitigations["L2"] = {**mitigations["L2"], "conflicts": ["L1"]}
    d = write_experiment(tmp_path, GOOD_EXPERIMENT)
    _, problems = validate_experiments(d, mitigations)
    assert any("conflicts" in p and "L1" in p for p in problems), problems


def test_experiment_vars_key_set_by_injection_switch_fails(tmp_path):
    d = write_experiment(tmp_path, GOOD_EXPERIMENT.replace(
        "vars:\n  spe_eval_sink: true", "vars:\n  spe_inject_trs_description: true"
    ))
    _, problems = validate_experiments(d)
    assert any("spe_inject_trs_description" in p and "registry-preflight" in p for p in problems), problems


def test_experiment_vars_key_set_by_mitigation_on_fails(tmp_path):
    d = write_experiment(tmp_path, GOOD_EXPERIMENT.replace(
        "vars:\n  spe_eval_sink: true", "vars:\n  spe_harden_trs_readonly: true"
    ))
    _, problems = validate_experiments(d)
    assert any("spe_harden_trs_readonly" in p and "L1" in p for p in problems), problems


def test_experiment_vars_key_set_by_parameter_fails(tmp_path):
    d = write_experiment(tmp_path, GOOD_EXPERIMENT.replace(
        "vars:\n  spe_eval_sink: true", "vars:\n  spe_samples: [HG002]"
    ))
    _, problems = validate_experiments(d)
    assert any("spe_samples" in p for p in problems), problems


def test_experiment_vars_key_set_by_an_unselected_mitigations_on_fails(tmp_path):
    # GOOD_EXPERIMENT selects L1 (base) and L2 (mitigation under test), never L3: its 'on' key
    # is still refused, named by L3's id (spec 01: one place per value, selected or not).
    d = write_experiment(tmp_path, GOOD_EXPERIMENT.replace(
        "vars:\n  spe_eval_sink: true", "vars:\n  spe_harden_egress: true"
    ))
    _, problems = validate_experiments(d)
    assert any("spe_harden_egress" in p and "L3" in p for p in problems), problems


def test_experiment_vars_key_set_by_an_unlisted_injections_switch_fails(tmp_path):
    # GOOD_EXPERIMENT lists only registry-preflight: drs-integrity's switch is still refused,
    # named by its id (spec 01: "an injection's switch is set only through injections").
    d = write_experiment(tmp_path, GOOD_EXPERIMENT.replace(
        "vars:\n  spe_eval_sink: true", "vars:\n  spe_inject_drs_description: true"
    ))
    _, problems = validate_experiments(d)
    assert any("spe_inject_drs_description" in p and "drs-integrity" in p for p in problems), problems


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


def test_three_mitigations_setting_the_same_on_key_name_all_three(tmp_path):
    """Naming only the first-seen owner of a contested key would leave a third mitigation setting
    it unnamed alongside the second -- the message must name all three files involved, not just
    two."""
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
    (mitigations_dir / "trs-guard-2.yml").write_text(
        "id: trs-guard-2\n"
        "name: A second mitigation also setting L1's key, for the test\n"
        "description: Sets the same Ansible key as L1 and trs-guard.\n"
        "closes: []\n"
        '"on": {spe_harden_trs_readonly: true}\n'
        '"off": {spe_harden_trs_readonly: false}\n'
    )
    _, problems = validate.validate_mitigations_catalog(
        mitigations_dir, real_path_ids(), real_probe_ids(), real_group_vars()
    )
    overlap = [p for p in problems if "spe_harden_trs_readonly" in p and "L1.yml" in p
               and "trs-guard.yml" in p and "trs-guard-2.yml" in p]
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


def test_mitigation_lowercase_ladder_id_fails(tmp_path):
    """`l1` has the same shape as the reserved ladder id `L1`, lowercased: confusable enough with
    it that it is refused rather than accepted as an ordinary kebab-case id."""
    mitigations_dir = tmp_path / "mitigations"
    shutil.copytree(REPO / "mitigations", mitigations_dir)
    (mitigations_dir / "l1.yml").write_text(
        "id: l1\n"
        "name: Lowercase ladder-shaped id\n"
        "description: An id shaped like a reserved ladder level, lowercased.\n"
        "closes: []\n"
        "conflicts: [L1]\n"
        '"on": {spe_harden_trs_readonly: true}\n'
        '"off": {spe_harden_trs_readonly: false}\n'
    )
    _, problems = validate.validate_mitigations_catalog(
        mitigations_dir, real_path_ids(), real_probe_ids(), real_group_vars()
    )
    assert any("l1.yml" in p and "l1" in p and "L<n>" in p for p in problems), problems


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
