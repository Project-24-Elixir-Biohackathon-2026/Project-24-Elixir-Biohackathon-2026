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
if [ -n "${FAKE_PROGRESS_LOG:-}" ]; then
  case "$2" in
    eval:controls) echo "controls=${SPE_EVAL_PROGRESS:-}" >> "$FAKE_PROGRESS_LOG" ;;
    eval:agent) echo "agent=${SPE_EVAL_PROGRESS:-}" >> "$FAKE_PROGRESS_LOG" ;;
  esac
fi
case "$2" in
  eval:controls) cp "$FAKE_CONTROLS" reports/controls.json; exit 100 ;;
  eval:agent) echo '{"results": {"results": []}}' > reports/agent.json; exit 100 ;;
esac
"""
# The non-default path (--suite/--reports-dir/--description) calls `npx promptfoo eval` directly rather
# than an npm script (run.sh's own comment says why): `-o <path>` is always the 8th word, and an agent
# eval is the one carrying `--repeat`, so detecting that is enough to tell the two calls apart.
FAKE_NPX = """#!/bin/sh
echo "$*" >> "$FAKE_NPM_LOG"
out=$8
is_agent=0
for a in "$@"; do
  if [ "$a" = "--repeat" ]; then is_agent=1; fi
done
if [ -n "${FAKE_PROGRESS_LOG:-}" ]; then
  if [ "$is_agent" = 1 ]; then
    echo "agent=${SPE_EVAL_PROGRESS:-}" >> "$FAKE_PROGRESS_LOG"
  else
    echo "controls=${SPE_EVAL_PROGRESS:-}" >> "$FAKE_PROGRESS_LOG"
  fi
fi
if [ "$is_agent" = 1 ]; then
  echo '{"results": {"results": []}}' > "$out"
else
  cp "$FAKE_CONTROLS" "$out"
fi
exit 100
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
    (tmp_path / "bin" / "npx").write_text(FAKE_NPX)
    (tmp_path / "bin" / "npx").chmod(0o755)
    hand = tmp_path / "handoff"
    hand.mkdir()
    (hand / "hardening.json").write_text(json.dumps(hardening(instance="t-01")))
    (hand / "canaries.json").write_text(json.dumps({"instance": "t-01", "tokens": CANARIES}))
    (hand / "injections.json").write_text(json.dumps(manifest(*ALL)))
    write_hosts(hand, hosts("t-01"))  # handoff.load_hardening checks the instance against hosts.yml
    log = tmp_path / "npm.log"

    def run(rows, repeat="3", *extra, env_extra=None):
        (tmp_path / "controls.json").write_text(json.dumps({"results": {"results": rows}}))
        env = {**os.environ, "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}", "FAKE_NPM_LOG": str(log),
               "FAKE_CONTROLS": str(tmp_path / "controls.json"), **(env_extra or {})}
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


def test_progress_env_set_only_for_the_agent_eval_default_path(setup, tmp_path):
    # task 5 review, Important 2: controls.yaml and agent.yaml both load isolation.py's progress
    # hook, so a shared SPE_EVAL_PROGRESS double-counts `done` once the agent suite's own `total`
    # line lands on top of the controls suite's. run.sh must unset it for the controls call only.
    run, _work, _hand = setup
    progress_log = tmp_path / "progress-calls.log"
    code, _calls, _err = run(rows(), "3", env_extra={"SPE_EVAL_PROGRESS": str(tmp_path / "progress.jsonl"),
                                                       "FAKE_PROGRESS_LOG": str(progress_log)})
    assert code == 0
    assert progress_log.read_text().splitlines() == ["controls=", f"agent={tmp_path / 'progress.jsonl'}"]


def test_progress_env_set_only_for_the_agent_eval_non_default_path(setup, tmp_path):
    run, work, _hand = setup
    target = work.parent / "progress-reports"
    progress_log = tmp_path / "progress-calls-2.log"
    code, _calls, _err = run(rows(), "3", "--reports-dir", str(target),
                             env_extra={"SPE_EVAL_PROGRESS": str(tmp_path / "progress.jsonl"),
                                        "FAKE_PROGRESS_LOG": str(progress_log)})
    assert code == 0
    assert progress_log.read_text().splitlines() == ["controls=", f"agent={tmp_path / 'progress.jsonl'}"]


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


def test_mixed_is_still_refused_on_the_default_ladder_path(setup):
    # fix round 1: --reports-dir/--suite/--description accept "mixed" (below); the ladder's own
    # default path (none of the three) must not, since it only ever builds clean or fully injected.
    run, _, hand = setup
    (hand / "hardening.json").write_text(json.dumps(hardening(instance="t-01", injections="mixed")))
    code, calls, _ = run(rows())
    assert code == 2 and calls == []


def test_mixed_is_accepted_with_reports_dir(setup):
    # fix round 1, cross-task gap: spe-eval run on an experiment naming only some of the
    # catalogue's injections writes hardening.json's injections as "mixed"; run.sh's own
    # --reports-dir path (spe-eval's own) must still run it, scored as injected.
    run, work, hand = setup
    target = work.parent / "mixed-reports"
    (hand / "hardening.json").write_text(json.dumps(hardening(instance="t-01", injections="mixed")))
    code, calls, _ = run(rows(), "3", "--reports-dir", str(target))
    assert code == 0, calls
    assert calls == [
        f"promptfoo eval -c controls.yaml --no-cache --no-share -o {target}/controls.json",
        f"promptfoo eval -c agent.yaml --no-cache --no-share -o {target}/agent.json --repeat 3",
    ]
    # scored as injected: injections.json (the placements) is copied alongside the rest.
    assert (target / "injections.json").is_file()


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


# --- run.sh's three new arguments (experiments spec part 03) ---
def test_reports_dir_places_everything_directly_and_is_not_cleared(setup):
    run, work, hand = setup
    target = work.parent / "custom-reports"
    target.mkdir()
    (target / "stale.txt").write_text("x")  # proves the directory is not cleared first
    code, calls, _ = run(rows(), "3", "--reports-dir", str(target))
    assert code == 0
    assert calls == [
        f"promptfoo eval -c controls.yaml --no-cache --no-share -o {target}/controls.json",
        f"promptfoo eval -c agent.yaml --no-cache --no-share -o {target}/agent.json --repeat 3",
    ]
    assert (target / "stale.txt").exists()
    names = {p.name for p in target.iterdir()}
    assert names == {"agent.json", "controls.json", "hardening.json", "injections.json", "run.json",
                     "gate-notes.json", "stale.txt"}
    assert json.loads((target / "gate-notes.json").read_text()) == []
    assert not (work / "reports").exists()
    label = json.loads((target / "run.json").read_text())
    assert label["canaries_sha256"] == handoff.canaries_digest(hand)


def test_reports_dir_gate_notes_file_carries_the_gate_s_notes(setup):
    run, work, hand = setup
    target = work.parent / "note-reports"
    note = "trs-write closed by this arm; declare it in probes"
    custom = rows()
    for r in custom:
        if r["vars"]["probe"] == "trs-write":
            r["gradingResult"]["reason"] = note
    code, _, _ = run(custom, "3", "--reports-dir", str(target))
    assert code == 0
    assert json.loads((target / "gate-notes.json").read_text()) == [note]


def test_suite_replaces_agent_yaml_without_a_reports_dir(setup):
    run, work, hand = setup
    code, calls, _ = run(rows(), "3", "--suite", "custom-suite.yaml")
    assert code == 0
    assert calls == [
        "promptfoo eval -c controls.yaml --no-cache --no-share -o reports/controls.json",
        "promptfoo eval -c custom-suite.yaml --no-cache --no-share -o reports/agent.json --repeat 3",
    ]
    out = work / "reports" / "L0"
    assert sorted(p.name for p in out.iterdir()) == [
        "agent.json", "controls.json", "hardening.json", "injections.json", "run.json"]
    assert not (work / "reports" / "gate-notes.json").exists()


def test_description_sets_both_evals_descriptions(setup):
    run, work, hand = setup
    target = work.parent / "d-reports"
    code, calls, _ = run(rows(), "3", "--reports-dir", str(target), "--description", "trs-guard mitigated")
    assert code == 0
    assert calls == [
        f"promptfoo eval -c controls.yaml --no-cache --no-share -o {target}/controls.json --description "
        "trs-guard mitigated controls",
        f"promptfoo eval -c agent.yaml --no-cache --no-share -o {target}/agent.json --repeat 3 --description "
        "trs-guard mitigated agent",
    ]


def test_all_three_arguments_together(setup):
    run, work, hand = setup
    target = work.parent / "all-reports"
    code, calls, _ = run(rows(), "5", "--suite", "custom-suite.yaml", "--reports-dir", str(target),
                         "--description", "trs-guard mitigated")
    assert code == 0
    assert calls == [
        f"promptfoo eval -c controls.yaml --no-cache --no-share -o {target}/controls.json --description "
        "trs-guard mitigated controls",
        f"promptfoo eval -c custom-suite.yaml --no-cache --no-share -o {target}/agent.json --repeat 5 "
        "--description trs-guard mitigated agent",
    ]
    names = {p.name for p in target.iterdir()}
    assert {"agent.json", "controls.json", "hardening.json", "injections.json", "run.json",
           "gate-notes.json"} <= names


def test_missing_flag_value_is_a_usage_error(setup):
    run, _, _ = setup
    code, calls, _ = run(rows(), "3", "--reports-dir")
    assert code == 2 and calls == []


def test_mismatch_with_reports_dir_refuses_before_any_model_call(setup):
    run, work, hand = setup
    target = work.parent / "mismatch-reports"
    code, calls, err = run(rows(failing={"egress"}), "3", "--reports-dir", str(target))
    assert code == 3 and "egress" in err
    assert calls == [f"promptfoo eval -c controls.yaml --no-cache --no-share -o {target}/controls.json"]
