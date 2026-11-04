#!/usr/bin/env python3
"""Validate threat model entries against vocabulary.yaml and conventions.

Checks per entry (threats/TM-*.md):
  - frontmatter parses, all required fields are present, and no other
    fields are present (the format is fixed; see threats/TEMPLATE.md)
  - `id` has format TM-NNN and matches the filename prefix
  - no duplicate IDs across the catalog
  - `status` is one vocabulary.yaml value; `entry-points`, `assets` and
    `stride` are non-empty lists of vocabulary.yaml values
  - the body has exactly the headings of the template, in order

Usage:
    python validate.py [--threats-dir threats] [--vocab vocabulary.yaml]

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


@dataclass
class Entry:
    path: Path
    meta: dict
    body: str


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
    headings = [(len(h), text) for h, text in HEADING_PATTERN.findall(content)]
    if not headings or headings[0][0] != 1:
        return ["body must start with the heading '# TM-NNN: Name'"]
    expected_h1 = f"{entry_id}: {name}"
    errors = []
    if headings[0][1] != expected_h1:
        errors.append(f"H1 is '{headings[0][1]}', expected '{expected_h1}'")
    if headings[1:] != BODY_HEADINGS:
        expected = ", ".join(f"{'#' * lvl} {t}" for lvl, t in BODY_HEADINGS)
        found = ", ".join(f"{'#' * lvl} {t}" for lvl, t in headings[1:])
        errors.append(
            f"body headings must be exactly [{expected}] in that order; "
            f"found [{found}]"
        )
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threats-dir", default="threats", type=Path)
    parser.add_argument("--vocab", default="vocabulary.yaml", type=Path)
    args = parser.parse_args()

    if not args.threats_dir.is_dir():
        sys.exit(f"threats directory '{args.threats_dir}' not found")
    vocab = load_vocabulary(args.vocab)

    entries, problems = validate_catalog(args.threats_dir, vocab)
    if problems:
        for line in problems:
            print(f"FAIL {line}")
        return 1
    print(f"OK: {len(entries)} entries validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
