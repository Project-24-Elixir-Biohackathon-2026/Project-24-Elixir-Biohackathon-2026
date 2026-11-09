"""Spec part 02, Hand-off and Acceptance checks: the injections.json schema, on synthetic manifests."""
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

import handoff
import injections_schema
from conftest import manifest

HERE = Path(__file__).resolve().parents[1]
ALL = ("registry-preflight", "drs-integrity", "workflow-preflight")


def test_a_complete_manifest_is_valid(repo_root):
    assert injections_schema.validate(manifest(*ALL), repo_root) == []


def test_an_empty_manifest_is_valid(repo_root):
    assert injections_schema.validate(manifest(), repo_root) == []


def broken(change):
    m = manifest(*ALL)
    change(m)
    return m


@pytest.mark.parametrize("change,error", [
    (lambda m: m.update(schema_version="1"), "schema_version"),
    (lambda m: m.update(schema_version=True), "schema_version"),
    (lambda m: m.update(seed="x"), "unknown top-level"),
    (lambda m: m.update(injections={}), "array"),
    (lambda m: m["injections"].append(copy.deepcopy(m["injections"][0])), "duplicate id"),
    (lambda m: m["injections"][0].update(id="new-fixture"), "unknown id"),
    (lambda m: m["injections"][0].pop("disclosure"), "missing disclosure"),
    (lambda m: m["injections"][0].update(token="x"), "unknown fields token"),
    (lambda m: m["injections"][0].update(action="read-file"), "invalid action"),
    (lambda m: m["injections"][0].update(surface="drs-description"), "surface must be"),
    (lambda m: m["injections"][1].update(surface="wiki-page"), "unknown surface"),
    (lambda m: m["injections"][0].update(switch="spe_inject_drs_description"), "switch must be"),
    (lambda m: m["injections"][0].update(canary_file="sensitive/registry/other.csv"), "different files"),
    (lambda m: m["injections"][1].update(disclosure="first-five-lines"), "disclosure must be whole-file"),
    (lambda m: m["injections"][0]["location"].pop("tool_id"), "location must hold"),
    (lambda m: m["injections"][2]["location"].update(version=""), "location must hold"),
    (lambda m: m["injections"][0]["location"].update(field="name"), "location.field"),
    (lambda m: m["injections"][0].update(payload_sha256="ABC"), "64 lowercase hex"),
    (lambda m: m["injections"][0].update(payload_sha256="0" * 64), "does not match"),
    (lambda m: m["injections"][0].update(payload_file="/etc/passwd"), "payload_file must be"),
    (lambda m: m["injections"][0].update(id=7), "non-empty strings"),
])
def test_invalid_manifests_are_rejected(repo_root, change, error):
    errors = injections_schema.validate(broken(change), repo_root)
    assert any(error in e for e in errors), errors


def test_a_changed_payload_file_is_rejected(repo_root):
    (repo_root / "platform/ansible/catalog/injections/drs-integrity.txt").write_text("other text\n")
    errors = injections_schema.validate(manifest(*ALL), repo_root)
    assert errors == ["injections[1] (drs-integrity): payload_sha256 does not match "
                      "platform/ansible/catalog/injections/drs-integrity.txt"]


def test_a_missing_payload_file_is_rejected_not_an_exception(repo_root):
    # Carried from task 2 review: load_injections must raise ManifestError before
    # metrics.injection_followed ever reads the payload file, never let OSError escape here.
    (repo_root / "platform/ansible/catalog/injections/drs-integrity.txt").unlink()
    errors = injections_schema.validate(manifest(*ALL), repo_root)
    assert any("not found" in e for e in errors), errors


def test_an_empty_payload_file_is_rejected(repo_root):
    # Carried from task 2 review: an empty payload file must not validate even when its
    # payload_sha256 is set to match the empty file's hash (metrics._exposures would otherwise
    # treat an empty fingerprint as "found" in every tool result).
    path = repo_root / "platform/ansible/catalog/injections/drs-integrity.txt"
    path.write_text("")
    m = manifest(*ALL)
    for entry in m["injections"]:
        if entry["id"] == "drs-integrity":
            entry["payload_sha256"] = hashlib.sha256(b"").hexdigest()
    errors = injections_schema.validate(m, repo_root)
    assert any("empty" in e for e in errors), errors


def test_cli(tmp_path, repo_root):
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text(json.dumps(manifest(*ALL)))
    bad.write_text(json.dumps(broken(lambda m: m["injections"][0].update(action="x"))))
    run = lambda p: subprocess.run([sys.executable, str(HERE / "injections_schema.py"), str(p), str(repo_root)],
                                   capture_output=True, text=True)
    assert run(good).returncode == 0
    result = run(bad)
    assert result.returncode == 1
    assert "invalid action" in result.stderr


def test_load_injections_validates(handoff_dir):
    (handoff_dir / "injections.json").write_text(json.dumps(broken(lambda m: m["injections"][0].update(action="x"))))
    with pytest.raises(handoff.ManifestError, match="invalid action"):
        handoff.load_injections(handoff_dir)


def test_load_injections_needs_a_file_canary_for_each_target(handoff_dir):
    record = json.loads((handoff_dir / "canaries.json").read_text())
    record["tokens"] = [t for t in record["tokens"] if t["file"] != "sensitive/secret/research_DO_NOT_LEAK"]
    (handoff_dir / "canaries.json").write_text(json.dumps(record))
    with pytest.raises(handoff.ManifestError, match="drs-integrity targets sensitive/secret/research_DO_NOT_LEAK"):
        handoff.load_injections(handoff_dir)
