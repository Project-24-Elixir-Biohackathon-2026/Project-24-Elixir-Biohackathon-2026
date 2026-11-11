#!/usr/bin/env python3
"""Check that one experiment (or every experiment) will run and fits the catalogue.

    python3 check_experiment.py [<name>] [--json]

At the repository root, beside validate.py: standard library plus PyYAML only, offline, under a
minute. See docs/specs/2026-11-10-experiments-design/05-contribution.md, `check_experiment.py
[<name>]`. It does not judge what a contribution should contain (05-contribution.md, *A skeleton,
not a rulebook*): nothing here refuses an experiment for its shape, only for what would fail in the
middle of a run or break another experiment.

Without <name>, every experiments/*.yml is checked (experiments/TEMPLATE.yml and
mitigations/TEMPLATE.yml are copy-and-fill-in documents, not experiments or mitigations to check,
and are excluded here too).

What is checked, reusing validate.py's functions rather than duplicating them:

  - validate.py's own catalog checks pass: threats, paths, mitigations (decision 4's mitigation
    'off'-equals-defaults and one-owner-per-key checks are part of this);
  - the experiment file itself, via validate.check_experiment: its threat, paths, mitigation, base
    mitigations, injections and test ids resolve; parameters are template parameters; vars collide
    with nothing; requires/conflicts hold per arm (01-experiment-model.md, decisions 1 and 4);
  - no file the experiment names (its own file, its mitigation file, its tests file, an injection's
    payload, its threat or path files) still carries a TODO placeholder (decision 18: spe-eval new's
    scaffolding is refused until filled);
  - each of its injections (decision 23): the payload names its target_file; its canary_file is
    planted by a type in the experiment's parameters.canaries; its switch defaults to false; its
    surface has location keys (platform/ansible/catalog/injections/surfaces.json); its action has a
    detector (metrics.DETECTORS);
  - each of its tests: its metadata labels resolve against the test catalogue's value sets
    (platform/promptfoo-evals/matrix.py, imported when available, else rebuilt from the same files),
    and each `type: python` assertion's `file://<module>.py:<function>` names a function that exists.

Each problem is printed as `<file>:<line>: <id>: <what is wrong>: <what to do>` (line is 1 when not
known). `--json` prints the same problems as a JSON list of objects. Exit codes: 0 nothing wrong,
1 problems were found, 2 a usage or configuration error (an unknown experiment name, a missing or
unreadable catalog file). Nothing here prints a canary value, a key or a secret.

Usage:
    python3 check_experiment.py [<name>] [--json]
                                 [--threats-dir threats] [--vocab vocabulary.yaml]
                                 [--paths-dir paths] [--mitigations-dir mitigations]
                                 [--group-vars platform/ansible/inventory/group_vars/all.yml]
                                 [--probes-dir platform/promptfoo-evals/probes]
                                 [--experiments-dir experiments]
                                 [--fixtures platform/ansible/catalog/injections/fixtures.json]
                                 [--tests-dir platform/promptfoo-evals/tests]

Dependencies:
    pip install pyyaml
"""
from __future__ import annotations

import argparse
import functools
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent  # the repository root; check_experiment.py lives here
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import validate  # noqa: E402  (the repository's own validator; reused rather than duplicated)

PROMPTFOO_EVALS = HERE / "platform" / "promptfoo-evals"  # real code (matrix.py, metrics.py,
# injections_schema.py), always read from this script's own location, never from a test's
# overridden data directories: these are the scoring/lint code, not catalog data to fixture.

PYTHON_ASSERT = re.compile(r"^file://([^:]+\.py):(\w+)$")

# canary_file (platform/ansible/catalog/injections/fixtures.json) -> the spe-experiments
# `parameters.canaries` value that plants it, from platform/ansible/roles/spe_data/files/
# spe_seed.py's `canaries.add(..., <file>, ...)` calls (the source of truth: canary planting is
# code, not a catalog file, so this mapping is kept here rather than read from a file; a new
# canary_file needs a line added here, and test_check_experiment.py's drift test catches this
# table and spe_seed.py falling out of step).
#
# Only sensitive/registry/ and sensitive/secret/ files appear: injections_schema._disclosure
# defines a disclosure rule for those two directories only, so an injection naming any other
# canary_file (e.g. a sensitive/genomes/*.vcf.gz one, planted by the vcf_variants canaries type)
# is always refused at run time regardless of what this table says -- there is no such entry to
# keep.
CANARY_FILE_TYPES: dict[str, str] = {
    "sensitive/registry/linkage.csv": "registry_tokens",
    "sensitive/registry/patient_identifiers_DO_NOT_EXPORT.csv": "honeypot_files",
    "sensitive/registry/.aws_credentials_backup.txt": "honeypot_files",
    "sensitive/registry/db_migration_notes.env": "honeypot_files",
    "sensitive/secret/research_DO_NOT_LEAK": "flag_file",
}


def canary_type_for(canary_file: str) -> str | None:
    """The `parameters.canaries` value that plants `canary_file`, or None when unknown."""
    return CANARY_FILE_TYPES.get(canary_file)


class ConfigError(Exception):
    """A usage or configuration error (exit 2): not a problem with an experiment, but with being
    able to check one at all."""


@dataclass
class Problem:
    file: str
    line: int
    id: str
    problem: str
    fix: str

    def format(self) -> str:
        return f"{self.file}:{self.line}: {self.id}: {self.problem}: {self.fix}"

    def to_dict(self) -> dict:
        return {"file": self.file, "line": self.line, "id": self.id, "problem": self.problem, "fix": self.fix}


SEE_SPEC = "see docs/specs/2026-11-10-experiments-design/01-experiment-model.md"


@dataclass
class Catalog:
    """Everything loaded once, shared across every experiment file being checked."""
    threat_ids: set[str]
    path_ids: set[str]
    mitigations_by_id: dict[str, dict]
    fixtures: list[dict]
    fixtures_by_id: dict[str, dict]
    test_ids: set[str]
    tests_by_id: dict[str, dict]
    reserved_vars: set[str]
    group_vars: dict
    surfaces: dict
    detectors: dict
    catalogue_labels: dict
    threats_dir: Path
    paths_dir: Path
    mitigations_dir: Path
    tests_dir: Path
    injections_dir: Path
    fixtures_path: Path
    group_vars_path: Path
    default_canaries: list[str]
    injections_schema: object


def _wrap(raw: list[str], directory: Path, pattern: re.Pattern | None) -> list[Problem]:
    """validate.py's own problems ('<file>.ext: message' or 'catalog: message') as Problems."""
    out = []
    for line in raw:
        file_part, sep, message = line.partition(": ")
        if not sep:
            file_part, message = "catalog", line
        if file_part == "catalog":
            out.append(Problem(str(directory), 1, directory.name, message,
                                "run `python validate.py` for the full catalog check"))
            continue
        ident = file_part.rsplit(".", 1)[0]
        if pattern:
            m = pattern.match(file_part)
            if m:
                ident = m.group(1)
        out.append(Problem(str(directory / file_part), 1, ident, message,
                            "run `python validate.py` for the full catalog check"))
    return out


def _todo_line(text: str) -> int | None:
    for i, line in enumerate(text.splitlines(), start=1):
        if "TODO" in line:
            return i
    return None


def _todo_problems(path: Path, ident: str, what: str, fix: str) -> list[Problem]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    line = _todo_line(text)
    if line is None:
        return []
    return [Problem(str(path), line, ident, f"TODO left in {what} ({path.name})", fix)]


def _load_surfaces(path: Path) -> dict[str, list]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"surfaces file '{path}': {exc}") from exc
    surfaces = data.get("surfaces") if isinstance(data, dict) else None
    if not isinstance(surfaces, dict):
        raise ConfigError(f"surfaces file '{path}' has no 'surfaces' object")
    return surfaces


def _default_canaries() -> list[str]:
    """The spe-experiments form's own default `canaries` list (`platform/coder/experiments-
    template/main.tf`: `form_defaults = local.experiments["ladder-l0"].parameters`), read from
    this script's own repository location -- never a test's overridden `experiments_dir` -- so an
    experiment that leaves out `parameters.canaries` is checked against what the form actually
    plants for it, not an empty list."""
    try:
        data = yaml.safe_load((HERE / "experiments" / "ladder-l0.yml").read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return []
    if not isinstance(data, dict):
        return []
    canaries = (data.get("parameters") or {}).get("canaries")
    return list(canaries) if isinstance(canaries, list) else []


def _load_detectors() -> dict:
    """metrics.DETECTORS: the action -> detector map (standard library only; see PROMPTFOO_EVALS)."""
    if str(PROMPTFOO_EVALS) not in sys.path:
        sys.path.insert(0, str(PROMPTFOO_EVALS))
    try:
        import metrics
    except ImportError as exc:
        raise ConfigError(f"cannot import metrics.py: {exc}") from exc
    return metrics.DETECTORS


def _load_injections_schema():
    """`platform/promptfoo-evals/injections_schema.py`: the schema `injections_manifest.py`
    enforces on every planted injection at run time (02-hand-off.md). Reused here (`DATA_SHARE`,
    `_disclosure`) so the offline check and the run-time one never drift apart."""
    if str(PROMPTFOO_EVALS) not in sys.path:
        sys.path.insert(0, str(PROMPTFOO_EVALS))
    try:
        import injections_schema
    except ImportError as exc:
        raise ConfigError(f"cannot import injections_schema.py: {exc}") from exc
    return injections_schema


def _catalogue_label_values() -> dict:
    """The test catalogue's label value sets (group/threat/path/closed_by), reused from
    platform/promptfoo-evals/matrix.py (decision 3) when importable offline (it is, standard
    library only); otherwise rebuilt minimally from the same files, against this script's own
    repository root (never a test's overridden catalog directories: a rebuilt value set must stay
    consistent with the real catalogue the scoring side reads)."""
    try:
        if str(PROMPTFOO_EVALS) not in sys.path:
            sys.path.insert(0, str(PROMPTFOO_EVALS))
        import matrix
        return matrix.build_catalogue(HERE)
    except Exception:
        tests_dir = HERE / "platform" / "promptfoo-evals" / "tests"
        groups = {p.stem for p in tests_dir.glob("*.yaml")} | \
            {p.stem for p in (tests_dir / "experiments").glob("*.yaml")}
        threats = set()
        for p in (HERE / "threats").glob("TM-*.md"):
            m = validate.FILENAME_PATTERN.match(p.name)
            if m:
                threats.add(m.group(1))
        paths = set()
        for p in (HERE / "paths").glob("P*.md"):
            m = validate.PATH_FILENAME_PATTERN.match(p.name)
            if m:
                paths.add(m.group(1))
        mitigations = {p.stem for p in (HERE / "mitigations").glob("*.yml") if p.stem != "TEMPLATE"}
        return {
            "group": frozenset(groups), "threat": frozenset(threats | {None}),
            "path": frozenset(paths | {None}), "closed_by": frozenset(mitigations | {None}),
        }


def _load_tests_by_id(tests_dir: Path) -> dict[str, dict]:
    """id -> {"test": <the test dict>, "file": <path>}, over tests_dir/*.yaml and
    tests_dir/experiments/*.yaml (as validate.test_ids_from scans, but keeping the full test)."""
    tests: dict[str, dict] = {}
    files = sorted(tests_dir.glob("*.yaml")) + sorted((tests_dir / "experiments").glob("*.yaml"))
    for path in files:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, UnicodeDecodeError):
            continue
        if not isinstance(data, list):
            continue
        for test in data:
            if not isinstance(test, dict):
                continue
            meta = test.get("metadata")
            if isinstance(meta, dict) and isinstance(meta.get("id"), str):
                tests[meta["id"]] = {"test": test, "file": path}
    return tests


@functools.lru_cache(maxsize=None)
def _module_functions(path: str) -> frozenset[str]:
    """The top-level function (or assigned) names of a Python module, via ast (never executed)."""
    import ast
    try:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return frozenset()
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return frozenset(names)


def _check_injection(iid: str, fixture: dict, parameters: dict, cat: Catalog) -> list[Problem]:
    problems: list[Problem] = []
    payload = fixture.get("payload")
    target_file = fixture.get("target_file", "")
    canary_file = fixture.get("canary_file", "")
    switch = fixture.get("switch", "")
    surface = fixture.get("surface", "")
    action = fixture.get("action", "")
    disclosure = fixture.get("disclosure", "")
    select = fixture.get("select")

    # `spe-eval new --injection` writes target_file/canary_file/action/disclosure as the literal
    # string TODO: named here, separately from the mismatch checks below, which would otherwise
    # report the same TODO placeholder as a confusing mismatch instead of a clear TODO.
    todo_fields = [f for f in ("target_file", "canary_file", "action", "disclosure") if fixture.get(f) == "TODO"]
    for field in todo_fields:
        problems.append(Problem(
            str(cat.fixtures_path), 1, iid, f"TODO left in fixture field '{field}' ({cat.fixtures_path.name})",
            "fill in its TODOs",
        ))

    payload_path: Path | None = None
    if not isinstance(payload, str):
        problems.append(Problem(str(cat.fixtures_path), 1, iid, "'payload' is missing or not a string",
                                 "add a payload field naming the payload file"))
    elif payload != Path(payload).name or ".." in Path(payload).parts:
        # A plain filename only (01-experiment-model.md, *Attacks*: the payload sits "beside
        # fixtures.json"): never a path that climbs out of the injections directory it is read from.
        problems.append(Problem(
            str(cat.fixtures_path), 1, iid, f"payload '{payload}' is not a plain filename",
            "name only the payload file itself, with no directory part or '..'",
        ))
    else:
        payload_path = cat.injections_dir / payload
        problems += _todo_problems(payload_path, iid, "its injection payload", "fill in its TODOs")
        if payload_path.is_file():
            text = payload_path.read_text(encoding="utf-8")
            if target_file and target_file not in text:
                problems.append(Problem(
                    str(payload_path), 1, iid, f"payload does not name its target '{target_file}'",
                    f"mention {target_file} in the payload text",
                ))
        else:
            problems.append(Problem(
                str(payload_path), 1, iid, "payload file not found",
                "add the payload file beside fixtures.json",
            ))

    canary_type = canary_type_for(canary_file)
    if "canaries" not in parameters:
        # The form's own default: an experiment that leaves this out is not planting nothing, it
        # is getting whatever `spe-experiments` plants by default.
        canaries_param = cat.default_canaries
    else:
        canaries_param = parameters.get("canaries")
        if not isinstance(canaries_param, list):
            canaries_param = []
    if canary_type is None:
        problems.append(Problem(
            str(cat.fixtures_path), 1, iid,
            f"canary file '{canary_file}' is not a known canary (not planted by any canaries type)",
            "use a canary_file check_experiment.py's CANARY_FILE_TYPES knows, or extend it",
        ))
    elif canary_type not in canaries_param:
        problems.append(Problem(
            str(cat.fixtures_path), 1, iid,
            f"canary file '{canary_file}' is planted by canaries type '{canary_type}', "
            f"not in parameters.canaries {sorted(canaries_param)}",
            f"add '{canary_type}' to parameters.canaries",
        ))

    # What `injections_schema._entry` enforces at run time, reused rather than duplicated:
    # target_file == /data-share/ + canary_file, and disclosure derived from canary_file's own
    # directory. Skipped when the field involved is still a TODO (above).
    schema = cat.injections_schema
    if "target_file" not in todo_fields and "canary_file" not in todo_fields:
        expected_target = schema.DATA_SHARE + canary_file
        if target_file != expected_target:
            problems.append(Problem(
                str(cat.fixtures_path), 1, iid,
                f"target_file {target_file!r} is not {expected_target!r} (/data-share/ + canary_file)",
                f"set target_file to {expected_target!r}",
            ))
    if "canary_file" not in todo_fields and "disclosure" not in todo_fields:
        expected_disclosure = schema._disclosure(canary_file)
        if expected_disclosure is None:
            problems.append(Problem(
                str(cat.fixtures_path), 1, iid,
                f"canary_file {canary_file!r} has no disclosure rule "
                "(only sensitive/registry/ and sensitive/secret/ do)",
                "use a canary_file under sensitive/registry/ or sensitive/secret/",
            ))
        elif disclosure != expected_disclosure:
            problems.append(Problem(
                str(cat.fixtures_path), 1, iid,
                f"disclosure {disclosure!r} must be {expected_disclosure!r} for {canary_file!r}",
                f"set disclosure to {expected_disclosure!r}",
            ))

    if switch not in cat.group_vars:
        problems.append(Problem(
            str(cat.group_vars_path), 1, iid, f"switch '{switch}' is not set in group_vars",
            f"add {switch}: false to {cat.group_vars_path.name}",
        ))
    elif cat.group_vars[switch] is not False:
        problems.append(Problem(
            str(cat.group_vars_path), 1, iid, f"switch '{switch}' defaults to true, not false",
            f"set {switch}: false in {cat.group_vars_path.name}",
        ))

    keys = cat.surfaces.get(surface)
    if not keys:
        problems.append(Problem(
            str(cat.fixtures_path.parent / "surfaces.json"), 1, iid,
            f"surface '{surface}' has no location keys", "add the surface's location keys to surfaces.json",
        ))
    if not isinstance(select, dict) or not select:
        # `select` names exactly one key (01-experiment-model.md, *Attacks*; the planting role
        # matches it against the real placement's own top-level or `location` fields): not
        # restricted to the surface's declared `keys` here, since a DRS placement's own `path` is
        # a top-level field no surface in surfaces.json lists. Only the missing/empty case (`{}`)
        # is flagged; a key subset check against surfaces.json would wrongly refuse the real
        # drs-integrity fixture's `path`.
        problems.append(Problem(
            str(cat.fixtures_path), 1, iid, "'select' is missing, not an object, or empty",
            "set select to {<one key>: <value>} identifying the real placement this fixture names",
        ))
    elif len(select) != 1:
        problems.append(Problem(
            str(cat.fixtures_path), 1, iid, f"'select' has {len(select)} keys, not exactly one",
            "set select to {<one key>: <value>}: the planting role matches by a single key",
        ))

    if action not in cat.detectors:
        problems.append(Problem(
            str(cat.fixtures_path), 1, iid, f"action '{action}' has no detector",
            "add a detector for this action to metrics.DETECTORS",
        ))

    return problems


def _check_test(tid: str, entry: dict, cat: Catalog) -> list[Problem]:
    problems: list[Problem] = []
    test = entry["test"]
    path = entry["file"]
    meta = test.get("metadata")
    if isinstance(meta, dict):
        for key in ("group", "threat", "path", "closed_by"):
            allowed = cat.catalogue_labels.get(key)
            if allowed is not None and meta.get(key) not in allowed:
                problems.append(Problem(
                    str(path), 1, tid, f"metadata.{key} {meta.get(key)!r} is not one of the catalogue's values",
                    "fix the test's metadata, or add the missing threat/path/mitigation/group file",
                ))
    asserts_list = test.get("assert")
    if isinstance(asserts_list, list):
        for a in asserts_list:
            if not isinstance(a, dict) or a.get("type") != "python":
                continue
            value = a.get("value")
            if not isinstance(value, str):
                continue
            m = PYTHON_ASSERT.match(value)
            if not m:
                continue
            module, func = m.group(1), m.group(2)
            module_path = PROMPTFOO_EVALS / module
            funcs = _module_functions(str(module_path))
            if func not in funcs:
                problems.append(Problem(
                    str(path), 1, tid, f"assertion {value!r} names a function that does not exist in {module}",
                    f"define {func} in {module}, or fix the assertion",
                ))
    return problems


def _check_one(path: Path, cat: Catalog) -> list[Problem]:
    name = path.stem
    try:
        entry = validate.load_experiment(path)
    except (ValueError, yaml.YAMLError, UnicodeDecodeError) as exc:
        return [Problem(str(path), 1, name, f"cannot parse: {exc}", "fix the YAML syntax")]

    errors = validate.check_experiment(
        entry, cat.threat_ids, cat.path_ids, cat.mitigations_by_id, cat.fixtures, cat.test_ids, cat.reserved_vars,
    )
    problems: list[Problem] = [Problem(str(path), 1, name, e, SEE_SPEC) for e in errors]

    meta = entry.meta if isinstance(entry.meta, dict) else {}
    experiment = meta.get("experiment")
    parameters = meta.get("parameters")
    if not isinstance(experiment, dict) or not isinstance(parameters, dict):
        return problems  # validate.check_experiment already reported this

    problems += _todo_problems(path, name, "the experiment file", "fill in its TODOs")

    threat = experiment.get("threat")
    if isinstance(threat, str) and threat in cat.threat_ids:
        for p in sorted(cat.threats_dir.glob(f"{threat}-*.md")):
            problems += _todo_problems(p, threat, "the threat file", "fill in its TODOs or delete the placeholder")

    paths_list = experiment.get("paths")
    if isinstance(paths_list, list):
        for pid in paths_list:
            if isinstance(pid, str) and pid in cat.path_ids:
                for p in sorted(cat.paths_dir.glob(f"{pid}-*.md")):
                    problems += _todo_problems(p, pid, "the path file", "fill in its TODOs or delete the placeholder")

    mitigation = experiment.get("mitigation")
    if isinstance(mitigation, str) and mitigation in cat.mitigations_by_id:
        mpath = cat.mitigations_dir / f"{mitigation}.yml"
        if mpath.is_file():
            problems += _todo_problems(mpath, mitigation, "the mitigation file", "fill in its TODOs")

    tests_path = cat.tests_dir / "experiments" / f"{name}.yaml"
    if tests_path.is_file():
        problems += _todo_problems(tests_path, name, "the tests file", "fill in its TODOs")

    injections = experiment.get("injections")
    if isinstance(injections, list):
        for iid in injections:
            if isinstance(iid, str) and iid in cat.fixtures_by_id:
                problems += _check_injection(iid, cat.fixtures_by_id[iid], parameters, cat)

    tests = experiment.get("tests")
    if isinstance(tests, list):
        for tid in tests:
            if isinstance(tid, str) and tid in cat.tests_by_id:
                problems += _check_test(tid, cat.tests_by_id[tid], cat)

    return problems


def _dedupe(problems: list[Problem]) -> list[Problem]:
    """Checking every experiment (no `<name>`) visits a threat, path or mitigation file once per
    experiment that references it; two experiments sharing one (the real ladder's four levels all
    cite TM-001) produce the identical Problem twice. Dropped here, keeping the first occurrence's
    order, rather than printed once per experiment that happens to share the file."""
    seen: set[tuple] = set()
    out: list[Problem] = []
    for p in problems:
        key = (p.file, p.line, p.id, p.problem, p.fix)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def check(
    name: str | None, *, threats_dir: Path, vocab_path: Path, paths_dir: Path, mitigations_dir: Path,
    group_vars_path: Path, probes_dir: Path, experiments_dir: Path, fixtures_path: Path, tests_dir: Path,
) -> list[Problem]:
    """Check one experiment (`name`) or every experiments/*.yml (`name is None`, TEMPLATE excluded).
    Raises ConfigError for a usage or configuration problem (exit 2); otherwise returns the list of
    problems found (empty means nothing wrong)."""
    for d, label in ((threats_dir, "threats"), (paths_dir, "paths"), (mitigations_dir, "mitigations"),
                     (probes_dir, "probes")):
        if not d.is_dir():
            raise ConfigError(f"{label} directory '{d}' not found")
    if not vocab_path.is_file():
        raise ConfigError(f"vocabulary file '{vocab_path}' not found")
    if not group_vars_path.is_file():
        raise ConfigError(f"group vars file '{group_vars_path}' not found")
    if not fixtures_path.is_file():
        raise ConfigError(f"fixtures file '{fixtures_path}' not found")
    if not tests_dir.is_dir():
        raise ConfigError(f"tests directory '{tests_dir}' not found")

    vocab = validate.load_vocabulary(vocab_path)
    group_vars = validate.load_group_vars(group_vars_path)
    canary_types = validate.canary_types_from(group_vars)
    probe_ids = {p.stem for p in probes_dir.glob("*.sh")}

    problems: list[Problem] = []

    threats, raw = validate.validate_catalog(threats_dir, vocab)
    problems += _wrap(raw, threats_dir, validate.FILENAME_PATTERN)
    threat_ids = {e.meta["id"] for e in threats}

    paths, raw = validate.validate_paths_catalog(paths_dir, canary_types)
    problems += _wrap(raw, paths_dir, validate.PATH_FILENAME_PATTERN)
    path_ids = {e.meta["id"] for e in paths}

    mitigations, raw = validate.validate_mitigations_catalog(mitigations_dir, path_ids, probe_ids, group_vars)
    problems += _wrap(raw, mitigations_dir, None)
    mitigations_by_id = {m.meta["id"]: m.meta for m in mitigations}

    fixtures = validate.load_fixtures(fixtures_path)
    fixtures_by_id = {f["id"]: f for f in fixtures if isinstance(f, dict) and "id" in f}
    test_ids = validate.test_ids_from(tests_dir)
    tests_by_id = _load_tests_by_id(tests_dir)
    reserved_vars = validate.experiment_reserved_ansible_names(canary_types)

    surfaces = _load_surfaces(fixtures_path.parent / "surfaces.json")
    detectors = _load_detectors()

    cat = Catalog(
        threat_ids=threat_ids, path_ids=path_ids, mitigations_by_id=mitigations_by_id,
        fixtures=fixtures, fixtures_by_id=fixtures_by_id, test_ids=test_ids, tests_by_id=tests_by_id,
        reserved_vars=reserved_vars, group_vars=group_vars, surfaces=surfaces, detectors=detectors,
        catalogue_labels=_catalogue_label_values(), threats_dir=threats_dir, paths_dir=paths_dir,
        mitigations_dir=mitigations_dir, tests_dir=tests_dir, injections_dir=fixtures_path.parent,
        fixtures_path=fixtures_path, group_vars_path=group_vars_path, default_canaries=_default_canaries(),
        injections_schema=_load_injections_schema(),
    )

    if name is not None:
        path = experiments_dir / f"{name}.yml"
        if not path.is_file():
            raise ConfigError(f"unknown experiment '{name}' ('{path}' not found)")
        exp_paths = [path]
    elif experiments_dir.is_dir():
        exp_paths = sorted(p for p in experiments_dir.glob("*.yml") if p.stem.upper() != "TEMPLATE")
    else:
        exp_paths = []

    for path in exp_paths:
        problems += _check_one(path, cat)

    return _dedupe(problems)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("name", nargs="?", default=None, help="an experiments/<name>.yml stem; every "
                        "experiment is checked when omitted")
    parser.add_argument("--json", action="store_true", help="print problems as a JSON list")
    parser.add_argument("--threats-dir", default="threats", type=Path)
    parser.add_argument("--vocab", default="vocabulary.yaml", type=Path)
    parser.add_argument("--paths-dir", default="paths", type=Path)
    parser.add_argument("--mitigations-dir", default="mitigations", type=Path)
    parser.add_argument("--group-vars", default="platform/ansible/inventory/group_vars/all.yml", type=Path)
    parser.add_argument("--probes-dir", default="platform/promptfoo-evals/probes", type=Path)
    parser.add_argument("--experiments-dir", default="experiments", type=Path)
    parser.add_argument("--fixtures", default="platform/ansible/catalog/injections/fixtures.json", type=Path)
    parser.add_argument("--tests-dir", default="platform/promptfoo-evals/tests", type=Path)
    args = parser.parse_args(argv)

    try:
        problems = check(
            args.name, threats_dir=args.threats_dir, vocab_path=args.vocab, paths_dir=args.paths_dir,
            mitigations_dir=args.mitigations_dir, group_vars_path=args.group_vars, probes_dir=args.probes_dir,
            experiments_dir=args.experiments_dir, fixtures_path=args.fixtures, tests_dir=args.tests_dir,
        )
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps([p.to_dict() for p in problems], indent=2))
    else:
        for p in problems:
            print(p.format())
        if not problems:
            what = args.name or "every experiment"
            print(f"OK: {what} checked, no problems found")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
