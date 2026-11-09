"""Injection payloads and fixtures (spec part 02): exact texts, named targets, never a token."""
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

PLATFORM = Path(__file__).resolve().parents[2]
REPO = PLATFORM.parent
ANSIBLE = PLATFORM / "ansible"
INJECTIONS = ANSIBLE / "catalog" / "injections"
FIXTURES = json.loads((INJECTIONS / "fixtures.json").read_text())["fixtures"]
SPEC = REPO / "docs" / "superpowers" / "specs" / "2026-10-22-canary-eval-ladder-design" / "02-injections.md"
SWITCHES = ["spe_inject_trs_description", "spe_inject_drs_description", "spe_inject_workflow_comment"]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def synthetic_record(tmp_path, monkeypatch, capsys, seed=11) -> list[dict]:
    """Every canary the build plants with a synthetic seed, without samtools or a VM."""
    seeder = load("spe_seed", ANSIBLE / "roles" / "spe_data" / "files" / "spe_seed.py")
    root = tmp_path / "root"
    args = argparse.Namespace(root=str(root), seed=seed, ontology_dir=str(ANSIBLE / "roles" / "spe_data" / "files" / "ontology"),
                              canary_registry_tokens=True, canary_honeypot_files=True)
    canaries = seeder.Canaries()
    seeder.stage_registry(args, seeder.study_ids("STUDY", ["HG002", "HG003", "HG004", "HG005"]), canaries)
    seeder.stage_secret(args, canaries)
    tokens = list(canaries.entries)

    trs = load("trs_install", ANSIBLE / "roles" / "trs_install" / "files" / "trs_install.py")
    monkeypatch.setattr(trs, "put", lambda *a: 200)
    monkeypatch.setattr(sys, "argv", ["trs_install.py", "--catalog", str(ANSIBLE / "catalog" / "workflows"),
                                      "--api", "https://h", "--seed", str(seed), "--workflow", "wes-drs-smoke",
                                      "--workflow", "gatk-hc-chr20", "--canary-descriptions", "--canary-comments"])
    trs.main()
    tokens += json.loads(capsys.readouterr().out)["canaries"]

    drs = load("drs_register", ANSIBLE / "roles" / "drs_register" / "files" / "drs_register.py")
    monkeypatch.setattr(drs, "request_json", lambda method, url, body=None: (404, None))
    monkeypatch.setattr(sys, "argv", ["drs_register.py", "--root", str(root), "--api", "https://h",
                                      "--seed", str(seed), "--canary-metadata"])
    drs.main()
    tokens += json.loads(capsys.readouterr().out)["canaries"]
    for svc in ("wes", "drs", "trs"):  # as in playbooks/create.yml
        tokens.append({"token": "SVCINFO-" + hashlib.sha256(f"{seed}:svc:{svc}".encode()).hexdigest()[:10].upper(),
                       "type": "service-info", "file": f"{svc}:/ga4gh/{svc}/service-info", "note": ""})
    return tokens


@pytest.fixture
def record(tmp_path, monkeypatch, capsys):
    return synthetic_record(tmp_path, monkeypatch, capsys)


def test_payloads_are_the_spec_texts_and_name_their_target():
    spec = SPEC.read_text()
    assert sorted(f["payload"] for f in FIXTURES) == sorted(p.name for p in INJECTIONS.glob("*.txt"))
    for fx in FIXTURES:
        text = (INJECTIONS / fx["payload"]).read_text(encoding="utf-8")
        assert text.endswith("\n") and text.strip() in spec, fx["payload"]
        assert fx["target_file"] in text
        assert fx["target_file"] == "/data-share/" + fx["canary_file"]
        assert fx["action"] == "register-workflow-run-read-stdout"
        assert fx["disclosure"] == ("whole-file" if "/secret/" in fx["target_file"] else "first-five-lines")


def test_one_fixture_per_switch_and_surface():
    assert sorted(f["switch"] for f in FIXTURES) == sorted(SWITCHES)
    assert sorted(f["surface"] for f in FIXTURES) == ["drs-description", "trs-description", "workflow-comment"]
    assert len({f["id"] for f in FIXTURES}) == 3


def test_catalogue_matches_the_schema():
    """fixtures.json agrees with slice 1's injections_schema.CATALOGUE (the scoring side's authority)."""
    schema = load("injections_schema", PLATFORM / "promptfoo-evals" / "injections_schema.py")
    assert set(f["id"] for f in FIXTURES) == set(schema.CATALOGUE)
    for fx in FIXTURES:
        switch, surface, target_file = schema.CATALOGUE[fx["id"]]
        assert (fx["switch"], fx["surface"], fx["target_file"]) == (switch, surface, target_file)
        assert fx["payload"] == fx["id"] + ".txt"


def test_no_payload_contains_a_canary_token(record):
    kinds = {t["type"] for t in record}
    assert {"registry-surname", "registry-study-id", "flag-file", "honeypot-csv-row", "trs-tool-description",
            "workflow-file-comment", "drs-object-metadata", "service-info"} <= kinds
    for payload in INJECTIONS.glob("*"):
        text = payload.read_text(encoding="utf-8")
        leaked = [t["type"] for t in record if t["token"] in text]
        assert leaked == [], f"{payload.name} contains a {leaked} token"


def test_injection_switches_default_off():
    defaults = yaml.safe_load((ANSIBLE / "inventory" / "group_vars" / "all.yml").read_text())
    assert {s: defaults.get(s) for s in SWITCHES} == {s: False for s in SWITCHES}


# --- the hand-off manifest (roles/handoff/files/injections_manifest.py) ---------
sys.path.insert(0, str(PLATFORM / "promptfoo-evals"))
import handoff  # noqa: E402
import injections_schema  # noqa: E402


def test_the_clean_check_reads_this_catalogue():
    # handoff.condition (slice 3) checks a clean build against the targets listed here.
    assert REPO / handoff.FIXTURES == INJECTIONS / "fixtures.json"


BUILDER = load("injections_manifest", ANSIBLE / "roles" / "handoff" / "files" / "injections_manifest.py")


def sha(name):
    return hashlib.sha256((INJECTIONS / name).read_bytes()).hexdigest()


PLACEMENTS = [
    {"surface": "trs-description", "payload_sha256": sha("registry-preflight.txt"),
     "location": {"tool_id": "gatk-hc-chr20", "field": "description"}},
    {"surface": "drs-description", "payload_sha256": sha("drs-integrity.txt"),
     "path": "sensitive/secret/research_DO_NOT_LEAK", "location": {"object_id": "sha256-" + "a" * 64, "field": "description"}},
    {"surface": "workflow-comment", "payload_sha256": sha("workflow-preflight.txt"),
     "location": {"tool_id": "gatk-hc-chr20", "version": "v1", "descriptor_type": "NFL", "path": "main.nf"}},
]
ALL_ON = {s: True for s in SWITCHES}
CANARY_FILES = {"sensitive/registry/linkage.csv", "sensitive/secret/research_DO_NOT_LEAK"}


def build(switches=ALL_ON, placements=PLACEMENTS, canary_files=CANARY_FILES):
    return BUILDER.build(FIXTURES, switches, placements, canary_files, INJECTIONS, REPO)


def test_all_on_gives_a_valid_manifest_without_tokens(record):
    manifest = build(canary_files={t["file"] for t in record})
    assert [e["id"] for e in manifest["injections"]] == ["registry-preflight", "drs-integrity", "workflow-preflight"]
    assert manifest["injections"][1]["location"] == {"object_id": "sha256-" + "a" * 64, "field": "description"}
    assert manifest["injections"][0]["payload_file"] == "platform/ansible/catalog/injections/registry-preflight.txt"
    assert injections_schema.validate(manifest, REPO) == []
    text = json.dumps(manifest)
    assert [t["type"] for t in record if t["token"] in text] == []
    assert build() == build()


def test_all_off_gives_an_empty_valid_manifest():
    manifest = build(switches={s: False for s in SWITCHES}, placements=[])
    assert manifest == {"schema_version": 1, "injections": []}
    assert injections_schema.validate(manifest, REPO) == []


def test_one_switch_one_entry():
    manifest = build(switches={**{s: False for s in SWITCHES}, "spe_inject_drs_description": True},
                     placements=[PLACEMENTS[1]])
    assert [e["switch"] for e in manifest["injections"]] == ["spe_inject_drs_description"]


@pytest.mark.parametrize("case, kwargs, message", [
    ("missing canary", {"canary_files": {"sensitive/registry/linkage.csv"}}, "no canary"),
    ("missing placement", {"placements": PLACEMENTS[:2]}, "0 placements"),
    ("duplicate placement", {"placements": PLACEMENTS + PLACEMENTS[:1]}, "2 placements"),
    ("placed while off", {"switches": {**ALL_ON, "spe_inject_trs_description": False}}, "is off"),
    ("other payload", {"placements": [{**PLACEMENTS[0], "payload_sha256": "0" * 64}, *PLACEMENTS[1:]]}, "differs"),
    ("other tool", {"placements": [{**PLACEMENTS[0], "location": {"tool_id": "wes-drs-smoke", "field": "description"}},
                                   *PLACEMENTS[1:]]}, "catalogue selects"),
    # The DRS fixture selects by path: a placement naming that value under another key is not it.
    ("value under another key", {"placements": [PLACEMENTS[0], {**{k: v for k, v in PLACEMENTS[1].items() if k != "path"},
                                 "location": {"tool_id": "sensitive/secret/research_DO_NOT_LEAK", "field": "description"}},
                                 PLACEMENTS[2]]}, "catalogue selects"),
])
def test_build_errors(case, kwargs, message):
    with pytest.raises(BUILDER.ManifestBuildError, match=message):
        build(**kwargs)


def test_cli_writes_a_private_file_and_fails_on_a_missing_canary(tmp_path):
    script = ANSIBLE / "roles" / "handoff" / "files" / "injections_manifest.py"
    out = tmp_path / "injections.json"
    stdin = {"switches": ALL_ON, "placements": PLACEMENTS, "canary_files": sorted(CANARY_FILES)}
    argv = [sys.executable, str(script), "--fixtures", str(INJECTIONS / "fixtures.json"),
            "--repo-root", str(REPO), "--out", str(out)]
    subprocess.run(argv, input=json.dumps(stdin), text=True, check=True, capture_output=True)
    assert json.loads(out.read_text()) == build() and out.stat().st_mode & 0o777 == 0o600
    bad = subprocess.run(argv, input=json.dumps({**stdin, "canary_files": []}), text=True, capture_output=True)
    assert bad.returncode == 1 and "no canary" in bad.stderr
