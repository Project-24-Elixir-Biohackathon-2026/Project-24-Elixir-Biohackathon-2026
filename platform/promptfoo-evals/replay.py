"""Replay the canary ladder's agent runs from the agent's run log into promptfoo: no model, no instance.

The ladder deleted its promptfoo reports after counting them; the agent's run log
(`/var/lib/spe-agent/runs.jsonl`, the `agent-runs` volume, which the isolation reset leaves alone)
still holds every run: prompt, tool calls and answer. This turns it back into promptfoo evals that
`promptfoo view` renders, one per level, each run re-scored by the same assertions.

    python3 replay.py build <runs.jsonl> <counts dir> <out dir>   # e.g. ../../docs/results/qwen3.8-27b
    PROMPTFOO_CONFIG_DIR=<out dir>/promptfoo npx promptfoo eval -c <out dir>/<level>/replay.yaml \
        --no-cache --no-share -o <out dir>/<level>/agent.json        # each level, SPE_HANDOFF_DIR set
    python3 replay.py check <out dir> <counts dir>                  # the re-scored counts match the committed

`build` splits the log into levels by each counts file's `started` (a level ends where the next
begins) and refuses unless every test has exactly the counted runs and the hand-off's canaries are
the ones the levels were built with. Re-scored: `canary.answer`, `canary.touched`, `canary.sent` and
the tests' own task checks. Not re-scored, so left out of the replay: `injection.followed`,
`canary.delivered` and `reports_run_state` (they need the state diff, which the log lacks) and
`key.leak` (the run log redacts the keys, and the LLM key is not kept); the committed counts stay
their record. The log caps each field at 16 KiB, so a canary past that in a tool result is not seen.

The provider (`call_api`, promptfoo's default entry point) returns the logged run whose `run_id`
is the test's `vars.run_id`.
"""
from __future__ import annotations

import functools
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:  # promptfoo loads this file by path
    sys.path.insert(0, str(HERE))
import handoff  # noqa: E402
import matrix  # noqa: E402

RESCORED = ("canary.answer", "canary.touched", "canary.sent")
STATE_DIFF_ASSERTS = {"file://asserts.py:reports_run_state"}


class ReplayError(Exception):
    pass


def _started(value: str) -> float:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def _abs(value: object) -> object:
    """file://x.py:fn relative to this directory, made absolute: the replay configs live elsewhere."""
    if isinstance(value, str) and value.startswith("file://") and not value.startswith("file:///"):
        return "file://" + str(HERE / value[len("file://"):])
    return value


def _catalogue() -> dict[str, dict]:
    import yaml
    tests = {}
    for path in sorted((HERE / "tests").glob("*.yaml")):
        for test in yaml.safe_load(path.read_text()) or []:
            tests[test["vars"]["message"]] = test
    return tests


def _levels(counts_dir: Path) -> list[tuple[str, dict]]:
    levels = [(p.stem, matrix._load(p)) for p in sorted(Path(counts_dir).glob("L*.json"))]
    if not levels:
        raise ReplayError(f"no L*.json counts in {counts_dir}")
    return sorted(levels, key=lambda item: _started(item[1]["started"]))


def _assert(level: str) -> list[dict]:
    asserts = [{"type": "python", "value": _abs("file://asserts.py:no_tls_bypass")}]
    names = {"canary.answer": "canary_answer", "canary.touched": "canary_touched", "canary.sent": "canary_sent"}
    return asserts + [{"type": "python", "value": _abs(f"file://metrics.py:{fn}"), "metric": m}
                      for m, fn in names.items()]


def _config(level: str, counts: dict, runs_path: Path, tests: list[dict]) -> dict:
    return {
        "description": f"Canary ladder {level.replace('-', ' ')} · {counts['model'].split(':')[-1]} · "
                       f"started {counts['started']} · replayed from the agent run log",
        "prompts": ["{{message}}"],
        "providers": [{"id": _abs("file://replay.py"), "label": "spe-agent (replay)",
                       "config": {"runs": str(runs_path)}}],
        "evaluateOptions": {"maxConcurrency": 1},
        "defaultTest": {"assert": _assert(level)},
        "tests": tests,
    }


def build(runs_path: Path, counts_dir: Path, out_dir: Path) -> dict[str, int]:
    """Writes <out>/<level>/runs.jsonl and replay.yaml per level; returns the runs per level."""
    import yaml
    catalogue = _catalogue()
    digest = handoff.canaries_digest(handoff.handoff_dir())
    records = []
    for n, line in enumerate(Path(runs_path).read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError as e:  # the position only, never the content: a line can carry canaries
            raise ReplayError(f"{runs_path} line {n}: not JSON ({e.msg}, column {e.colno})") from None
        if isinstance(record, dict) and record.get("run_id") and record.get("input") in catalogue:
            records.append(record)
    levels = _levels(counts_dir)
    out_dir = Path(out_dir)
    done = {}
    for i, (level, counts) in enumerate(levels):
        if counts.get("canaries_sha256") != digest:
            raise ReplayError(f"{level}: built with other canaries than SPE_HANDOFF_DIR's (canaries_sha256)")
        start = _started(counts["started"])
        end = _started(levels[i + 1][1]["started"]) if i + 1 < len(levels) else float("inf")
        window = [r for r in records if start <= r["started"] < end]
        by_test: dict[str, list[dict]] = {}
        for record in window:
            by_test.setdefault(catalogue[record["input"]]["metadata"]["id"], []).append(record)
        expected = {tid: t["runs"] for tid, t in counts["tests"].items()}
        found = {tid: len(rs) for tid, rs in by_test.items()}
        if found != expected:
            wrong = sorted(t for t in set(found) | set(expected) if found.get(t) != expected.get(t))
            raise ReplayError(f"{level}: runs in the log differ from the counts for "
                              + ", ".join(f"{t} ({found.get(t, 0)} logged, {expected.get(t, 0)} counted)"
                                          for t in wrong)
                              + " (a run after the last level, or an aborted level rerun, lands in a level's window)")
        tests = []
        for test in catalogue.values():
            tid = test["metadata"]["id"]
            runs = sorted(by_test.get(tid, []), key=lambda r: r["started"])
            for n, record in enumerate(runs, 1):
                own = [{**a, "value": _abs(a["value"])} for a in test.get("assert") or []
                       if a.get("value") not in STATE_DIFF_ASSERTS]
                entry = {"description": f"{test['description']} · run {n}/{len(runs)}",
                         "vars": {"message": test["vars"]["message"], "run_id": record["run_id"]},
                         "metadata": {**test["metadata"], "replayed": True}}
                if own:
                    entry["assert"] = own
                tests.append(entry)
        level_dir = out_dir / level
        level_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        level_runs = level_dir / "runs.jsonl"
        fd = os.open(level_runs, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in window)
        (level_dir / "replay.yaml").write_text(
            yaml.safe_dump(_config(level, counts, level_runs, tests), sort_keys=False, allow_unicode=True))
        done[level] = len(window)
    return done


def check(out_dir: Path, counts_dir: Path) -> list[str]:
    """The re-scored metrics against the committed counts: one line per difference (test ids and numbers only)."""
    problems = []
    for level, counts in _levels(counts_dir):
        tests = matrix._tests(matrix._rows(matrix._load(Path(out_dir) / level / "agent.json"), f"{level}/agent.json"))
        for tid, committed in counts["tests"].items():
            got = tests.get(tid)
            if got is None:
                problems.append(f"{level} {tid}: not replayed")
                continue
            if got["runs"] != committed["runs"] or got["errors"] != committed.get("errors", 0):
                problems.append(f"{level} {tid}: {got['runs']} runs, {got['errors']} errors "
                                f"(committed {committed['runs']} runs, {committed.get('errors', 0)} errors)")
            for metric in RESCORED:
                a, b = got["failures"].get(metric, 0), committed["failures"].get(metric, 0)
                if a != b:
                    problems.append(f"{level} {tid}: {metric} {a}, committed {b}")
    return problems


@functools.lru_cache(maxsize=None)
def _runs(path: str) -> dict[str, dict]:
    return {r["run_id"]: r for r in map(json.loads, Path(path).read_text().splitlines()) if r.get("run_id")}


def call_api(prompt: str, options: dict | None = None, context: dict | None = None) -> dict:
    config = (options or {}).get("config") or {}
    run_id = ((context or {}).get("vars") or {}).get("run_id")
    record = _runs(config["runs"]).get(run_id)
    if record is None:
        return {"error": f"run {run_id} is not in {config['runs']}"}
    usage = record.get("usage") or {}
    out = {
        "output": record.get("answer") or "",
        "metadata": {"tool_calls": [{k: c.get(k) for k in ("id", "name", "args", "result")}
                                    for c in record.get("tool_calls") or []],
                     "run_id": record["run_id"], "thread_id": record.get("thread_id"),
                     "terminal": "RUN_FINISHED" if record.get("status") == "completed" else "RUN_ERROR",
                     "started": datetime.fromtimestamp(record["started"], timezone.utc).isoformat(),
                     "duration_s": round(record["ended"] - record["started"], 1),
                     "replayed_from": "agent run log (fields capped at 16 KiB)"},
        "tokenUsage": {"prompt": usage.get("input_tokens", 0), "completion": usage.get("output_tokens", 0),
                       "total": usage.get("input_tokens", 0) + usage.get("output_tokens", 0)},
    }
    if record.get("status") != "completed":
        out["error"] = f"the logged run ended {record.get('status')}: {str(record.get('error'))[:500]}"
    return out


def main(argv: list[str]) -> int:
    try:
        if len(argv) == 4 and argv[0] == "build":
            for level, n in build(Path(argv[1]), Path(argv[2]), Path(argv[3])).items():
                print(f"{level}: {n} runs")
            return 0
        if len(argv) == 3 and argv[0] == "check":
            problems = check(Path(argv[1]), Path(argv[2]))
            print("\n".join(problems) or f"every level matches the committed {', '.join(RESCORED)}")
            return 1 if problems else 0
    except (ReplayError, matrix.MatrixError, handoff.ConfigError) as e:
        print(f"replay: {e}", file=sys.stderr)
        return 2
    print(__doc__.split("\n\n")[2], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
