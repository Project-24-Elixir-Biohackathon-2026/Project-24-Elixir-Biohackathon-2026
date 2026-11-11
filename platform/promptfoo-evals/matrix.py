"""The ladder's results as counts and a Markdown matrix (spec part 06, decision 11), standard library only.

    python3 matrix.py counts reports/L<n> > ../../docs/results/<model>/L<n>.json
    python3 matrix.py render ../../docs/results/<model>/L*.json > ../../docs/results/canary-ladder-<model>.md

Run from platform/promptfoo-evals, where run.sh leaves reports/L<n>/ and docs/results/ is two levels up.
`counts` reads one run's reports directory (hardening.json, controls.json, agent.json, run.json and,
for an injected run, injections.json, as run.sh copies them) and keeps only labels, probe ids, test
metadata, per-metric failure counts, the start time, the canary digest and the planted payloads'
SHA-256: never an answer, a reason, a variable or a token, so its output can be committed and the raw
reports deleted. `render` turns the counts of one model's runs into Markdown; it refuses mixed models,
two runs of one level and condition, a level whose clean and injected runs were built with different
canaries, and one fixture id with two payloads. A clean run (hardening.json `injections: false`, spec
part 06, *Clean and injected runs*) is a column of its own, "L<n> clean", just before "L<n>".

promptfoo 0.125.1 `-o x.json` shape read here: {results: {results: [{testCase: {vars, metadata},
gradingResult: {pass, componentResults: [{pass, assertion: {metric}}]}, response: {error},
failureReason}]}}; a bare {results: [...]} is accepted too. A row without a gradingResult, with
response.error or with failureReason 2 (ERROR) counts as an error, not as a pass or a failure. So
does a row with a component whose reason starts with "configuration error:" (metrics.py's
hand-off/provider errors) or "Error running Python script:" (how promptfoo 0.125.1 reports an
assertion that raised, as an ordinary failed component): neither is evidence of a leak. Only
the six decision-8 assertions (METRICS) may carry a `metric:`; any other metric name is refused.

The catalogue metadata value sets (spec part 04, group/threat/path/closed_by) are built as
CATALOGUE from the repository's own files (build_catalogue, experiments spec part 01 decision 3):
group from the stems of tests/*.yaml and tests/experiments/*.yaml, threat from threats/TM-*.md,
path from paths/P*-*.md, closed_by from mitigations/*.yml. This is their one definition, and the
agent-catalogue lint (tests/test_catalogue.py) imports it rather than keeping a second copy that
could drift from this one.
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
SHA256 = re.compile(r"[0-9a-f]{64}")
STARTED = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")  # run.sh: date -u +%Y-%m-%dT%H:%M:%SZ
GROUPS = ("utility", "direct", "troubleshooting", "injection", "egress")  # render's row order; a
# group outside it (an experiment's own) sorts after, by name (see render's `order`)


def build_catalogue(root: Path) -> dict:
    """The agent catalogue's value sets (spec part 04, *Tests*), read from the repository's own
    files rather than listed here: `group` from the stems of the ladder's and the experiments'
    test files, `threat`/`path`/`closed_by` from the threat, path and mitigation catalogues'
    filenames (validate.py checks each id matches its filename, so the filename is enough).
    None is a member of threat/path/closed_by because a utility test carries closed_by: null, and
    a test outside the threat model could carry threat/path: null; never a member of group.
    """
    promptfoo = Path(root) / "platform/promptfoo-evals"
    groups = {p.stem for p in promptfoo.glob("tests/*.yaml")} \
        | {p.stem for p in promptfoo.glob("tests/experiments/*.yaml")}
    threats = {"-".join(p.stem.split("-")[:2]) for p in (Path(root) / "threats").glob("TM-*.md")}
    paths = {p.stem.split("-")[0] for p in (Path(root) / "paths").glob("P*-*.md")}
    closed_by = {p.stem for p in (Path(root) / "mitigations").glob("*.yml") if p.stem != "TEMPLATE"}
    return {
        "group": frozenset(groups),
        "threat": frozenset(threats | {None}),
        "path": frozenset(paths | {None}),
        "closed_by": frozenset(closed_by | {None}),
    }


REPO_ROOT = Path(__file__).resolve().parents[2]  # matrix.py is platform/promptfoo-evals/matrix.py
CATALOGUE = build_catalogue(REPO_ROOT)
# The six leak metrics of decision 8 (metrics.py); the only metric names counts.py will record.
METRICS = frozenset({"canary.answer", "canary.touched", "canary.sent", "canary.delivered", "injection.followed",
                     "key.leak"})
ERROR = 2  # promptfoo ResultFailureReason.ERROR
# Component reason prefixes that mean "the assertion could not judge", not "the assertion failed":
# metrics.CONFIG_ERROR, and promptfoo 0.125.1's wording for a Python assertion that raised.
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


def _run(directory: Path) -> dict:
    run = _load(directory / "run.json")
    if not isinstance(run, dict) or not isinstance(run.get("started"), str) or not STARTED.fullmatch(run["started"]) \
            or not isinstance(run.get("canaries_sha256"), str) or not SHA256.fullmatch(run["canaries_sha256"]):
        raise MatrixError("run.json: needs started (YYYY-MM-DDTHH:MM:SSZ) and canaries_sha256, as run.sh writes them")
    return run


def _payloads(directory: Path, injected: bool) -> dict[str, str]:
    """Fixture id -> payload SHA-256 from injections.json; only those two fields are read."""
    entries: object = []
    if (directory / "injections.json").exists():
        manifest = _load(directory / "injections.json")
        entries = manifest.get("injections") if isinstance(manifest, dict) else None
        if not isinstance(entries, list):
            raise MatrixError("injections.json: no injections[]")
    if bool(entries) != injected:
        raise MatrixError(f"injections.json does not match hardening.json's injections: {str(injected).lower()}")
    payloads: dict[str, str] = {}
    for e in entries:
        iid = e.get("id") if isinstance(e, dict) else None
        digest = e.get("payload_sha256") if isinstance(e, dict) else None
        if not isinstance(iid, str) or not ID.fullmatch(iid) or iid in payloads \
                or not isinstance(digest, str) or not SHA256.fullmatch(digest):
            raise MatrixError("injections.json: an entry without a unique kebab-case id and a payload_sha256")
        payloads[iid] = digest
    return payloads


def counts(level_dir: Path, *, allow_mixed: bool = False) -> dict:
    """One report directory's counts (the ladder's own reading, decision 11). `allow_mixed`
    (default `False`, the ladder's own call: unchanged) lets a hardening record whose
    `injections` is `"mixed"` through instead of refusing it: an experiment's arm can plant only
    some of the catalogue's fixtures (decision 9 / R4), which is exactly that record, and
    `spe_eval.arm_counts` (experiments spec part 07, `results`/`pr-body`) needs to read it too."""
    directory = Path(level_dir)
    try:
        record = handoff.check_hardening(_load(directory / "hardening.json"))
    except handoff.ConfigError as e:
        # The contract promises MatrixError; a caller catching only that must not see a bare ConfigError.
        raise MatrixError(str(e)) from e
    if record["injections"] == "mixed" and not allow_mixed:
        # check_hardening accepts "mixed" for an experiment's arm (decision 9 / R4), but the ladder
        # matrix only ever has true/false columns: render()'s own sort key, (level, injections),
        # would mix a bool and a str the moment one counts file is mixed.
        raise MatrixError(f"{directory / 'hardening.json'}: injections is \"mixed\", not a ladder "
                          "condition (true or false); the ladder matrix has no column for it")
    run = _run(directory)
    # "mixed" means at least one catalogue fixture is planted (never none, by definition): the
    # same bool _payloads itself uses for the "every fixture on" case.
    payloads_injected = True if record["injections"] == "mixed" else record["injections"]
    return {"schema_version": 1, "instance": record["instance"], "level": record["level"],
            "injections": record["injections"], "started": run["started"],
            "canaries_sha256": run["canaries_sha256"], "payloads": _payloads(directory, payloads_injected),
            "model": f"{record['model_provider']}:{record['model']}", "commit": record["commit"],
            "restore_seconds": record.get("restore_seconds"),
            "controls": _controls(_rows(_load(directory / "controls.json"), "controls.json")),
            "tests": _tests(_rows(_load(directory / "agent.json"), "agent.json"))}


def _check(c: object, i: int) -> dict:
    keys = ("schema_version", "instance", "level", "injections", "started", "canaries_sha256", "payloads", "model",
            "commit", "restore_seconds", "controls", "tests")
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
    # A clean run sits just before the injected run of its level.
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
    # Matched builds (spec part 02): the two conditions of a level share one canary record.
    unmatched = sorted({c["level"] for c in levels
                        if len({o["canaries_sha256"] for o in levels if o["level"] == c["level"]}) > 1})
    if unmatched:
        raise MatrixError("clean and injected runs built with different canaries: "
                          + ", ".join(f"L{n}" for n in unmatched))
    planted: dict[str, set[str]] = {}
    for c in levels:
        for iid, digest in c["payloads"].items():
            planted.setdefault(iid, set()).add(digest)
    if two := sorted(iid for iid, digests in planted.items() if len(digests) > 1):
        raise MatrixError(f"two payloads for one fixture: {', '.join(two)}")

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
             row("Started (UTC)", [c["started"][:16].replace("T", " ") for c in levels]),
             row("Payloads", [", ".join(f"{i} {d[:8]}" for i, d in sorted(c["payloads"].items())) or "–"
                              for c in levels]),
             row("Restore (s)", restore), row("Controls", controls), "",
             "| Test | Group | Threat | Path | Closed by | " + " | ".join(columns) + " |",
             "|---" * (5 + len(levels)) + "|"]
    meta: dict[str, dict] = {}
    for c in levels:
        for tid, test in c["tests"].items():
            meta.setdefault(tid, test)

    def group_key(group: str) -> tuple:
        return (GROUPS.index(group), "") if group in GROUPS else (len(GROUPS), group)

    order = sorted(meta, key=lambda t: group_key(meta[t]["group"]) + (t,))
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
