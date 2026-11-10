"""The ladder experiments tie to the controller-side ladder (experiments spec, 06-ladder-as-example.md).

For each ladder-l<N>, the Ansible values its two arms assemble -- the parameter-derived values, its
`vars`, its arm's mitigations' `on`, and its injections' switches, all true -- equal the corresponding
`platform/ansible/instances/L<n>.example.yml`'s values, for the keys both set (those files are
cumulative overlays, so compared on their own keys, not the whole build). `spe_agent_model*` is
excluded: the model is the portal's, not the experiment's.
"""
import json
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
EXPERIMENTS = REPO / "experiments"
MITIGATIONS = REPO / "mitigations"
INSTANCES = REPO / "platform/ansible/instances"
FIXTURES = REPO / "platform/ansible/catalog/injections/fixtures.json"

# Experiment parameter -> Ansible name, for the parameters an L<n>.example.yml file could also set
# (canaries expand to one spe_canary_<type> key per type instead, handled separately).
PARAMETER_ANSIBLE_NAMES = {
    "samples": "spe_samples",
    "tiers": "spe_tiers",
    "workflows": "spe_workflows",
    "flavor": "spe_flavor",
    "smoke_test": "spe_run_smoke_test",
}


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def mitigation_on(mitigation_id: str) -> dict:
    return load_yaml(MITIGATIONS / f"{mitigation_id}.yml").get("on") or {}


def injection_switches() -> dict:
    fixtures = json.loads(FIXTURES.read_text())["fixtures"]
    return {f["id"]: f["switch"] for f in fixtures}


def ansible_values(experiment: dict, mitigation_ids: set[str]) -> dict:
    """The Ansible values one arm (its mitigation set) of this experiment assembles."""
    params = experiment["parameters"]
    values: dict = {}
    for key, name in PARAMETER_ANSIBLE_NAMES.items():
        if key in params:
            values[name] = params[key]
    for canary in params.get("canaries") or []:
        values[f"spe_canary_{canary}"] = True
    values.update(experiment.get("vars") or {})
    for mitigation_id in mitigation_ids:
        values.update(mitigation_on(mitigation_id))
    switches = injection_switches()
    for injection_id in experiment["experiment"].get("injections") or []:
        values[switches[injection_id]] = True
    return values


def assert_matches_l_file(values: dict, l_file: Path) -> None:
    l_values = load_yaml(l_file)
    common = {k for k in l_values if k in values and not k.startswith("spe_agent_model")}
    assert common, f"no key both this arm and {l_file.name} set"
    for key in common:
        assert values[key] == l_values[key], (
            f"{key}: the experiment's arm gives {values[key]!r}, {l_file.name} gives {l_values[key]!r}"
        )


def ladder_experiment(n: int) -> dict:
    return load_yaml(EXPERIMENTS / f"ladder-l{n}.yml")


@pytest.mark.parametrize("n", [1, 2, 3])
def test_baseline_arm_matches_the_level_below(n):
    experiment = ladder_experiment(n)
    base = set(experiment["experiment"]["base"])
    assert_matches_l_file(ansible_values(experiment, base), INSTANCES / f"L{n - 1}.example.yml")


@pytest.mark.parametrize("n", [1, 2, 3])
def test_mitigated_arm_matches_its_own_level(n):
    experiment = ladder_experiment(n)
    base = set(experiment["experiment"]["base"])
    mitigation = experiment["experiment"]["mitigation"]
    assert_matches_l_file(ansible_values(experiment, base | {mitigation}), INSTANCES / f"L{n}.example.yml")


def test_ladder_l0_baseline_matches_l0():
    experiment = ladder_experiment(0)
    base = set(experiment["experiment"]["base"])
    assert experiment["experiment"]["mitigation"] is None  # one arm only
    assert_matches_l_file(ansible_values(experiment, base), INSTANCES / "L0.example.yml")
