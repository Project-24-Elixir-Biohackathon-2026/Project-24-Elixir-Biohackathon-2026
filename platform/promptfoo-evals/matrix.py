"""The ladder's results as counts and a Markdown matrix (spec part 06, decision 11), standard library only.

    python3 matrix.py counts reports/L<n> > ../../docs/results/<model>/L<n>.json
    python3 matrix.py render ../../docs/results/<model>/L*.json > ../../docs/results/canary-ladder-<model>.md

Run from platform/promptfoo-evals, where run.sh leaves reports/L<n>/ and docs/results/ is two levels up.
`counts` reads one level's reports directory (hardening.json, controls.json, agent.json, as run.sh
copies them) and keeps only labels, probe ids, test metadata and per-metric failure counts: never an
answer, a reason, a variable or a token, so its output can be committed and the raw reports deleted.
`render` turns the counts of one model's levels into Markdown; it refuses mixed models and duplicate
levels. A run without injections (hardening.json `injections: false`, spec clarification 6) is a column
of its own, "L<n> clean", beside the injected run of the same level.

promptfoo 0.124.1 `-o x.json` shape read here: {results: {results: [{testCase: {vars, metadata},
gradingResult: {pass, componentResults: [{pass, assertion: {metric}}]}, response: {error},
failureReason}]}}; a bare {results: [...]} is accepted too. A row without a gradingResult, with
response.error or with failureReason 2 (ERROR) counts as an error, not as a pass or a failure. So
does a row with a component whose reason starts with "configuration error:" (metrics.py's
hand-off/provider errors) or "Error running Python script:" (how promptfoo 0.124.1 reports an
assertion that raised, as an ordinary failed component): neither is evidence of a leak. Only
the six decision-8 assertions (METRICS) may carry a `metric:`; any other metric name is refused.

The catalogue metadata value sets (spec part 04, group/threat/path/closed_by) are fixed here as
CATALOGUE: this is their one definition, and the agent-catalogue lint (tests/test_catalogue.py)
imports it rather than keeping a second copy that could drift from this one.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = str(Path(__file__).resolve().parent)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import handoff  # noqa: E402

ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
GROUPS = ("utility", "direct", "troubleshooting", "injection", "egress")
# The agent catalogue's value sets (spec part 04, *Tests*): the one place these are enumerated.
# None is a member of threat/path/closed_by because a utility test carries closed_by: null, and a
# test outside the threat model (none yet) could carry threat/path: null.
CATALOGUE = {
    "group": frozenset(GROUPS),
    "threat": frozenset({"TM-001", "TM-002", "TM-003", "TM-004", None}),
    "path": frozenset({"P1", "P2", "P3", "P4", None}),
    "closed_by": frozenset({"L1", "L2", "L3", "L4", "L5", None}),
}
# The six leak metrics of decision 8 (metrics.py); the only metric names counts.py will record.
METRICS = frozenset({"canary.answer", "canary.touched", "canary.sent", "canary.delivered", "injection.followed",
                     "key.leak"})
ERROR = 2  # promptfoo ResultFailureReason.ERROR
# Component reason prefixes that mean "the assertion could not judge", not "the assertion failed":
# metrics.CONFIG_ERROR, and promptfoo 0.124.1's wording for a Python assertion that raised.
ERROR_REASONS = ("configuration error:", "Error running Python script:")


class MatrixError(Exception):
    pass


def _load(path: Path) -> object:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        raise MatrixError(f"missing {path}") from None
    except (OSError, ValueError) as e:  # JSON errors give a position, never the content
        raise MatrixError(f"unreadable {path}: {e}") from None


def _rows(report: object, name: str) -> list[dict]:
    results = report.get("results") if isinstance(report, dict) else None
    if isinstance(results, dict):
        results = results.get("results")
    if not isinstance(results, list):
        raise MatrixError(f"{name}: no results.results[] (promptfoo -o JSON report)")
    rows = [r for r in results if isinstance(r, dict)]
    if not rows:
        raise MatrixError(f"{name}: no results (an empty run proves nothing)")
    return rows


def _is_error(row: dict) -> bool:
    grading = row.get("gradingResult")
    if not isinstance(grading, dict) or row.get("failureReason") == ERROR or (row.get("response") or {}).get("error"):
        return True
    # Read, never copied: a reason can carry anything.
    return any(isinstance(c, dict) and str(c.get("reason") or "").startswith(ERROR_REASONS)
               for c in grading.get("componentResults") or [])


def _label(kind: str, value: object, where: str) -> str | None:
    """Only labels in CATALOGUE (or, for a metric, METRICS) are copied; nothing else, so a value that
    is not one of the catalogue's own labels is refused rather than echoed into counts.
    """
    if value is None and None in CATALOGUE.get(kind, ()):  # never for group or metric
        return None
    allowed = METRICS if kind == "metric" else CATALOGUE[kind]
    if not isinstance(value, str) or value not in allowed:
        raise MatrixError(f"{where}: not an allowed {kind} (spec part 04)")
    return value


def _controls(rows: list[dict]) -> dict:
    disagree = set()
    for row in rows:
        case = row.get("testCase") or {}
        probe = (case.get("vars") or {}).get("probe") or (case.get("metadata") or {}).get("probe")
        if not isinstance(probe, str) or not ID.fullmatch(probe):
            raise MatrixError("controls.json: a result without a kebab-case vars.probe")
        if _is_error(row) or not row["gradingResult"].get("pass"):
            disagree.add(probe)
    return {"probes": len(rows), "disagree": sorted(disagree)}


def _tests(rows: list[dict]) -> dict:
    tests: dict[str, dict] = {}
    for row in rows:
        meta = (row.get("testCase") or {}).get("metadata") or {}
        tid = meta.get("id")
        if not isinstance(tid, str) or not ID.fullmatch(tid):
            raise MatrixError("agent.json: a test without a kebab-case metadata.id")
        test = tests.setdefault(tid, {**{k: _label(k, meta.get(k), tid)
                                         for k in ("group", "threat", "path", "closed_by")},
                                      "runs": 0, "errors": 0, "passed": 0, "failures": {}})
        test["runs"] += 1
        if _is_error(row):
            test["errors"] += 1
            continue
        grading = row["gradingResult"]
        test["passed"] += bool(grading.get("pass"))
        for component in grading.get("componentResults") or []:
            metric = (component.get("assertion") or {}).get("metric") or component.get("metric")
            if metric is None:
                continue
            metric = _label("metric", metric, tid)
            test["failures"][metric] = test["failures"].get(metric, 0) + (not component.get("pass"))
    return tests


def counts(level_dir: Path) -> dict:
    directory = Path(level_dir)
    try:
        record = handoff.check_hardening(_load(directory / "hardening.json"))
    except handoff.ConfigError as e:
        # The contract promises MatrixError; a caller catching only that must not see a bare ConfigError.
        raise MatrixError(str(e)) from e
    return {"schema_version": 1, "instance": record["instance"], "level": record["level"],
            "injections": record["injections"],
            "model": f"{record['model_provider']}:{record['model']}", "commit": record["commit"],
            "restore_seconds": record.get("restore_seconds"),
            "controls": _controls(_rows(_load(directory / "controls.json"), "controls.json")),
            "tests": _tests(_rows(_load(directory / "agent.json"), "agent.json"))}


def _check(c: object, i: int) -> dict:
    keys = ("schema_version", "instance", "level", "injections", "model", "commit", "restore_seconds", "controls",
            "tests")
    if not isinstance(c, dict) or c.get("schema_version") != 1 or any(k not in c for k in keys):
        raise MatrixError(f"counts file {i + 1}: not counts version 1 (python3 matrix.py counts ...)")
    return c


def _cell(test: dict | None) -> str:
    if test is None:
        return "–"
    n = test["runs"]
    parts = [f"pass {test['passed']}/{n}"] if test["group"] == "utility" else []
    parts += [f"{metric.rsplit('.', 1)[-1]} {k}/{n}" for metric, k in sorted(test["failures"].items()) if k]
    if test["errors"]:
        parts.append(f"error {test['errors']}/{n}")
    return ", ".join(parts) or f"none/{n}"


def _column(c: dict) -> str:
    return f"L{c['level']}" + ("" if c["injections"] else " clean")


def render(counts_list: list[dict]) -> str:
    # A clean control run sits just before the injected run of its level.
    levels = sorted((_check(c, i) for i, c in enumerate(counts_list)), key=lambda c: (c["level"], c["injections"]))
    if not levels:
        raise MatrixError("no counts given")
    models = sorted({c["model"] for c in levels})
    if len(models) > 1:
        raise MatrixError(f"mixed models: {', '.join(models)}")
    columns = [_column(c) for c in levels]
    duplicates = sorted({n for n in columns if columns.count(n) > 1})
    if duplicates:
        raise MatrixError(f"duplicate levels: {', '.join(duplicates)}")

    def row(name: str, cells: list[str]) -> str:
        return f"| {name} | " + " | ".join(cells) + " |"

    restore = [("–" if c["restore_seconds"] is None else f"{c['restore_seconds']:.0f}") for c in levels]
    controls = [(f"all {c['controls']['probes']} as expected" if not c["controls"]["disagree"]
                 else "disagree: " + ", ".join(c["controls"]["disagree"])) for c in levels]
    lines = [f"# Canary evaluation ladder: {models[0]}", "",
             "Failures per metric over the repeats (utility tests: passes). Counts only: no answers, no tokens.", "",
             row("Level", columns), row("---", ["---"] * len(levels)),
             row("Instance", [c["instance"] for c in levels]),
             row("Commit", [f"`{c['commit'][:12]}`" for c in levels]),
             row("Restore (s)", restore), row("Controls", controls), "",
             "| Test | Group | Threat | Path | Closed by | " + " | ".join(columns) + " |",
             "|---" * (5 + len(levels)) + "|"]
    meta: dict[str, dict] = {}
    for c in levels:
        for tid, test in c["tests"].items():
            meta.setdefault(tid, test)
    order = sorted(meta, key=lambda t: (GROUPS.index(meta[t]["group"]) if meta[t]["group"] in GROUPS
                                        else len(GROUPS), t))
    for tid in order:
        m = meta[tid]
        labels = [m["group"] or "–", m["threat"] or "–", m["path"] or "–", m["closed_by"] or "–"]
        lines.append(row(tid, labels + [_cell(c["tests"].get(tid)) for c in levels]))
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    try:
        if len(argv) == 2 and argv[0] == "counts":
            print(json.dumps(counts(Path(argv[1])), indent=2, sort_keys=True))
            return 0
        if len(argv) >= 2 and argv[0] == "render":
            print(render([_load(Path(p)) for p in argv[1:]]), end="")
            return 0
    except MatrixError as e:  # counts() wraps handoff.ConfigError
        print(f"matrix: {e}", file=sys.stderr)
        return 1
    print("usage: matrix.py counts <reports/instance> | matrix.py render <L*.json>...", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
