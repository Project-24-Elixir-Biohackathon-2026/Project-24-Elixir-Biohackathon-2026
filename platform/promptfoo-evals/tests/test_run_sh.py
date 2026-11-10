"""run.sh with a fake npm on PATH that records its calls: refuses before any model call on a mismatch."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import controls_asserts as ca
import handoff
from conftest import CANARIES, ENTRY_SHAPE, hardening, hosts, manifest, write_hosts, write_payloads

HERE = Path(__file__).resolve().parents[1]
FAKE_NPM = """#!/bin/sh
echo "$*" >> "$FAKE_NPM_LOG"
mkdir -p reports
case "$2" in
  eval:controls) cp "$FAKE_CONTROLS" reports/controls.json; exit 100 ;;
  eval:agent) echo '{"results": {"results": []}}' > reports/agent.json; exit 100 ;;
esac
"""
ALL = tuple(ENTRY_SHAPE)  # the three fixture ids


@pytest.fixture
def setup(tmp_path):
    repo = tmp_path / "repo"  # run.sh's copy sits at repo/platform/promptfoo-evals, so handoff.REPO_ROOT is repo
    work = repo / "platform" / "promptfoo-evals"
    work.mkdir(parents=True)
    # handoff imports the schema; the schema's build_catalogue imports metrics (lazily) for the
    # action -> detector map, and metrics imports asserts, so both come along too.
    for f in ("run.sh", "controls_asserts.py", "handoff.py", "injections_schema.py", "metrics.py", "asserts.py"):
        shutil.copy(HERE / f, work / f)
    report = repo / "platform" / "report"  # handoff.py imports canarymatch and canary_record from here
    report.mkdir(parents=True)
    for f in ("canarymatch.py", "canary_record.py"):
        shutil.copy(HERE.parent / "report" / f, report / f)
    write_payloads(repo)  # also writes the full fixtures.json/surfaces.json (conftest.py)
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "npm").write_text(FAKE_NPM)
    (tmp_path / "bin" / "npm").chmod(0o755)
    hand = tmp_path / "handoff"
    hand.mkdir()
    (hand / "hardening.json").write_text(json.dumps(hardening(instance="t-01")))
    (hand / "canaries.json").write_text(json.dumps({"instance": "t-01", "tokens": CANARIES}))
    (hand / "injections.json").write_text(json.dumps(manifest(*ALL)))
    write_hosts(hand, hosts("t-01"))  # handoff.load_hardening checks the instance against hosts.yml
    log = tmp_path / "npm.log"

    def run(rows, repeat="3", *extra):
        (tmp_path / "controls.json").write_text(json.dumps({"results": {"results": rows}}))
        env = {**os.environ, "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}", "FAKE_NPM_LOG": str(log),
               "FAKE_CONTROLS": str(tmp_path / "controls.json")}
        p = subprocess.run(["bash", str(work / "run.sh"), str(hand), repeat, *extra], env=env, capture_output=True,
                           text=True)
        calls = log.read_text().splitlines() if log.exists() else []
        return p.returncode, calls, p.stderr
    return run, work, hand


def rows(failing=()):
    return [{"vars": {"probe": p}, "success": p not in failing, "gradingResult": {"reason": "r"}}
            for p in ca.PROBE_CONTROL]


def make_clean(hand):
    (hand / "hardening.json").write_text(json.dumps(hardening(instance="t-01", injections=False)))
    (hand / "injections.json").write_text(json.dumps(manifest()))


def test_mismatch_refuses_before_any_model_call(setup):
    run, _, _ = setup
    code, calls, err = run(rows(failing={"egress"}))
    assert code == 3 and calls == ["run eval:controls"] and "egress" in err


def test_injected_runs_the_whole_suite_uncached_and_files_its_labels(setup):
    run, work, hand = setup
    code, calls, _ = run(rows())
    assert code == 0 and calls == ["run eval:controls", "run eval:agent -- --repeat 3 --no-cache"]
    out = work / "reports" / "L0"
    assert sorted(p.name for p in out.iterdir()) == [
        "agent.json", "controls.json", "hardening.json", "injections.json", "run.json"]
    label = json.loads((out / "run.json").read_text())
    assert label["canaries_sha256"] == handoff.canaries_digest(hand)
    assert label["started"].endswith("Z") and len(label["started"]) == 20


def test_clean_runs_the_whole_suite_in_its_own_directory(setup):
    run, work, hand = setup
    make_clean(hand)
    code, calls, _ = run(rows(), "5")
    assert code == 0 and calls[-1] == "run eval:agent -- --repeat 5 --no-cache"  # no filter: the whole suite
    out = work / "reports" / "L0-clean"
    assert sorted(p.name for p in out.iterdir()) == ["agent.json", "controls.json", "hardening.json", "run.json"]
    assert not (work / "reports" / "L0").exists()


@pytest.mark.parametrize("case", ["mixed", "injected-without-placements", "clean-without-a-target-canary"])
def test_a_build_that_is_not_a_ladder_condition_refuses_before_npm(setup, case):
    run, _, hand = setup
    if case == "mixed":
        (hand / "hardening.json").write_text(json.dumps(hardening(instance="t-01", injections="mixed")))
    elif case == "injected-without-placements":
        (hand / "injections.json").write_text(json.dumps(manifest()))
    else:
        make_clean(hand)
        tokens = [t for t in CANARIES if t["type"] != "flag-file"]
        (hand / "canaries.json").write_text(json.dumps({"instance": "t-01", "tokens": tokens}))
    code, calls, _ = run(rows())
    assert code == 2 and calls == []


def test_extra_promptfoo_arguments_are_refused(setup):
    # A filtered run would be filed as a whole condition: the build, not the caller, says what runs.
    run, _, _ = setup
    code, calls, _ = run(rows(), "3", "--filter-metadata", "group=injection")
    assert code == 2 and calls == []


def test_stale_hardening_refuses_before_npm(setup):
    run, _, hand = setup
    (hand / "hardening.json").write_text(json.dumps(hardening(instance="other-01")))
    code, calls, _ = run(rows())
    assert code == 2 and calls == []


@pytest.mark.parametrize("repeat", ["0", "x", "-1"])
def test_bad_repeat(setup, repeat):
    run, _, _ = setup
    code, calls, _ = run(rows(), repeat)
    assert code == 2 and calls == []
