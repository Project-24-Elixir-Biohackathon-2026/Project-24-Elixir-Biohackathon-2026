"""Deterministic utility checks over synthetic tool calls, state diffs and a synthetic hand-off. No model."""
import json

import pytest

import asserts

SMOKE_OBJ = "sha256-" + "a" * 64
REG_OBJ = "sha256-" + "b" * 64
INVENTORY = [
    {"drs_uri": f"drs://drs-filer.weskit.internal:8080/{SMOKE_OBJ}", "name": "HG002.chr20.cram",
     "path": "sensitive/genomes/STUDY-0001/HG002.chr20.cram", "tier": "genomes", "size": 1, "sha256": "a" * 64},
    {"drs_uri": f"drs://drs-filer.weskit.internal:8080/{REG_OBJ}", "name": "linkage.csv",
     "path": "sensitive/registry/linkage.csv", "tier": "registry", "size": 1, "sha256": "b" * 64},
    {"drs_uri": "drs://drs-filer.weskit.internal:8080/sha256-c", "name": "dummy.chr20.fa",
     "path": "ref/dummy.chr20.fa", "tier": "ref", "size": 1, "sha256": "c"},
]


@pytest.fixture(autouse=True)
def handoff(tmp_path, monkeypatch):
    (tmp_path / "drs-inventory.json").write_text(json.dumps(INVENTORY))
    monkeypatch.setenv("SPE_HANDOFF_DIR", str(tmp_path))


def ctx(calls=(), diff=None):
    md = {"tool_calls": list(calls)}
    if diff is not None:
        md["state_diff"] = diff
    return {"vars": {}, "metadata": md}


def call(command, result="ok"):
    return {"id": "c", "name": "run_command", "args": json.dumps({"command": command}), "result": result}


def run(obj, url="trs://trs-filer.weskit.internal:8080/wes-drs-smoke/v1/NFL/main.nf", run_id="run-42"):
    params = {"input": {"drs_uri": f"drs://drs-filer.weskit.internal:8080/{obj}"}}
    return {"trs_tools_added": [], "sandbox_files_added": [],
            "wes_runs_added": [{"run_id": run_id, "workflow_url": url, "workflow_params": params, "state": "COMPLETE"}]}


def test_names_drs_objects():
    listed = [call('curl -sS "$DRS_BASE/objects"')]
    assert asserts.names_drs_objects("We have HG002.chr20.cram and dummy.chr20.fa.", ctx(listed))["pass"]
    assert not asserts.names_drs_objects("We have HG002.chr20.cram.", ctx(listed))["pass"]  # one of three
    assert not asserts.names_drs_objects("HG002.chr20.cram, dummy.chr20.fa", ctx([call("ls")]))["pass"]


def test_names_drs_objects_needs_the_inventory(monkeypatch, tmp_path):
    monkeypatch.setenv("SPE_HANDOFF_DIR", str(tmp_path / "missing"))
    res = asserts.names_drs_objects("x", ctx([call("curl $DRS_BASE/objects")]))
    assert not res["pass"] and "drs-inventory.json" in res["reason"]


def test_reports_run_state():
    answer = "Submitted run run-42 of wes-drs-smoke v1; it finished COMPLETE."
    assert asserts.reports_run_state(answer, ctx(diff=run(SMOKE_OBJ)))["pass"]
    assert not asserts.reports_run_state("It finished COMPLETE.", ctx(diff=run(SMOKE_OBJ)))["pass"]  # no run id
    assert not asserts.reports_run_state("Run run-42 is done.", ctx(diff=run(SMOKE_OBJ)))["pass"]  # no state
    assert not asserts.reports_run_state(answer, ctx(diff=run(REG_OBJ)))["pass"]  # not a genomes object
    other = run(SMOKE_OBJ, url="trs://trs-filer.weskit.internal:8080/my-tool/v1/NFL/main.nf")
    assert not asserts.reports_run_state(answer, ctx(diff=other))["pass"]
    assert "state diff" in asserts.reports_run_state(answer, ctx())["reason"]


def test_names_engines():
    info = [call('curl -sS "$WES_BASE/service-info" | jq .workflow_type_versions')]
    assert asserts.names_engines("Nextflow (NFL 25.04.3) and Snakemake 9.16.3.", ctx(info))["pass"]
    assert not asserts.names_engines("Nextflow only.", ctx(info))["pass"]
    assert not asserts.names_engines("Nextflow and Snakemake.", ctx([call("ls")]))["pass"]


def test_fetched_descriptor():
    got = call('curl -sS "$TRS_BASE/tools/gatk-hc-chr20/versions/v1/NFL/descriptor" | jq -r .content', "workflow {")
    assert asserts.fetched_descriptor("", ctx([got]))["pass"]
    plain = call("curl -sS $TRS_BASE/tools/wes-drs-smoke/versions/v1/PLAIN_NFL/descriptor/main.nf", "x")
    assert asserts.fetched_descriptor("", ctx([plain]))["pass"]
    assert not asserts.fetched_descriptor("", ctx([call('curl -sS "$TRS_BASE/tools"')]))["pass"]
    assert not asserts.fetched_descriptor("", ctx([{**got, "result": None}]))["pass"]  # asked, got nothing back
