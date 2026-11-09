"""agent.yaml and its catalogue: the wiring of metrics, isolation and assertions. No model, no instance."""
import json
import re
from pathlib import Path

import yaml

import asserts
import metrics

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
METRICS = {"canary.answer": "canary_answer", "canary.touched": "canary_touched", "canary.sent": "canary_sent",
           "canary.delivered": "canary_delivered", "injection.followed": "injection_followed", "key.leak": "key_leak"}
GROUPS = {"utility", "direct", "troubleshooting", "injection", "egress"}


def load(name):
    return yaml.safe_load((ROOT / name).read_text())


def catalogue():
    return [(f.stem, t) for f in sorted((ROOT / "tests").glob("*.yaml")) for t in yaml.safe_load(f.read_text())]


def test_agent_yaml_wires_the_six_metrics():
    cfg = load("agent.yaml")
    assert cfg["tests"] == "file://tests/*.yaml"
    assert cfg["evaluateOptions"]["maxConcurrency"] == 1
    assert cfg["extensions"] == load("controls.yaml")["extensions"]
    (provider,) = cfg["providers"]
    assert provider["id"] == "file://agui_provider.py" and provider["config"]["state_diff"] is True
    default = cfg["defaultTest"]["assert"]
    named = {a["metric"]: a["value"] for a in default if "metric" in a}
    assert named == {m: f"file://metrics.py:{fn}" for m, fn in METRICS.items()}
    values = [a["value"] for a in default]
    assert "file://asserts.py:no_tls_bypass" in values and not any("no_key_leak" in v for v in values)


def test_starter_config_and_script_are_gone():
    assert not (ROOT / "promptfooconfig.yaml").exists()
    scripts = json.loads((ROOT / "package.json").read_text())["scripts"]
    assert "eval" not in scripts and "-c agent.yaml" in scripts["eval:agent"]


def test_catalogue_groups_and_ids():
    tests = catalogue()
    assert len(tests) == 13 and {stem for stem, _ in tests} == GROUPS
    ids = [t["metadata"]["id"] for _, t in tests]
    assert len(ids) == len(set(ids)) and all(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", i) for i in ids)
    for stem, t in tests:
        md = t["metadata"]
        assert md["group"] == stem and t["description"] and t["vars"]["message"]
        assert md["threat"] is None or list((REPO / "threats").glob(f"{md['threat']}-*.md")), md["threat"]


def test_every_python_assert_names_a_real_function():
    modules = {"asserts.py": asserts, "metrics.py": metrics}
    for _, t in catalogue():
        for a in t.get("assert", []):
            m = re.fullmatch(r"file://(\w+\.py):(\w+)", a["value"])
            assert a["type"] == "python" and m and callable(getattr(modules[m[1]], m[2], None)), a["value"]


def test_utility_rows_have_a_deterministic_check_and_no_level():
    for _, t in catalogue():
        if t["metadata"]["group"] == "utility":
            assert t["assert"] and t["metadata"]["closed_by"] is None and t["metadata"]["path"] is None


def test_workflow_comment_row_requests_the_descriptor():
    (row,) = [t for _, t in catalogue() if t["metadata"]["id"] == "explain-descriptor"]
    assert "descriptor" in row["vars"]["message"] and row["metadata"]["group"] == "injection"
    assert "file://asserts.py:fetched_descriptor" in [a["value"] for a in row["assert"]]
