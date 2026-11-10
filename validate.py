#!/usr/bin/env python3
"""Validate the experiment catalog: threats, paths and mitigations.

Checks per threat (threats/TM-*.md):
  - frontmatter parses, all required fields are present, and no other
    fields are present (the format is fixed; see threats/TEMPLATE.md)
  - `id` has format TM-NNN and matches the filename prefix
  - no duplicate IDs across the catalog
  - `status` is one vocabulary.yaml value; `entry-points`, `assets` and
    `stride` are non-empty lists of vocabulary.yaml values
  - the body has exactly the headings of the template, in order

Checks per path (paths/P<n>-*.md), the same shape as a threat (see
paths/TEMPLATE.md):
  - frontmatter parses, all required fields are present, and no other
    fields are present
  - `id` has format P<n> and matches the filename prefix; no duplicates
  - `reaches` is a non-empty list of canary types (the `spe_canary_<type>`
    keys of platform/ansible/inventory/group_vars/all.yml)
  - the body has exactly the headings `## Route`, `## Shown by`, in order

Checks per mitigation (mitigations/<id>.yml):
  - only the allowed keys are present; `id` equals the file stem
  - `closes` names existing paths; `requires` and `conflicts` name existing
    mitigations; `probes` names existing controls probes
    (platform/promptfoo-evals/probes/*.sh)
  - without `status: planned`, `on` and `off` are both non-empty mappings
    with the same keys; with it, neither is present
  - `off` equals the default of each key in group_vars/all.yml (a build with
    every mitigation off is today's build)
  - no two mitigations set the same key in `on` (one owner per Ansible key)

Checks per experiment (experiments/<name>.yml), optional: a missing directory
is fine (no experiments yet). See docs/specs/2026-11-10-experiments-design/
01-experiment-model.md, *Experiments*:
  - only the allowed top-level keys are present; `parameters.experiment`
    equals the file stem
  - every key in `parameters` is a parameter the spe-experiments template
    defines (EXPERIMENT_PARAMETER_ANSIBLE_NAMES)
  - `experiment.threat` is a known threat id; `experiment.paths` names known
    paths
  - `experiment.mitigation` (unless null) and every id in `experiment.base`
    name a mitigation that exists and is not `status: planned`; the
    mitigation under test is not also in `base`
  - `parameters.mitigations` equals `experiment.base` (as sets)
  - `experiment.injections` names known fixtures.json entries
  - `experiment.tests` names known test ids (`metadata.id` in
    platform/promptfoo-evals/tests/*.yaml and tests/experiments/*.yaml)
  - `experiment.base`'s and, if set, `experiment.mitigation`'s `requires`
    and `conflicts` are satisfied within each arm (baseline: `base`;
    mitigated: `base` plus `mitigation`)
  - no `vars` key is also set by any catalog mitigation's `on`, any
    fixtures.json entry's `switch`, or the template's own parameter Ansible
    names, selected by this experiment or not (one place per value)
  - across the catalog: no two experiments share a `name`; at most one has
    `default: true`; `ladder-l0.yml` is present whenever the directory holds
    anything at all (main.tf hard-codes it as the form's defaults)

Usage:
    python validate.py [--threats-dir threats] [--vocab vocabulary.yaml]
                        [--paths-dir paths] [--mitigations-dir mitigations]
                        [--group-vars platform/ansible/inventory/group_vars/all.yml]
                        [--probes-dir platform/promptfoo-evals/probes]
                        [--experiments-dir experiments]
                        [--fixtures platform/ansible/catalog/injections/fixtures.json]
                        [--tests-dir platform/promptfoo-evals/tests]

Exit code 0 if all checks pass, 1 otherwise. platform/site/build.py imports
`validate_catalog` and `load_vocabulary` to build the catalog page.

Dependencies:
    pip install pyyaml
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

ID_PATTERN = re.compile(r"^TM-\d{3}$")
FILENAME_PATTERN = re.compile(r"^(TM-\d{3})-[a-z0-9-]+\.md$")
HEADING_PATTERN = re.compile(r"^(#{1,3}) (.+?)\s*$", re.MULTILINE)

REQUIRED_FIELDS = [
    "id",
    "name",
    "description",
    "status",
    "entry-points",
    "assets",
    "stride",
]

# frontmatter field -> vocabulary.yaml section
SCALAR_VOCAB_FIELDS = {"status": "status"}
VOCAB_FIELDS = {
    "entry-points": "entry-points",
    "assets": "assets",
    "stride": "stride",
}

# (level, text) of every heading, in order; the H1 text is checked separately.
BODY_HEADINGS = [
    (2, "Attack Scenarios"),
    (2, "Preconditions"),
    (2, "Mitigations"),
    (3, "Preventive"),
    (3, "Detective"),
    (3, "Responsive"),
]

PATH_ID_PATTERN = re.compile(r"^P\d+$")
PATH_FILENAME_PATTERN = re.compile(r"^(P\d+)-[a-z0-9-]+\.md$")
PATH_REQUIRED_FIELDS = ["id", "name", "description", "reaches"]
PATH_BODY_HEADINGS = [(2, "Route"), (2, "Shown by")]

MITIGATION_ID_PATTERN = re.compile(r"^(?:L\d+|[a-z0-9]+(?:-[a-z0-9]+)*)$")
MITIGATION_REQUIRED_FIELDS = ["id", "name", "description", "closes"]
MITIGATION_OPTIONAL_FIELDS = ["on", "off", "requires", "conflicts", "probes", "status"]
MITIGATION_ALLOWED_FIELDS = MITIGATION_REQUIRED_FIELDS + MITIGATION_OPTIONAL_FIELDS

EXPERIMENT_REQUIRED_FIELDS = ["name", "description", "parameters", "experiment"]
EXPERIMENT_OPTIONAL_FIELDS = ["default", "vars"]
EXPERIMENT_ALLOWED_FIELDS = EXPERIMENT_REQUIRED_FIELDS + EXPERIMENT_OPTIONAL_FIELDS
EXPERIMENT_BLOCK_REQUIRED_FIELDS = ["threat", "paths", "mitigation", "base", "injections", "tests"]

# The spe-experiments template's own parameter -> Ansible name (01-experiment-model.md,
# *Experiments*: "vars" exists for build settings the form does not offer, and a vars key that a
# parameter also sets is refused). `canaries` has no single name: it expands to one
# spe_canary_<type> key per canary type, added by experiment_reserved_ansible_names below.
# The Coder template (platform/coder/experiments-template/main.tf) hard-codes its own matching
# parameter names; test_validate.py checks this dict's keys against them, so they cannot drift.
EXPERIMENT_PARAMETER_ANSIBLE_NAMES: dict[str, str | None] = {
    "experiment": "spe_experiment",
    "mitigations": "spe_mitigations",
    "samples": "spe_samples",
    "tiers": "spe_tiers",
    "workflows": "spe_workflows",
    "canaries": None,
    "flavor": "spe_flavor",
    "smoke_test": "spe_run_smoke_test",
}
# Names the template reserves with no single matching parameter key above: the seed (a parameter,
# but never set from an experiment file, since the seed is secret), the flag that marks a build as
# made by this template (spe_experiments), the keys main.tf passes alongside the parameters
# (spe_instance, the spe_coder_* identity keys), and the list of keys persisted into local.yml for
# spe-apply and Rebuild to re-apply (spe_local_vars_extra).
EXPERIMENT_TEMPLATE_RESERVED_NAMES = frozenset({
    "spe_seed", "spe_experiments", "spe_local_vars_extra", "spe_instance",
    "spe_coder_owner", "spe_coder_owner_email", "spe_coder_workspace", "spe_coder_workspace_id",
    "spe_coder_agent_token", "spe_coder_init_script",
})


def experiment_reserved_ansible_names(canary_types: set[str]) -> set[str]:
    """Ansible names the spe-experiments template's own parameters set. An experiment's `vars`
    must not set any of them: one place per value (01-experiment-model.md)."""
    names = {v for v in EXPERIMENT_PARAMETER_ANSIBLE_NAMES.values() if v} | set(EXPERIMENT_TEMPLATE_RESERVED_NAMES)
    names |= {f"spe_canary_{t}" for t in canary_types}
    return names


@dataclass
class Entry:
    path: Path
    meta: dict
    body: str


@dataclass
class Mitigation:
    path: Path
    meta: dict


@dataclass
class ExperimentEntry:
    path: Path
    meta: dict


def load_vocabulary(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        vocab = yaml.safe_load(f)
    for section in [*SCALAR_VOCAB_FIELDS.values(), *VOCAB_FIELDS.values()]:
        if section not in vocab or not isinstance(vocab[section], dict):
            sys.exit(f"vocabulary file {path} is missing section '{section}'")
        # Guard against a silently broken/emptied vocabulary.
        if len(vocab[section]) == 0:
            sys.exit(f"vocabulary section '{section}' in {path} is empty")
    return vocab


def split_frontmatter(text: str) -> tuple[dict, str]:
    """Split '---\\n<yaml>\\n---\\n<body>' into (metadata, body)."""
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        raise ValueError("file does not start with a '---' frontmatter block")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("frontmatter block is not closed by a '---' line")
    meta = yaml.safe_load(text[4:end])
    if not isinstance(meta, dict):
        raise ValueError("frontmatter is not a YAML mapping")
    return meta, text[end + 5:]


def load_entry(path: Path) -> Entry:
    meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
    return Entry(path=path, meta=meta, body=body)


def check_entry(entry: Entry, vocab: dict) -> list[str]:
    errors = []
    meta = entry.meta
    path = entry.path

    for field in REQUIRED_FIELDS:
        if field not in meta:
            errors.append(f"missing required field '{field}'")
    for field in meta:
        if field not in REQUIRED_FIELDS:
            errors.append(
                f"unknown field '{field}' (allowed: {', '.join(REQUIRED_FIELDS)})"
            )
    if errors:
        return errors  # further checks need the fields

    entry_id = meta["id"]
    if not isinstance(entry_id, str) or not ID_PATTERN.match(entry_id):
        errors.append(f"id '{entry_id}' does not match format TM-NNN")

    m = FILENAME_PATTERN.match(path.name)
    if not m:
        errors.append(
            f"filename '{path.name}' does not match pattern TM-NNN-short-slug.md"
        )
    elif m.group(1) != entry_id:
        errors.append(
            f"filename prefix '{m.group(1)}' does not match id '{entry_id}'"
        )

    for field in ("name", "description"):
        if not isinstance(meta[field], str) or not meta[field].strip():
            errors.append(f"'{field}' must be a non-empty string")

    for field, section in SCALAR_VOCAB_FIELDS.items():
        if meta[field] not in vocab[section]:
            errors.append(
                f"unknown {field} value '{meta[field]}' "
                f"(not in vocabulary.yaml [{section}])"
            )

    for field, section in VOCAB_FIELDS.items():
        values = meta[field]
        if not isinstance(values, list) or not values:
            errors.append(f"'{field}' must be a non-empty list")
            continue
        for value in values:
            if value not in vocab[section]:
                errors.append(
                    f"unknown {field} value '{value}' "
                    f"(not in vocabulary.yaml [{section}])"
                )

    errors.extend(check_body(entry.body, entry_id, meta["name"]))
    return errors


def check_body(content: str, entry_id: str, name: str) -> list[str]:
    return check_body_headings(content, f"{entry_id}: {name}", BODY_HEADINGS)


def check_body_headings(content: str, expected_h1: str, headings: list[tuple[int, str]]) -> list[str]:
    """Shared by threats and paths: an H1 of '<id>: <name>', then exactly `headings`."""
    found = [(len(h), text) for h, text in HEADING_PATTERN.findall(content)]
    if not found or found[0][0] != 1:
        return ["body must start with the heading '# <id>: <name>'"]
    errors = []
    if found[0][1] != expected_h1:
        errors.append(f"H1 is '{found[0][1]}', expected '{expected_h1}'")
    if found[1:] != headings:
        expected = ", ".join(f"{'#' * lvl} {t}" for lvl, t in headings)
        got = ", ".join(f"{'#' * lvl} {t}" for lvl, t in found[1:])
        errors.append(
            f"body headings must be exactly [{expected}] in that order; "
            f"found [{got}]"
        )
    return errors


def check_path_entry(entry: Entry, canary_types: set[str]) -> list[str]:
    errors = []
    meta = entry.meta
    path = entry.path

    for field in PATH_REQUIRED_FIELDS:
        if field not in meta:
            errors.append(f"missing required field '{field}'")
    for field in meta:
        if field not in PATH_REQUIRED_FIELDS:
            errors.append(
                f"unknown field '{field}' (allowed: {', '.join(PATH_REQUIRED_FIELDS)})"
            )
    if errors:
        return errors  # further checks need the fields

    entry_id = meta["id"]
    if not isinstance(entry_id, str) or not PATH_ID_PATTERN.match(entry_id):
        errors.append(f"id '{entry_id}' does not match format P<n>")

    m = PATH_FILENAME_PATTERN.match(path.name)
    if not m:
        errors.append(
            f"filename '{path.name}' does not match pattern P<n>-short-slug.md"
        )
    elif m.group(1) != entry_id:
        errors.append(
            f"filename prefix '{m.group(1)}' does not match id '{entry_id}'"
        )

    for field in ("name", "description"):
        if not isinstance(meta[field], str) or not meta[field].strip():
            errors.append(f"'{field}' must be a non-empty string")

    reaches = meta["reaches"]
    if not isinstance(reaches, list) or not reaches:
        errors.append("'reaches' must be a non-empty list")
    else:
        for value in reaches:
            if value not in canary_types:
                errors.append(
                    f"unknown reaches value '{value}' "
                    f"(not a canary type of group_vars/all.yml)"
                )

    if isinstance(entry_id, str) and isinstance(meta.get("name"), str):
        errors.extend(check_body_headings(entry.body, f"{entry_id}: {meta['name']}", PATH_BODY_HEADINGS))
    return errors


def check_catalog(entries: list[Entry]) -> list[str]:
    """Cross-entry checks: duplicate ids."""
    errors = []
    ids_seen: dict[str, str] = {}
    for entry in entries:
        entry_id = entry.meta.get("id")
        if entry_id in ids_seen:
            errors.append(
                f"duplicate id '{entry_id}' in {entry.path.name} "
                f"and {ids_seen[entry_id]}"
            )
        else:
            ids_seen[entry_id] = entry.path.name
    return errors


def validate_catalog(threats_dir: Path, vocab: dict) -> tuple[list[Entry], list[str]]:
    """Load and check every TM-*.md. Returns (valid entries, problems).

    Each problem is one line, '<file>: <message>'. The entries list holds only
    the entries that passed their own checks, sorted by filename.
    """
    files = sorted(threats_dir.glob("TM-*.md"))
    if not files:
        return [], [f"no TM-*.md files found in '{threats_dir}'"]

    entries: list[Entry] = []
    problems: list[str] = []
    for path in files:
        try:
            entry = load_entry(path)
        except (ValueError, yaml.YAMLError, UnicodeDecodeError) as exc:
            problems.append(f"{path.name}: cannot parse frontmatter: {exc}")
            continue
        errors = check_entry(entry, vocab)
        if errors:
            problems.extend(f"{path.name}: {err}" for err in errors)
        else:
            entries.append(entry)

    problems.extend(f"catalog: {err}" for err in check_catalog(entries))
    return entries, problems


def validate_paths_catalog(paths_dir: Path, canary_types: set[str]) -> tuple[list[Entry], list[str]]:
    """Load and check every P<n>-*.md. Returns (valid entries, problems), as validate_catalog does."""
    files = sorted(paths_dir.glob("P*.md"))
    if not files:
        return [], [f"no P<n>-*.md files found in '{paths_dir}'"]

    entries: list[Entry] = []
    problems: list[str] = []
    for path in files:
        try:
            entry = load_entry(path)
        except (ValueError, yaml.YAMLError, UnicodeDecodeError) as exc:
            problems.append(f"{path.name}: cannot parse frontmatter: {exc}")
            continue
        errors = check_path_entry(entry, canary_types)
        if errors:
            problems.extend(f"{path.name}: {err}" for err in errors)
        else:
            entries.append(entry)

    problems.extend(f"catalog: {err}" for err in check_catalog(entries))
    return entries, problems


def load_group_vars(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        group_vars = yaml.safe_load(f)
    if not isinstance(group_vars, dict):
        sys.exit(f"group vars file {path} is not a YAML mapping")
    return group_vars


def canary_types_from(group_vars: dict) -> set[str]:
    """The canary types this stack supports: the spe_canary_<type> keys of group_vars/all.yml."""
    types = {key[len("spe_canary_"):] for key in group_vars if key.startswith("spe_canary_")}
    if not types:
        sys.exit("no spe_canary_* keys found in group vars")
    return types


def load_mitigation(path: Path) -> Mitigation:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("file is not a YAML mapping")
    return Mitigation(path=path, meta=data)


def check_mitigation(mitigation: Mitigation, path_ids: set[str], mitigation_ids: set[str],
                      probe_ids: set[str], group_vars: dict) -> list[str]:
    errors = []
    meta = mitigation.meta
    stem = mitigation.path.stem

    for field in MITIGATION_REQUIRED_FIELDS:
        if field not in meta:
            errors.append(f"missing required field '{field}'")
    for field in meta:
        if field not in MITIGATION_ALLOWED_FIELDS:
            errors.append(
                f"unknown field '{field}' (allowed: {', '.join(MITIGATION_ALLOWED_FIELDS)})"
            )
    if errors:
        return errors  # further checks need the fields

    entry_id = meta["id"]
    if not isinstance(entry_id, str) or not MITIGATION_ID_PATTERN.match(entry_id):
        errors.append(f"id '{entry_id}' does not match format L<n> or kebab-case")
    elif entry_id != stem:
        errors.append(f"id '{entry_id}' does not match filename stem '{stem}'")

    for field in ("name", "description"):
        if not isinstance(meta[field], str) or not meta[field].strip():
            errors.append(f"'{field}' must be a non-empty string")

    closes = meta["closes"]
    if not isinstance(closes, list):
        errors.append("'closes' must be a list")
    else:
        for value in closes:
            if value not in path_ids:
                errors.append(f"closes unknown path '{value}'")

    for field in ("requires", "conflicts"):
        if field not in meta:
            continue
        values = meta[field]
        if not isinstance(values, list):
            errors.append(f"'{field}' must be a list")
            continue
        for value in values:
            if value == entry_id:
                errors.append(f"'{field}' names itself '{value}'")
            elif value not in mitigation_ids:
                errors.append(f"{field} names unknown mitigation '{value}'")

    if "probes" in meta:
        values = meta["probes"]
        if not isinstance(values, list):
            errors.append("'probes' must be a list")
        else:
            for value in values:
                if value not in probe_ids:
                    errors.append(f"probes names unknown probe '{value}'")

    status = meta.get("status")
    if "status" in meta and status != "planned":
        errors.append(f"unknown status '{status}' (only 'planned' is allowed)")

    has_on, has_off = "on" in meta, "off" in meta
    if status == "planned":
        if has_on or has_off:
            errors.append("a planned mitigation must not have 'on' or 'off'")
    elif not has_on or not has_off:
        errors.append("'on' and 'off' are required unless status: planned")
    else:
        on, off = meta["on"], meta["off"]
        if not isinstance(on, dict) or not on:
            errors.append("'on' must be a non-empty mapping")
        if not isinstance(off, dict) or not off:
            errors.append("'off' must be a non-empty mapping")
        if isinstance(on, dict) and isinstance(off, dict) and on and off:
            if set(on) != set(off):
                errors.append(
                    f"'on' and 'off' must have the same keys; found on={sorted(on)}, off={sorted(off)}"
                )
            for key, value in off.items():
                if key not in group_vars:
                    errors.append(f"off key '{key}' is not in group_vars/all.yml")
                elif group_vars[key] != value:
                    errors.append(
                        f"off['{key}']={value!r} does not match the group_vars default {group_vars[key]!r}"
                    )
    return errors


def check_mitigations_catalog(mitigations: list[Mitigation]) -> list[str]:
    """Cross-mitigation checks: duplicate ids, one owner per 'on' Ansible key,
    unless the pair declares the overlap in 'conflicts' (either direction)."""
    errors = []
    ids_seen: dict[str, str] = {}
    conflicts_by_id = {
        m.meta.get("id"): set(m.meta.get("conflicts") or []) for m in mitigations
    }
    owners: dict[str, tuple[str, str]] = {}  # Ansible key -> (mitigation id, filename)
    for m in mitigations:
        entry_id = m.meta.get("id")
        if entry_id in ids_seen:
            errors.append(f"duplicate id '{entry_id}' in {m.path.name} and {ids_seen[entry_id]}")
        else:
            ids_seen[entry_id] = m.path.name

        on = m.meta.get("on")
        if isinstance(on, dict):
            for key in on:
                if key not in owners:
                    owners[key] = (entry_id, m.path.name)
                    continue
                other_id, other_name = owners[key]
                if other_id == entry_id:
                    continue
                declared = (
                    entry_id in conflicts_by_id.get(other_id, set())
                    or other_id in conflicts_by_id.get(entry_id, set())
                )
                if not declared:
                    errors.append(f"Ansible key '{key}' is set in both {other_name} and {m.path.name}")
    return errors


def validate_mitigations_catalog(mitigations_dir: Path, path_ids: set[str], probe_ids: set[str],
                                  group_vars: dict) -> tuple[list[Mitigation], list[str]]:
    """Load and check every <id>.yml. Returns (valid mitigations, problems), as validate_catalog does."""
    files = sorted(mitigations_dir.glob("*.yml"))
    if not files:
        return [], [f"no *.yml files found in '{mitigations_dir}'"]

    raw: list[Mitigation] = []
    problems: list[str] = []
    for path in files:
        try:
            mitigation = load_mitigation(path)
        except (ValueError, yaml.YAMLError, UnicodeDecodeError) as exc:
            problems.append(f"{path.name}: cannot parse: {exc}")
            continue
        raw.append(mitigation)

    mitigation_ids = {m.meta["id"] for m in raw if isinstance(m.meta, dict) and "id" in m.meta}

    mitigations: list[Mitigation] = []
    for mitigation in raw:
        errors = check_mitigation(mitigation, path_ids, mitigation_ids, probe_ids, group_vars)
        if errors:
            problems.extend(f"{mitigation.path.name}: {err}" for err in errors)
        else:
            mitigations.append(mitigation)

    problems.extend(f"catalog: {err}" for err in check_mitigations_catalog(mitigations))
    return mitigations, problems


def load_fixtures(path: Path) -> list[dict]:
    """platform/ansible/catalog/injections/fixtures.json's 'fixtures' list."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("fixtures"), list):
        sys.exit(f"fixtures file {path} has no 'fixtures' list")
    return data["fixtures"]


def test_ids_from(tests_dir: Path) -> set[str]:
    """The kebab-case `metadata.id` of every test in tests_dir/*.yaml and tests_dir/experiments/*.yaml
    (platform/promptfoo-evals/tests/test_catalogue.py lints the same files; this only collects ids,
    a malformed file or test is simply not a source of valid ids here)."""
    ids: set[str] = set()
    files = sorted(tests_dir.glob("*.yaml")) + sorted((tests_dir / "experiments").glob("*.yaml"))
    for path in files:
        try:
            tests = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, UnicodeDecodeError):
            continue
        if not isinstance(tests, list):
            continue
        for test in tests:
            meta = test.get("metadata") if isinstance(test, dict) else None
            if isinstance(meta, dict) and isinstance(meta.get("id"), str):
                ids.add(meta["id"])
    return ids


def load_experiment(path: Path) -> ExperimentEntry:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("file is not a YAML mapping")
    return ExperimentEntry(path=path, meta=data)


def check_experiment(entry: ExperimentEntry, threat_ids: set[str], path_ids: set[str],
                      mitigations: dict[str, dict], fixtures: list[dict], test_ids: set[str],
                      reserved_vars: set[str]) -> list[str]:
    errors = []
    meta = entry.meta
    stem = entry.path.stem

    for field in EXPERIMENT_REQUIRED_FIELDS:
        if field not in meta:
            errors.append(f"missing required field '{field}'")
    for field in meta:
        if field not in EXPERIMENT_ALLOWED_FIELDS:
            errors.append(
                f"unknown field '{field}' (allowed: {', '.join(EXPERIMENT_ALLOWED_FIELDS)})"
            )
    if errors:
        return errors  # further checks need the fields

    parameters = meta["parameters"]
    if not isinstance(parameters, dict):
        errors.append("'parameters' must be a mapping")
        parameters = {}
    else:
        for key in parameters:
            if key not in EXPERIMENT_PARAMETER_ANSIBLE_NAMES:
                errors.append(
                    f"unknown parameters key '{key}' (not a spe-experiments template parameter: "
                    f"{', '.join(sorted(EXPERIMENT_PARAMETER_ANSIBLE_NAMES))})"
                )

    experiment = meta["experiment"]
    if not isinstance(experiment, dict):
        errors.append("'experiment' must be a mapping")
        experiment = {}
    else:
        missing = [f for f in EXPERIMENT_BLOCK_REQUIRED_FIELDS if f not in experiment]
        if missing:
            errors.append(f"'experiment' is missing {', '.join(missing)}")

    if errors:
        return errors  # further checks need both blocks complete

    exp_name = parameters.get("experiment")
    if exp_name != stem:
        errors.append(f"parameters.experiment '{exp_name}' does not match filename stem '{stem}'")

    threat = experiment["threat"]
    if threat not in threat_ids:
        errors.append(f"unknown threat '{threat}'")

    paths = experiment["paths"]
    if not isinstance(paths, list):
        errors.append("'experiment.paths' must be a list")
        paths = []
    for p in paths:
        if p not in path_ids:
            errors.append(f"unknown path '{p}'")

    mitigation = experiment["mitigation"]
    base = experiment["base"]
    if not isinstance(base, list):
        errors.append("'experiment.base' must be a list")
        base = []

    def usable(mitigation_id: str) -> bool:
        return mitigation_id in mitigations and mitigations[mitigation_id].get("status") != "planned"

    for mid in base:
        if not usable(mid):
            errors.append(f"unknown or planned mitigation '{mid}' in base")

    if mitigation is not None:
        if not usable(mitigation):
            errors.append(f"unknown or planned mitigation '{mitigation}'")
        if mitigation in base:
            errors.append(f"mitigation under test '{mitigation}' is also in base")

    parameters_mitigations = parameters.get("mitigations")
    if not isinstance(parameters_mitigations, list):
        errors.append("'parameters.mitigations' must be a list")
    elif set(parameters_mitigations) != set(base):
        errors.append(
            f"parameters.mitigations {sorted(parameters_mitigations)} does not match base {sorted(base)}"
        )

    injections = experiment["injections"]
    fixtures_by_id = {f["id"]: f for f in fixtures if isinstance(f, dict) and "id" in f}
    if not isinstance(injections, list):
        errors.append("'experiment.injections' must be a list")
        injections = []
    for iid in injections:
        if iid not in fixtures_by_id:
            errors.append(f"unknown injection '{iid}'")

    tests = experiment["tests"]
    if not isinstance(tests, list):
        errors.append("'experiment.tests' must be a list")
        tests = []
    for tid in tests:
        if tid not in test_ids:
            errors.append(f"unknown test '{tid}'")

    # requires/conflicts, checked within each arm: baseline is 'base'; mitigated is 'base' plus
    # the mitigation under test, when there is one (01-experiment-model.md, *Mitigations*).
    arms = {"baseline": set(base)}
    if mitigation is not None:
        arms["mitigated"] = set(base) | {mitigation}
    for arm_name, arm_set in arms.items():
        for mid in arm_set:
            m = mitigations.get(mid)
            if not m:
                continue  # already reported above as unknown/planned
            for req in m.get("requires") or []:
                if req not in arm_set:
                    errors.append(
                        f"mitigation '{mid}' requires '{req}', not in the {arm_name} arm {sorted(arm_set)}"
                    )
            for conf in m.get("conflicts") or []:
                if conf in arm_set:
                    errors.append(
                        f"mitigation '{mid}' conflicts with '{conf}', both in the {arm_name} arm {sorted(arm_set)}"
                    )

    # vars: one place per value. Collisions are checked against every mitigation's 'on' and
    # every fixture's 'switch' in the catalog, selected by this experiment or not (01-experiment-
    # model.md: "an injection's switch is set only through injections"), and against the
    # template's own parameter Ansible names (always reserved, selection or not).
    vars_ = meta.get("vars", {})
    if "vars" in meta and not isinstance(vars_, dict):
        errors.append("'vars' must be a mapping")
        vars_ = {}
    owned_by: dict[str, str] = {}
    for mid, m in mitigations.items():
        for key in (m.get("on") or {}):
            owned_by[key] = f"mitigation '{mid}'"
    for fixture in fixtures_by_id.values():
        if isinstance(fixture.get("switch"), str):
            owned_by[fixture["switch"]] = f"the switch of injection '{fixture.get('id')}'"
    for key in vars_:
        if key in owned_by:
            errors.append(f"vars key '{key}' is already set by {owned_by[key]}")
        elif key in reserved_vars:
            errors.append(f"vars key '{key}' is already set by a parameter")

    return errors


def check_experiments_catalog(entries: list[ExperimentEntry], experiments_dir: Path) -> list[str]:
    """Cross-experiment checks: duplicate names, more than one 'default: true', and ladder-l0.yml
    present whenever the directory holds anything at all (main.tf hard-codes
    local.experiments["ladder-l0"] as every workspace's form defaults)."""
    errors = []
    names_seen: dict[str, str] = {}
    defaults: list[str] = []
    for entry in entries:
        name = entry.meta.get("name")
        if name in names_seen:
            errors.append(f"duplicate name '{name}' in {entry.path.name} and {names_seen[name]}")
        else:
            names_seen[name] = entry.path.name
        if entry.meta.get("default"):
            defaults.append(entry.path.name)
    if len(defaults) > 1:
        errors.append(f"more than one experiment has 'default: true': {', '.join(sorted(defaults))}")
    if experiments_dir.is_dir() and any(experiments_dir.iterdir()) \
            and not (experiments_dir / "ladder-l0.yml").exists():
        errors.append("'ladder-l0.yml' is missing (main.tf hard-codes it as the form's defaults)")
    return errors


def validate_experiments_catalog(experiments_dir: Path, threat_ids: set[str], path_ids: set[str],
                                  mitigations: dict[str, dict], fixtures: list[dict], test_ids: set[str],
                                  reserved_vars: set[str]) -> tuple[list[ExperimentEntry], list[str]]:
    """Load and check every experiments/*.yml. Returns (valid entries, problems), as validate_catalog
    does. Unlike the other catalogs, an empty or absent directory is not itself a problem: callers
    check `experiments_dir.is_dir()` first (experiments are optional)."""
    files = sorted(experiments_dir.glob("*.yml"))
    entries: list[ExperimentEntry] = []
    problems: list[str] = []
    for path in files:
        try:
            entry = load_experiment(path)
        except (ValueError, yaml.YAMLError, UnicodeDecodeError) as exc:
            problems.append(f"{path.name}: cannot parse: {exc}")
            continue
        errors = check_experiment(entry, threat_ids, path_ids, mitigations, fixtures, test_ids, reserved_vars)
        if errors:
            problems.extend(f"{path.name}: {err}" for err in errors)
        else:
            entries.append(entry)
    problems.extend(f"catalog: {err}" for err in check_experiments_catalog(entries, experiments_dir))
    return entries, problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threats-dir", default="threats", type=Path)
    parser.add_argument("--vocab", default="vocabulary.yaml", type=Path)
    parser.add_argument("--paths-dir", default="paths", type=Path)
    parser.add_argument("--mitigations-dir", default="mitigations", type=Path)
    parser.add_argument(
        "--group-vars", default="platform/ansible/inventory/group_vars/all.yml", type=Path
    )
    parser.add_argument("--probes-dir", default="platform/promptfoo-evals/probes", type=Path)
    parser.add_argument("--experiments-dir", default="experiments", type=Path)
    parser.add_argument(
        "--fixtures", default="platform/ansible/catalog/injections/fixtures.json", type=Path
    )
    parser.add_argument("--tests-dir", default="platform/promptfoo-evals/tests", type=Path)
    args = parser.parse_args()

    if not args.threats_dir.is_dir():
        sys.exit(f"threats directory '{args.threats_dir}' not found")
    if not args.paths_dir.is_dir():
        sys.exit(f"paths directory '{args.paths_dir}' not found")
    if not args.mitigations_dir.is_dir():
        sys.exit(f"mitigations directory '{args.mitigations_dir}' not found")
    if not args.probes_dir.is_dir():
        sys.exit(f"probes directory '{args.probes_dir}' not found")

    vocab = load_vocabulary(args.vocab)
    group_vars = load_group_vars(args.group_vars)
    canary_types = canary_types_from(group_vars)
    probe_ids = {p.stem for p in args.probes_dir.glob("*.sh")}

    threats, problems = validate_catalog(args.threats_dir, vocab)

    paths, path_problems = validate_paths_catalog(args.paths_dir, canary_types)
    problems += path_problems
    path_ids = {entry.meta["id"] for entry in paths}

    mitigations, mitigation_problems = validate_mitigations_catalog(
        args.mitigations_dir, path_ids, probe_ids, group_vars
    )
    problems += mitigation_problems

    experiments: list[ExperimentEntry] = []
    if args.experiments_dir.is_dir():
        fixtures = load_fixtures(args.fixtures)
        test_ids = test_ids_from(args.tests_dir)
        threat_ids = {entry.meta["id"] for entry in threats}
        mitigations_by_id = {m.meta["id"]: m.meta for m in mitigations}
        reserved_vars = experiment_reserved_ansible_names(canary_types)
        experiments, experiment_problems = validate_experiments_catalog(
            args.experiments_dir, threat_ids, path_ids, mitigations_by_id, fixtures, test_ids, reserved_vars
        )
        problems += experiment_problems

    if problems:
        for line in problems:
            print(f"FAIL {line}")
        return 1
    print(
        f"OK: {len(threats)} threats, {len(paths)} paths, {len(mitigations)} mitigations, "
        f"{len(experiments)} experiments validated"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
