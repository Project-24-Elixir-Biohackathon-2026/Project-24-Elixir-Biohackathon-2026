"""The run-log replay on a synthetic log and synthetic counts (conftest.py). No instance, no promptfoo."""
import json

import pytest
import yaml

import handoff
import replay

CATALOGUE = replay._catalogue()
BY_ID = {t["metadata"]["id"]: t for t in CATALOGUE.values()}
STATE_DIFF_TEST = next(t["metadata"]["id"] for t in CATALOGUE.values()
                       if any(a.get("value") in replay.STATE_DIFF_ASSERTS for a in t.get("assert") or []))
L0_START, L1_START = 1_700_000_000.0, 1_700_010_000.0


def iso(ts: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(tid: str, started: float, n: int, **overrides) -> dict:
    record = {"run_id": f"run-{tid}-{int(started)}-{n}", "thread_id": f"thread-{n}", "started": started + n,
              "ended": started + n + 12.34, "input": BY_ID[tid]["vars"]["message"], "status": "completed",
              "answer": f"answer {n}", "usage": {"input_tokens": 100, "output_tokens": 20},
              "tool_calls": [{"id": "c1", "name": "shell", "args": {"cmd": "ls"}, "result": "ok", "extra": "x"}]}
    record.update(overrides)
    return record


def counts(started: float, digest: str, runs: dict[str, int]) -> dict:
    return {"schema_version": 1, "model": "openai_compatible:qwen3.8-27b", "started": iso(started),
            "canaries_sha256": digest,
            "tests": {tid: {**{k: BY_ID[tid]["metadata"][k] for k in ("group", "threat", "path", "closed_by")},
                            "runs": n, "errors": 0, "passed": 0,
                            "failures": {m: 0 for m in replay.RESCORED}} for tid, n in runs.items()}}


@pytest.fixture
def ladder(tmp_path, handoff_dir):
    """Two levels: L0 with 2 + 1 runs, L1 with 1 run of the state-diff test; plus noise the build drops."""
    digest = handoff.canaries_digest(handoff_dir)
    counts_dir = tmp_path / "counts"
    counts_dir.mkdir()
    l0 = counts(L0_START, digest, {"ask-flag-file": 2, "list-workflows": 1})
    l1 = counts(L1_START, digest, {STATE_DIFF_TEST: 1})
    (counts_dir / "L0.json").write_text(json.dumps(l0))
    (counts_dir / "L1.json").write_text(json.dumps(l1))
    records = [run("ask-flag-file", L0_START, 1), run("ask-flag-file", L0_START, 2),
               run("list-workflows", L0_START, 3), run(STATE_DIFF_TEST, L1_START, 1),
               {**run("list-workflows", L0_START, 9), "input": "a question from a person, not the suite"},
               {"event": "startup"}]
    log = tmp_path / "runs.jsonl"
    log.write_text("".join(json.dumps(r) + "\n" for r in records))
    return {"log": log, "counts": counts_dir, "out": tmp_path / "out", "records": records, "L0": l0, "L1": l1}


def test_build_splits_the_log_by_level(ladder):
    assert replay.build(ladder["log"], ladder["counts"], ladder["out"]) == {"L0": 3, "L1": 1}
    l0 = yaml.safe_load((ladder["out"] / "L0" / "replay.yaml").read_text())
    ids = [t["vars"]["run_id"] for t in l0["tests"]]
    assert ids == [r["run_id"] for r in ladder["records"][:3]]
    assert [t["description"].rsplit(" · ", 1)[1] for t in l0["tests"]] == ["run 1/2", "run 2/2", "run 1/1"]
    assert all(t["metadata"]["replayed"] for t in l0["tests"])
    assert l0["providers"][0]["config"]["runs"] == str(ladder["out"] / "L0" / "runs.jsonl")
    assert l0["providers"][0]["id"] == f"file://{replay.HERE / 'replay.py'}"
    metrics = [a.get("metric") for a in l0["defaultTest"]["assert"]]
    assert metrics == [None, *replay.RESCORED]
    logged = (ladder["out"] / "L0" / "runs.jsonl")
    assert [json.loads(line)["run_id"] for line in logged.read_text().splitlines()] == ids
    assert logged.stat().st_mode & 0o777 == 0o600


def test_build_drops_the_state_diff_assertion_and_makes_paths_absolute(ladder):
    replay.build(ladder["log"], ladder["counts"], ladder["out"])
    (test,) = yaml.safe_load((ladder["out"] / "L1" / "replay.yaml").read_text())["tests"]
    values = [a["value"] for a in test.get("assert") or []]
    assert not set(values) & replay.STATE_DIFF_ASSERTS
    assert all(v.startswith("file:///") for v in values)


def test_build_refuses_a_count_mismatch(ladder):
    ladder["L0"]["tests"]["ask-flag-file"]["runs"] = 3
    (ladder["counts"] / "L0.json").write_text(json.dumps(ladder["L0"]))
    with pytest.raises(replay.ReplayError, match=r"L0: .*ask-flag-file \(2 logged, 3 counted\)"):
        replay.build(ladder["log"], ladder["counts"], ladder["out"])


def test_build_refuses_other_canaries(ladder):
    ladder["L1"]["canaries_sha256"] = "0" * 64
    (ladder["counts"] / "L1.json").write_text(json.dumps(ladder["L1"]))
    with pytest.raises(replay.ReplayError, match="L1: built with other canaries"):
        replay.build(ladder["log"], ladder["counts"], ladder["out"])


def test_build_needs_counts(tmp_path, ladder):
    with pytest.raises(replay.ReplayError, match="no L\\*.json"):
        replay.build(ladder["log"], tmp_path / "out", ladder["out"])


def test_call_api_returns_the_logged_run(ladder):
    replay.build(ladder["log"], ladder["counts"], ladder["out"])
    options = {"config": {"runs": str(ladder["out"] / "L0" / "runs.jsonl")}}
    record = ladder["records"][0]
    out = replay.call_api("ignored", options, {"vars": {"run_id": record["run_id"]}})
    assert out["output"] == "answer 1" and "error" not in out
    assert out["metadata"]["tool_calls"] == [{"id": "c1", "name": "shell", "args": {"cmd": "ls"}, "result": "ok"}]
    assert out["metadata"]["terminal"] == "RUN_FINISHED" and out["metadata"]["duration_s"] == 12.3
    assert out["tokenUsage"] == {"prompt": 100, "completion": 20, "total": 120}
    missing = replay.call_api("ignored", options, {"vars": {"run_id": "run-unknown"}})
    assert missing["error"].startswith("run run-unknown is not in")


def test_call_api_marks_a_failed_run(tmp_path):
    log = tmp_path / "runs.jsonl"
    log.write_text(json.dumps(run("ask-flag-file", L0_START, 1, run_id="failed", status="failed",
                                  error="model timeout")) + "\n")
    out = replay.call_api("", {"config": {"runs": str(log)}}, {"vars": {"run_id": "failed"}})
    assert out["metadata"]["terminal"] == "RUN_ERROR"
    assert out["error"] == "the logged run ended failed: model timeout"


def report(rows: list[tuple[str, dict[str, bool]]]) -> dict:
    return {"results": {"results": [
        {"testCase": {"metadata": BY_ID[tid]["metadata"]},
         "gradingResult": {"pass": all(passes.values()),
                           "componentResults": [{"pass": ok, "assertion": {"metric": m}} for m, ok in passes.items()]}}
        for tid, passes in rows]}}


def test_check_compares_the_rescored_metrics(ladder):
    replay.build(ladder["log"], ladder["counts"], ladder["out"])
    clean = {m: True for m in replay.RESCORED}
    (ladder["out"] / "L0" / "agent.json").write_text(json.dumps(report(
        [("ask-flag-file", clean), ("ask-flag-file", clean), ("list-workflows", clean)])))
    (ladder["out"] / "L1" / "agent.json").write_text(json.dumps(report([(STATE_DIFF_TEST, clean)])))
    assert replay.check(ladder["out"], ladder["counts"]) == []

    (ladder["out"] / "L0" / "agent.json").write_text(json.dumps(report(
        [("ask-flag-file", {**clean, "canary.touched": False}), ("ask-flag-file", clean)])))
    assert replay.check(ladder["out"], ladder["counts"]) == [
        "L0 ask-flag-file: canary.touched 1, committed 0", "L0 list-workflows: not replayed"]


def test_check_compares_errors_with_the_committed(ladder):
    replay.build(ladder["log"], ladder["counts"], ladder["out"])
    clean = {m: True for m in replay.RESCORED}
    failed = report([("list-workflows", clean)])["results"]["results"][0] | {"response": {"error": "ended failed"}}
    rows = report([("ask-flag-file", clean), ("ask-flag-file", clean)])
    rows["results"]["results"].append(failed)
    (ladder["out"] / "L0" / "agent.json").write_text(json.dumps(rows))
    (ladder["out"] / "L1" / "agent.json").write_text(json.dumps(report([(STATE_DIFF_TEST, clean)])))
    assert replay.check(ladder["out"], ladder["counts"]) == [
        "L0 list-workflows: 1 runs, 1 errors (committed 1 runs, 0 errors)"]
    ladder["L0"]["tests"]["list-workflows"]["errors"] = 1  # the original run errored too
    (ladder["counts"] / "L0.json").write_text(json.dumps(ladder["L0"]))
    assert replay.check(ladder["out"], ladder["counts"]) == []


def test_levels_are_ordered_by_start_not_name(ladder):
    (ladder["counts"] / "L1.json").rename(ladder["counts"] / "L0-clean.json")  # sorts before L0.json by name
    assert list(replay.build(ladder["log"], ladder["counts"], ladder["out"])) == ["L0", "L0-clean"]


def test_build_refuses_a_line_that_is_not_json(ladder):
    ladder["log"].write_text(ladder["log"].read_text() + "\n" + '{"run_id": "half-writ')
    with pytest.raises(replay.ReplayError, match=r"line 8: not JSON") as e:
        replay.build(ladder["log"], ladder["counts"], ladder["out"])
    assert "half-writ" not in str(e.value)


def test_main_reports_a_refusal(ladder, capsys):
    ladder["L1"]["canaries_sha256"] = "0" * 64
    (ladder["counts"] / "L1.json").write_text(json.dumps(ladder["L1"]))
    assert replay.main(["build", str(ladder["log"]), str(ladder["counts"]), str(ladder["out"])]) == 2
    assert "replay: L1: built with other canaries" in capsys.readouterr().err
    assert replay.main([]) == 2
