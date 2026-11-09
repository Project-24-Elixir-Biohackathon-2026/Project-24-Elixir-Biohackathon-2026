"""controls.yaml and package.json: no model, every probe once, serial, uncached; no Ansible role runs a probe."""
import json
from pathlib import Path

import yaml

import controls_asserts as ca

HERE = Path(__file__).resolve().parents[1]


def test_controls_yaml():
    cfg = yaml.safe_load((HERE / "controls.yaml").read_text())
    assert [p["id"] for p in cfg["providers"]] == ["file://controls_provider.py"]
    assert cfg["extensions"] == ["file://isolation.py:extension_hook"]
    assert cfg["evaluateOptions"]["maxConcurrency"] == 1
    probes = [t["vars"]["probe"] for t in cfg["tests"]]
    assert sorted(probes) == sorted(ca.PROBE_CONTROL) and len(set(probes)) == len(probes)
    assert probes.index("isolation-check") == probes.index("isolation-plant") + 1
    asserts = cfg["defaultTest"]["assert"]
    assert asserts == [{"type": "python", "value": "file://controls_asserts.py:probe_state"}]


def test_npm_scripts_uncached():
    scripts = json.loads((HERE / "package.json").read_text())["scripts"]
    assert "-c controls.yaml" in scripts["eval:controls"] and "-o reports/controls.json" in scripts["eval:controls"]
    assert "-c agent.yaml" in scripts["eval:agent"] and "-o reports/agent.json" in scripts["eval:agent"]
    assert all("--no-cache" in scripts[s] for s in ("eval:controls", "eval:agent"))


def test_no_role_runs_a_probe():
    roles = HERE.parent / "ansible" / "roles"
    assert not [p for p in roles.rglob("*") if p.is_file() and "probes/" in p.read_text(errors="ignore")]
