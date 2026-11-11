#!/usr/bin/env python3
"""Write injections.json (spec part 02, *Hand-off*) from the catalogue and the actual placements.

Runs on the controller. stdin: {"switches": {spe_inject_*: bool}, "placements": [...],
"canary_files": [...]}, where placements are what trs_install.py and drs_register.py
reported and canary_files the `file` fields of the canary record. Tokens are never
passed in, so none can reach the manifest. Any enabled fixture without exactly one
placement, with a payload that differs from the committed file, or without a canary
in its target file stops the build (exit 1).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


class ManifestBuildError(Exception):
    pass


def build(fixtures: list[dict], switches: dict, placements: list[dict], canary_files: set[str],
          payload_dir: Path, repo_root: Path) -> dict:
    by_id: dict[str, list[dict]] = {}
    for p in placements:
        # `p["id"]`, not `.get("id")` (final review, I4b): a placement with no 'id' used to be
        # grouped silently under the key None, which either lingered unreported (no fixture ever
        # has id None) or, once a second kind of unmatched placement existed too, made the final
        # `sorted(by_id)` below raise TypeError (None is not orderable against a str) instead of
        # this clear error.
        if "id" not in p:
            raise ManifestBuildError("a placement was reported with no 'id'")
        by_id.setdefault(p["id"], []).append(p)
    entries = []
    for fx in fixtures:
        found = by_id.pop(fx["id"], [])
        if not switches.get(fx["switch"]):
            if found:
                raise ManifestBuildError(f"{fx['id']}: placed although {fx['switch']} is off")
            continue
        if len(found) != 1:
            raise ManifestBuildError(f"{fx['id']}: {len(found)} placements for {fx['switch']}, expected 1")
        placement = found[0]
        # The fixture selects by one key (tool_id or path): the placement's value under that same key,
        # top-level (a DRS object's path) or in its location (a TRS tool's id).
        (key, want), = fx["select"].items()
        selected = placement.get(key, placement["location"].get(key))
        if selected != want:
            raise ManifestBuildError(f"{fx['id']}: placed in {selected}, catalogue selects {fx['select']}")
        payload = (payload_dir / fx["payload"]).resolve()
        digest = hashlib.sha256(payload.read_bytes()).hexdigest()
        if placement["payload_sha256"] != digest:
            raise ManifestBuildError(f"{fx['id']}: planted payload differs from {fx['payload']}")
        if fx["target_file"] not in payload.read_text(encoding="utf-8"):
            raise ManifestBuildError(f"{fx['id']}: {fx['payload']} does not name {fx['target_file']}")
        if fx["canary_file"] not in canary_files:
            raise ManifestBuildError(f"{fx['id']}: no canary in {fx['canary_file']}; "
                                     "enable the registry and flag canaries")
        entries.append({
            "id": fx["id"], "switch": fx["switch"],
            "payload_file": payload.relative_to(repo_root.resolve()).as_posix(),
            "payload_sha256": digest, "surface": fx["surface"], "location": placement["location"],
            "target_file": fx["target_file"], "canary_file": fx["canary_file"],
            "action": fx["action"], "disclosure": fx["disclosure"],
        })
    if by_id:
        raise ManifestBuildError(f"placements without a catalogue fixture: {sorted(by_id)}")
    return {"schema_version": 1, "injections": entries}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", required=True, help="catalog/injections/fixtures.json")
    ap.add_argument("--repo-root", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    fixtures_file = Path(args.fixtures)
    data = json.load(sys.stdin)
    manifest = build(json.loads(fixtures_file.read_text())["fixtures"], data["switches"], data["placements"],
                     set(data["canary_files"]), fixtures_file.parent, Path(args.repo_root))
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)  # also when an earlier run left the file with another mode
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    print(f"{len(manifest['injections'])} injections in {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ManifestBuildError, OSError, KeyError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
