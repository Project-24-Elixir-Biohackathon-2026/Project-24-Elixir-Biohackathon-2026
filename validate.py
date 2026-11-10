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

Usage:
    python validate.py [--threats-dir threats] [--vocab vocabulary.yaml]
                        [--paths-dir paths] [--mitigations-dir mitigations]
                        [--group-vars platform/ansible/inventory/group_vars/all.yml]
                        [--probes-dir platform/promptfoo-evals/probes]

Exit code 0 if all checks pass, 1 otherwise. platform/site/build.py imports
`validate_catalog` and `load_vocabulary` to build the catalog page.

Dependencies:
    pip install pyyaml
"""

import argparse
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


@dataclass
class Entry:
    path: Path
    meta: dict
    body: str


@dataclass
class Mitigation:
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

    if problems:
        for line in problems:
            print(f"FAIL {line}")
        return 1
    print(f"OK: {len(threats)} threats, {len(paths)} paths, {len(mitigations)} mitigations validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
