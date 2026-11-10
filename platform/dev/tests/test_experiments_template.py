"""The spe-experiments Coder template, planned with OpenTofu (experiments spec, decisions 4 and 6).

The coder provider plans with no Coder server: a parameter's value comes from the environment
(`CODER_PARAMETER_<sha256 hex of its name>`, a list as a JSON string), and the plan's JSON gives the
`build_vars` output (ansible_vars without the Coder identity, token and init script, which are unknown
at plan time) and, in `prior_state`, the parameters' options and the presets. Skipped unless `SPE_TOFU`
names a tofu/terraform binary or one is on PATH; `TF_PLUGIN_CACHE_DIR` is passed through when set.
"""
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
TEMPLATE = REPO / "platform/coder/experiments-template"
SPE_TEMPLATE = REPO / "platform/coder/template"
ASSEMBLE = TEMPLATE / "assemble.sh"
# What assemble.sh copies in (git-ignored), never taken from a developer's working copy.
ASSEMBLED = ("experiments", "mitigations", "catalog", "run-ansible.sh")
# Fixed, so the seed derived from the workspace id is the same in every plan.
WORKSPACE_ID = "0e4b1c56-0000-4000-8000-000000000001"
# spe's ansible_vars keys that only the Coder deployment knows; build_vars leaves them out.
CODER_IDENTITY_KEYS = {"spe_coder_owner", "spe_coder_owner_email", "spe_coder_workspace",
                       "spe_coder_workspace_id", "spe_coder_agent_token", "spe_coder_init_script"}

TOFU = os.environ.get("SPE_TOFU") or shutil.which("tofu") or shutil.which("terraform")
needs_tofu = pytest.mark.skipif(not TOFU, reason="no OpenTofu/Terraform: set SPE_TOFU or put tofu on PATH")


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def preset_parameters(stem: str) -> dict:
    return load_yaml(REPO / "experiments" / f"{stem}.yml")["parameters"]


def parameter_value(value) -> str:
    """A parameter value as the coder provider reads it from the environment (and as a preset sets it)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    return json.dumps(value)


def tofu(cwd: Path, *args: str, env: dict | None = None) -> str:
    p = subprocess.run([TOFU, *args, "-no-color"], cwd=cwd, env=env or os.environ.copy(),
                       capture_output=True, text=True)
    assert p.returncode == 0, f"tofu {args[0]} failed:\n{p.stdout}\n{p.stderr}"
    return p.stdout


def plan(cwd: Path, parameters: dict | None = None) -> dict:
    env = os.environ.copy()
    env.update(CODER_WORKSPACE_TRANSITION="start", CODER_WORKSPACE_ID=WORKSPACE_ID)
    for name, value in (parameters or {}).items():
        env["CODER_PARAMETER_" + hashlib.sha256(name.encode()).hexdigest()] = parameter_value(value)
    tofu(cwd, "plan", "-input=false", "-out", "plan.bin", env=env)
    return json.loads(tofu(cwd, "show", "-json", "plan.bin"))


def build_vars(plan_json: dict) -> dict:
    return plan_json["planned_values"]["outputs"]["build_vars"]["value"]


def data_sources(plan_json: dict, kind: str) -> list[dict]:
    return [r["values"] for r in plan_json["prior_state"]["values"]["root_module"]["resources"]
            if r["mode"] == "data" and r["type"] == kind]


def parameter(plan_json: dict, name: str) -> dict:
    return next(p for p in data_sources(plan_json, "coder_parameter") if p["name"] == name)


def copy_template(dst: Path) -> Path:
    shutil.copytree(TEMPLATE, dst, ignore=shutil.ignore_patterns(".terraform*", "*.tfstate*", "plan.bin",
                                                                  *ASSEMBLED))
    subprocess.run([ASSEMBLE, REPO, dst], check=True)
    return dst


@pytest.fixture(scope="session")
def template(tmp_path_factory) -> Path:
    """The assembled template, initialised once per session."""
    path = copy_template(tmp_path_factory.mktemp("tf") / "experiments-template")
    tofu(path, "init", "-input=false")
    return path


@pytest.fixture(scope="session")
def ladder_l0_plan(template) -> dict:
    return plan(template, preset_parameters("ladder-l0"))


@pytest.fixture
def template_copy(template, tmp_path) -> Path:
    """A copy of the initialised template that a test may add files to (shares the providers)."""
    path = tmp_path / "experiments-template"
    shutil.copytree(template, path, ignore=shutil.ignore_patterns(".terraform", "plan.bin"))
    (path / ".terraform").symlink_to(template / ".terraform")
    return path


def test_assemble_replaces_stale_copies(tmp_path):
    (tmp_path / "experiments").mkdir()
    (tmp_path / "experiments/deleted.yml").write_text("name: gone\n")
    subprocess.run([ASSEMBLE, REPO, tmp_path], check=True)
    assert sorted(p.name for p in (tmp_path / "experiments").iterdir()) == \
        sorted(p.name for p in (REPO / "experiments").glob("*.yml"))
    assert sorted(p.name for p in (tmp_path / "mitigations").iterdir()) == \
        sorted(p.name for p in (REPO / "mitigations").glob("*.yml"))
    assert (tmp_path / "catalog/injections/fixtures.json").read_text() == \
        (REPO / "platform/ansible/catalog/injections/fixtures.json").read_text()
    assert os.access(tmp_path / "run-ansible.sh", os.X_OK)


@needs_tofu
def test_ladder_l2_preset_builds_the_baseline_arm(template):
    v = build_vars(plan(template, preset_parameters("ladder-l2")))
    assert v["spe_harden_trs_readonly"] is True
    assert "spe_harden_data_tiers" not in v   # L2 is under test, not in the base: its Ansible default ([])
    assert v["spe_frontends"] == ["agui"]
    for fixture in json.loads((REPO / "platform/ansible/catalog/injections/fixtures.json").read_text())["fixtures"]:
        assert v[fixture["switch"]] is True
    assert (v["spe_experiments"], v["spe_experiment"], v["spe_mitigations"]) == (True, "ladder-l2", ["L1"])
    assert {"spe_experiments", "spe_experiment", "spe_mitigations", "spe_harden_trs_readonly",
            "spe_frontends", "spe_eval_sink", "spe_agui_smoke"} <= set(v["spe_local_vars_extra"])


@needs_tofu
def test_selected_mitigations_merge_their_on_values(template):
    v = build_vars(plan(template, {**preset_parameters("ladder-l2"), "mitigations": ["L1", "L2"]}))
    assert v["spe_harden_trs_readonly"] is True
    assert v["spe_harden_data_tiers"] == ["ref", "genomes"]
    assert v["spe_mitigations"] == ["L1", "L2"]


@needs_tofu
def test_no_mitigation_builds_spe_values(ladder_l0_plan, tmp_path):
    """Decision 4: with no mitigation selected, no mitigation key is set, and every key spe's
    template builds has the same value as a build from spe with the same form."""
    v = build_vars(ladder_l0_plan)
    assert not [k for k in v if k.startswith(("spe_harden_", "spe_mitigate_"))]

    spe = tmp_path / "spe"
    shutil.copytree(SPE_TEMPLATE, spe, ignore=shutil.ignore_patterns(".terraform*", "*.tfstate*"))
    # An extra output only in this copy: spe's ansible_vars without what is unknown at plan time.
    (spe / "zz_test_output.tf").write_text(
        'output "build_vars" {\n'
        '  value = { for k, v in local.ansible_vars : k => v\n'
        '    if !contains(["spe_coder_agent_token", "spe_coder_init_script"], k) }\n'
        '}\n')
    tofu(spe, "init", "-input=false")
    spe_vars = build_vars(plan(spe, preset_parameters("ladder-l0")))
    shared = {k: spe_vars[k] for k in spe_vars if k not in CODER_IDENTITY_KEYS}
    assert {k: v[k] for k in shared} == shared


@needs_tofu
def test_form_defaults_are_ladder_l0s_preset(template, ladder_l0_plan):
    assert build_vars(plan(template)) == build_vars(ladder_l0_plan)


@needs_tofu
def test_presets_are_the_experiment_files(ladder_l0_plan):
    presets = {p["name"]: p for p in data_sources(ladder_l0_plan, "coder_workspace_preset")}
    experiments = {p.stem: load_yaml(p) for p in (REPO / "experiments").glob("*.yml")}
    assert set(presets) == {e["name"] for e in experiments.values()}
    l1 = presets[experiments["ladder-l1"]["name"]]
    assert l1["description"].endswith(" — TM-001 via P2 · mitigation L1: TRS read-only")
    assert len(l1["description"].encode()) <= 128   # the coder provider's limit, in bytes
    assert l1["parameters"]["mitigations"] == "[]"
    assert presets[experiments["ladder-l0"]["name"]]["description"].endswith(
        " — TM-001 via P1, P2, P3, P4 · no mitigation (one arm)")
    assert [p["name"] for p in presets.values() if p["default"]] == [experiments["ladder-l0"]["name"]]


@needs_tofu
def test_planned_mitigations_are_not_offered(ladder_l0_plan):
    offered = {o["value"] for o in parameter(ladder_l0_plan, "mitigations")["option"]}
    planned = {p.stem for p in (REPO / "mitigations").glob("*.yml") if load_yaml(p).get("status") == "planned"}
    assert planned and not offered & planned
    assert {"L1", "L2", "L3"} <= offered


@needs_tofu
def test_new_files_appear_with_no_main_tf_change(template_copy):
    (template_copy / "mitigations/x.yml").write_text(yaml.safe_dump({
        "id": "x", "name": "Test guard X", "description": "A test mitigation.", "closes": [],
        "on": {"spe_mitigate_x": True}, "off": {"spe_mitigate_x": False}, "probes": []}))
    y = load_yaml(template_copy / "experiments/ladder-l0.yml")
    y.update(name="Test experiment Y", description="Does X stop it?", default=False)
    y["parameters"].update(experiment="y", mitigations=[])
    y["experiment"].update(threat="TM-002", paths=["P1", "P3"], mitigation="x", base=[],
                           injections=["drs-integrity"])
    (template_copy / "experiments/y.yml").write_text(yaml.safe_dump(y, sort_keys=False))

    result = plan(template_copy, {**y["parameters"], "mitigations": ["x"]})
    assert {"value": "x", "name": "Test guard X"}.items() <= next(
        o for o in parameter(result, "mitigations")["option"] if o["value"] == "x").items()
    assert "y" in {o["value"] for o in parameter(result, "experiment")["option"]}
    preset = next(p for p in data_sources(result, "coder_workspace_preset") if p["name"] == "Test experiment Y")
    assert preset["description"] == "Does X stop it? — TM-002 via P1, P3 · mitigation x: Test guard X"

    v = build_vars(result)
    assert (v["spe_experiment"], v["spe_mitigate_x"]) == ("y", True)
    assert "spe_mitigate_x" in v["spe_local_vars_extra"]
    # Only the experiment's own injections are switched on; the others are not set at all.
    assert v["spe_inject_drs_description"] is True
    assert "spe_inject_trs_description" not in v and "spe_inject_workflow_comment" not in v


@needs_tofu
def test_a_description_past_tofus_range_limit_is_still_cut_to_fit(template_copy):
    # range() refuses more than 1024 elements, so the candidates must not be one per character.
    y = load_yaml(template_copy / "experiments/ladder-l0.yml")
    y.update(name="Test experiment Long", description="word " * 400, default=False)
    y["parameters"]["experiment"] = "long"
    (template_copy / "experiments/long.yml").write_text(yaml.safe_dump(y, sort_keys=False))

    result = plan(template_copy)
    preset = next(p for p in data_sources(result, "coder_workspace_preset") if p["name"] == "Test experiment Long")
    assert preset["description"].startswith("word word") and "… — TM-001" in preset["description"]
    assert len(preset["description"].encode()) <= 128
