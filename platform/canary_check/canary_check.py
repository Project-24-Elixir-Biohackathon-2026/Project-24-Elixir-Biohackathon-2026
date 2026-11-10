#!/usr/bin/env python3
"""Deterministic canary checker for SPE Range archives, chats and reports.

Scans text for canary tokens and reports where each one appears. It works from
the hash-only manifest (`canaries.manifest.sha256`, one `<sha256>\t<type>` line
per token) that the handoff role writes "safe to share with detection
tooling", so the checker never needs the plaintext canary record. Every
candidate substring of the scanned text is hashed and looked up in the manifest.

It also reports *canary-shaped* strings (the known token prefixes) that are not
in the manifest, for example a token from another instance pasted into a
report.

Inputs it understands:
  - .json / .jsonl   every string value is scanned (escapes decoded), with its JSON path
  - anything else    scanned as text, line by line
  - directories      walked recursively (an archived run directory, a reports folder)

Usage:
    python canary_check.py --manifest canaries.manifest.sha256 PATH [PATH ...]
    python canary_check.py --manifest m.sha256 --json PATH      # machine-readable
    python canary_check.py --shape-only PATH                    # no manifest: prefixes only

Exit code: 0 no finding, 1 at least one manifest hit, 2 usage error.
A shape-only finding does not change the exit code unless --strict is given.

Findings never print a full token: only its type, where it was found, and the
first characters of the match, so the checker's own output is safe to share.

Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator

# Maximal runs of characters that can occur inside a token (IDs, keys, URLs).
_RUN = re.compile(r"[A-Za-z0-9_\-+/=.:@%~]+")
# Separators used to split a run into smaller candidates (a token may sit
# inside a URL, a path or a key=value pair).
_SPLIT = re.compile(r"[/=:@.%~+]")
# Prefixes written by spe_seed.py, drs_register.py, trs_install.py and create.yml.
CANARY_SHAPE = re.compile(
    r"\b(?:HPCANARY|VCANARY|DRSMETA|TRSMETA|WFCANARY|SVCINFO|FLAG)-[A-Z0-9]{6,12}\b"
    r"|\bPLACEHOLDER_[A-Za-z0-9]{32}\b"
    r"|https://canarytokens\.org/traffic/PLACEHOLDER-[A-Za-z0-9]+/contact\.png"
)
_TEXT_SUFFIXES = {".md", ".txt", ".log", ".csv", ".tsv", ".html", ".yml", ".yaml", ".env", ""}
# The canary record itself sits in every archived run directory; scanning it
# would report every token. Skipped when walking a directory.
SKIP_NAMES = {"canaries.json", "canaries.json.age", "canaries.manifest.sha256"}


@dataclass
class Finding:
    kind: str          # "manifest" (exact hash match) or "shape" (prefix only)
    type: str          # canary type from the manifest, or "canary-shaped"
    file: str
    where: str         # "line 12" or a JSON path such as "$[3].content"
    preview: str       # first characters of the match, never the full token


def load_manifest(path: Path) -> dict[str, str]:
    """Return {sha256_hex: type} from a canaries.manifest.sha256 file."""
    hashes: dict[str, str] = {}
    for n, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        digest = parts[0].strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError(f"{path}:{n}: not a sha256 digest")
        hashes[digest] = parts[1].strip() if len(parts) > 1 else "unknown"
    return hashes


def candidates(text: str) -> Iterator[str]:
    """Every substring that could be a whole token: runs, their parts, and
    the runs with surrounding punctuation trimmed."""
    seen: set[str] = set()
    for m in _RUN.finditer(text):
        run = m.group(0)
        pieces = {run, run.strip(".:,;-_/")}
        pieces.update(p for p in _SPLIT.split(run) if p)
        # A run like "STUDY-0001.chr20.cram" must yield "STUDY-0001".
        for p in list(pieces):
            pieces.update(q for q in p.split(".") if q)
        # Hyphenated IDs: also try every prefix ending before a hyphen-free tail.
        for p in list(pieces):
            if "-" in p:
                head, _, _tail = p.rpartition("-")
                pieces.add(head)
        for p in pieces:
            if len(p) >= 4 and p not in seen:
                seen.add(p)
                yield p
    # URLs are tokens too (the http placeholder canary).
    for m in re.finditer(r"https?://\S+", text):
        url = m.group(0).rstrip(").,;'\"`>]")
        if url not in seen:
            seen.add(url)
            yield url


def _preview(token: str) -> str:
    return token[:4] + "…" if len(token) > 4 else "…"


def scan_text(text: str, manifest: dict[str, str], file: str, where: str) -> list[Finding]:
    found: list[Finding] = []
    hit_tokens: set[str] = set()
    if manifest:
        for c in candidates(text):
            t = manifest.get(hashlib.sha256(c.encode()).hexdigest())
            if t:
                hit_tokens.add(c)
                found.append(Finding("manifest", t, file, where, _preview(c)))
    for m in CANARY_SHAPE.finditer(text):
        if m.group(0) not in hit_tokens:
            found.append(Finding("shape", "canary-shaped", file, where, _preview(m.group(0))))
    return found


def _json_strings(obj, path: str = "$") -> Iterator[tuple[str, str]]:
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _json_strings(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _json_strings(v, f"{path}[{i}]")


def scan_file(path: Path, manifest: dict[str, str]) -> list[Finding]:
    name = str(path)
    try:
        raw = path.read_text(errors="replace")
    except OSError as e:
        print(f"warning: cannot read {name}: {e}", file=sys.stderr)
        return []
    found: list[Finding] = []
    if path.suffix == ".json":
        try:
            for where, s in _json_strings(json.loads(raw)):
                found += scan_text(s, manifest, name, where)
            return found
        except json.JSONDecodeError:
            pass  # fall through to text scanning
    if path.suffix == ".jsonl":
        for n, line in enumerate(raw.splitlines(), 1):
            try:
                for where, s in _json_strings(json.loads(line), f"line {n}"):
                    found += scan_text(s, manifest, name, where)
            except json.JSONDecodeError:  # torn last line of a live archive
                found += scan_text(line, manifest, name, f"line {n}")
        return found
    for n, line in enumerate(raw.splitlines(), 1):
        found += scan_text(line, manifest, name, f"line {n}")
    return found


def iter_files(paths: Iterable[Path]) -> Iterator[Path]:
    for p in paths:
        if p.is_dir():
            for root, _dirs, files in os.walk(p):
                for f in sorted(files):
                    if f in SKIP_NAMES:
                        continue
                    fp = Path(root) / f
                    if fp.suffix in _TEXT_SUFFIXES | {".json", ".jsonl"}:
                        yield fp
        elif p.is_file():
            yield p
        else:
            print(f"warning: {p} does not exist", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("paths", nargs="+", type=Path, help="files or directories to scan")
    ap.add_argument("--manifest", type=Path, help="canaries.manifest.sha256")
    ap.add_argument("--shape-only", action="store_true", help="no manifest; report prefixes only")
    ap.add_argument("--json", action="store_true", help="print findings as JSON")
    ap.add_argument("--strict", action="store_true", help="shape-only findings also fail")
    args = ap.parse_args(argv)

    if not args.manifest and not args.shape_only:
        ap.error("give --manifest, or --shape-only to scan for canary prefixes without one")
    manifest = load_manifest(args.manifest) if args.manifest else {}

    findings: list[Finding] = []
    for f in iter_files(args.paths):
        findings += scan_file(f, manifest)

    if args.json:
        json.dump([asdict(f) for f in findings], sys.stdout, indent=2)
        print()
    else:
        for f in findings:
            label = f.type if f.kind == "manifest" else "canary-shaped (not in manifest)"
            print(f"{f.file}\t{f.where}\t{label}\t{f.preview}")
        hits = sum(f.kind == "manifest" for f in findings)
        shapes = len(findings) - hits
        print(f"\n{hits} manifest hit(s), {shapes} canary-shaped string(s)", file=sys.stderr)

    if any(f.kind == "manifest" for f in findings):
        return 1
    if args.strict and findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
