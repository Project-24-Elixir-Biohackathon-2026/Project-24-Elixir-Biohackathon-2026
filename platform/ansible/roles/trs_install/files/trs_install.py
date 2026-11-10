#!/usr/bin/env python3
"""Install workflows from the catalog into the instance's TRS server.

Each catalog directory holds tool.yml plus the workflow files. Optional
canaries: a token appended to the tool description, and a comment line with a
token inserted into every descriptor file. Tokens are derived from --seed and
reported on stdout, never stored on the instance.

Optional injections (evaluation fixtures, never tokens): --inject-description
ID PAYLOAD TOOL_ID appends a payload file's text to one tool's description,
--inject-comment ID PAYLOAD TOOL_ID inserts it as comment lines into one
tool's primary descriptor; either is repeatable, so several payloads can land
on the same tool's description or descriptor, appended in order. Fields are
always built from tool.yml and the payload, so re-running gives the same
fields; the placements (each carrying its catalogue id) are reported on
stdout for injections.json.

stdout: {"installed": [...], "canaries": [...], "injections": [...]}
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml

_UNAMBIGUOUS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
COMMENT = {"NFL": "//", "SMK": "#", "CWL": "#", "WDL": "#"}
DIRECTIVES = ("nextflow.enable.", "nextflow.preview.")


def put(base: str, path: str, body: dict) -> int:
    req = Request(base + path, data=json.dumps(body).encode(),
                  headers={"Content-Type": "application/json"}, method="PUT")
    try:
        with urlopen(req, timeout=60) as resp:
            return resp.status
    except HTTPError as e:
        raise RuntimeError(f"PUT {path} failed ({e.code}): {e.read().decode(errors='replace')}") from e
    except URLError as e:
        raise RuntimeError(f"cannot reach {base}: {e.reason}") from e


def read_payload(path: str) -> tuple[str, str]:
    """(text, sha256 of the file bytes) of a committed payload file.

    Twin: drs_register.py's read_payload (kept duplicated, each script is
    deployed alone; platform/dev/tests covers both with the same cases).
    """
    raw = Path(path).read_bytes()
    text = raw.decode("utf-8").strip()
    if not text:
        raise ValueError(f"payload {path} is empty")
    return text, hashlib.sha256(raw).hexdigest()


def directive_end(lines: list[str]) -> int:
    """Index of the first line after a leading shebang and Nextflow directives."""
    i = 1 if lines and lines[0].startswith("#!") else 0
    while i < len(lines) and lines[i].startswith(DIRECTIVES):
        i += 1
    return i


def build_descriptor(content: str, descriptor_type: str, token: str | None = None,
                     payloads: list[str] | None = None) -> str:
    """The descriptor with a canary comment and/or each payload, in order, as comment lines after its directives."""
    marker = COMMENT.get(descriptor_type, "#")
    block = [f"{marker} provenance-id: {token}"] if token else []
    for payload in payloads or []:
        block += [f"{marker} {line}".rstrip() for line in payload.splitlines()]
    lines = content.splitlines()
    at = directive_end(lines)
    lines[at:at] = block
    return "\n".join(lines) + "\n"


def build_description(base: str, token: str | None = None, payloads: list[str] | None = None) -> str:
    description = f"{base} [ref {token}]" if token else base
    for payload in payloads or []:
        description += f"\n\n{payload}"
    return description


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--api", required=True, help="https://HOST/ga4gh/trs/v2")
    ap.add_argument("--trs-host", default="trs-filer.weskit.internal:8080")
    ap.add_argument("--workflow", action="append", default=[])
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--canary-descriptions", action="store_true")
    ap.add_argument("--canary-comments", action="store_true")
    ap.add_argument("--inject-description", action="append", nargs=3, default=[],
                    metavar=("ID", "PAYLOAD", "TOOL_ID"), help="repeatable: catalogue id, payload file, target tool")
    ap.add_argument("--inject-comment", action="append", nargs=3, default=[],
                    metavar=("ID", "PAYLOAD", "TOOL_ID"), help="repeatable: catalogue id, payload file, target tool")
    args = ap.parse_args()

    base = args.api.rstrip("/")
    rng = random.Random(f"{args.seed}:trs")
    metas = [(Path(args.catalog) / name, yaml.safe_load((Path(args.catalog) / name / "tool.yml").read_text()))
             for name in args.workflow]
    ids = {meta["id"] for _, meta in metas}

    def load_injections(triples: list[list[str]]) -> list[dict]:
        """[(id, payload, tool), ...] -> [{"id", "tool", "text", "sha256"}, ...], validated before any PUT."""
        entries = []
        for iid, payload_path, tool in triples:
            if tool not in ids:
                raise RuntimeError(f"{iid}: injection target {tool} is not among the installed workflows {sorted(ids)}")
            text, digest = read_payload(payload_path)
            entries.append({"id": iid, "tool": tool, "text": text, "sha256": digest})
        return entries

    desc_entries = load_injections(args.inject_description)
    comment_entries = load_injections(args.inject_comment)
    installed, canaries, injections = [], [], []

    for wdir, meta in metas:
        tool_id = meta["id"]
        version = meta["version"]
        dtype = version["descriptor_type"]
        token = None
        if args.canary_descriptions:
            token = "TRSMETA-" + "".join(rng.choice(_UNAMBIGUOUS) for _ in range(8))
            canaries.append({"token": token, "type": "trs-tool-description",
                             "file": f"trs:{tool_id}", "note": "tool description"})
        own_desc = [e for e in desc_entries if e["tool"] == tool_id]
        for e in own_desc:
            injections.append({"id": e["id"], "surface": "trs-description", "payload_sha256": e["sha256"],
                               "location": {"tool_id": tool_id, "field": "description"}})
        description = build_description(meta.get("description", ""), token, [e["text"] for e in own_desc])

        toolclass = meta["toolclass"]
        put(base, f"/toolClasses/{toolclass['id']}",
            {"name": toolclass["name"], "description": toolclass["description"]})
        put(base, f"/tools/{tool_id}", {
            "organization": meta.get("organization", "local"),
            "name": meta.get("name", tool_id),
            "description": description,
            "has_checker": False,
            "toolclass": toolclass,
            "versions": [],
        })

        files = []
        for entry in meta["files"]:
            content = (wdir / entry["path"]).read_text()
            token = None
            if args.canary_comments:
                token = "WFCANARY-" + "".join(rng.choice(_UNAMBIGUOUS) for _ in range(8))
                canaries.append({"token": token, "type": "workflow-file-comment",
                                 "file": f"trs:{tool_id}/{version['id']}/{dtype}/{entry['path']}",
                                 "note": "comment line in workflow file"})
            own_comment = []
            if entry["file_type"] == "PRIMARY_DESCRIPTOR":
                own_comment = [e for e in comment_entries if e["tool"] == tool_id]
            for e in own_comment:
                injections.append({"id": e["id"], "surface": "workflow-comment", "payload_sha256": e["sha256"],
                                   "location": {"tool_id": tool_id, "version": version["id"],
                                                "descriptor_type": dtype, "path": entry["path"]}})
            if token or own_comment:
                content = build_descriptor(content, dtype, token, [e["text"] for e in own_comment])
            files.append({"tool_file": {"path": entry["path"], "file_type": entry["file_type"]},
                          "file_wrapper": {"content": content}, "type": dtype})
        put(base, f"/tools/{tool_id}/versions/{version['id']}", {
            "author": version.get("author", ["local"]),
            "name": version["id"],
            "is_production": bool(version.get("is_production", False)),
            "descriptor_type": [dtype],
            "verified": False,
            "signed": False,
            "files": files,
        })
        primary = next(e["path"] for e in meta["files"] if e["file_type"] == "PRIMARY_DESCRIPTOR")
        installed.append({
            "id": tool_id, "version": version["id"], "descriptor_type": dtype,
            "workflow_url": f"trs://{args.trs_host}/{tool_id}/{version['id']}/{dtype}/{primary}",
        })
        print(f"installed {tool_id}/{version['id']}", file=sys.stderr)

    json.dump({"installed": installed, "canaries": canaries, "injections": injections}, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError, KeyError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
