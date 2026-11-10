#!/usr/bin/env python3
"""The canary hit viewer's watcher (spec *Watcher*). This slice: the scan of one archived run
directory (/data-share/runs/<time>_<instance>/, as the run_archive role writes it) into a hits file.

    canary_watch.py --archive RUN_DIR --out HITS.jsonl [--html PAGE.html] [--api-host HOST]

The scan reads the run's canaries.json, the AG-UI journals (agui/agui-journals/<session>.jsonl), the
agent's run log (agui/agent-runs.jsonl) and Open WebUI's chats (openwebui-export.json in the run
directory itself, never agui/openwebui-export.json, which is the journals reshaped and would repeat
their hits under Open WebUI's ids). Journals go first, so their copy of a run wins the dedup.

With --html, every hit now in the hits file (not only those appended this run) is also rendered as a
standalone participant page (hits_view.standalone), written with mode 0640 like the hits file itself:
the early output (spec *Early output*).

Logs carry paths, counts and errors only, never a canary value (decision 10).

Standard library only: the portal runs this from its repository checkout with the system Python.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from canary_hits import HitsFile, Place, JournalReader, agent_run_places, dedup_key, hits_for, openwebui_places  # noqa: E402
from canary_record import RecordError, _scalar, load_canaries, read_hosts  # noqa: E402
from hits_view import participant_body, standalone  # noqa: E402

OUTPUT_ROOT = Path(__file__).resolve().parents[1] / "ansible" / "output"  # spe_output_root's default
ARCHIVE_GENERATION = "archive"  # the generation a scan by hand keys its hits under


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _jsonl(path: Path):
    """The parsed lines of a JSON Lines file; lines that do not parse are dropped (untrusted input)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
    except FileNotFoundError:
        return


def _archive_places(run_dir: Path) -> list[Place]:
    places: list[Place] = []
    for journal in sorted((run_dir / "agui" / "agui-journals").glob("*.jsonl")):
        reader = JournalReader(journal.stem)
        for line in _jsonl(journal):
            places += reader.feed(line)
    records = list(_jsonl(run_dir / "agui" / "agent-runs.jsonl"))
    titles = {r.get("thread_id"): r.get("title") for r in records
              if isinstance(r, dict) and r.get("type") == "title" and isinstance(r.get("title"), str)}
    for record in records:
        places += agent_run_places(record, titles)
    try:
        export = json.loads((run_dir / "openwebui-export.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        export = None
    chats = export.get("chats") if isinstance(export, dict) else None
    for chat in chats if isinstance(chats, list) else []:
        if isinstance(chat, dict):
            places += openwebui_places(chat, "archive")
    return places


def scan_archive(run_dir: str, hits: HitsFile, seen: set[str], meta: dict, api_host: str | None,
                 generation: str) -> int:
    """Append to `hits` each hit of the archived run whose dedup key is not in `seen` (and add it there);
    the number appended. Raises RecordError when the run has no usable canaries.json."""
    directory = Path(run_dir)
    canaries = load_canaries(directory)
    count = 0
    for place in _archive_places(directory):
        for hit in hits_for(place, canaries, api_host):
            hit = {"id": None, "detected": _now(), "workspace": meta.get("workspace"),
                   "instance": meta.get("instance"), "owner": meta.get("owner"), **hit}
            key = dedup_key(hit, generation)
            if key in seen:
                continue
            if hits.append(hit) is None:
                return count
            seen.add(key)
            count += 1
    return count


def _top_level(path: Path, keys: tuple[str, ...]) -> dict:
    """Top-level scalar keys of a YAML file written by to_nice_yaml (run.yml); nested values are skipped."""
    out: dict = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        key, sep, raw = line.partition(":")
        if key in keys and sep and (not raw or raw[0] == " "):
            try:
                value = _scalar(raw.strip(), path.name)
            except RecordError:
                continue
            out[key] = value if isinstance(value, str) else None
    return out


def archive_meta(run_dir: str) -> dict:
    """`workspace`, `instance` and `owner` of an archived run: from its report.json (the report
    sidecar's copy), else from run.yml (`instance`, `participant`), with workspace null."""
    directory = Path(run_dir)
    try:
        report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        report = None
    if isinstance(report, dict) and isinstance(report.get("workspace_id"), str):
        return {"workspace": report["workspace_id"], "instance": report.get("instance"), "owner": report.get("owner")}
    run = _top_level(directory / "run.yml", ("instance", "participant"))
    return {"workspace": None, "instance": run.get("instance"), "owner": run.get("participant")}


def write_html(path: str, meta: dict, hits_list: list[dict]) -> None:
    """The run's hits file rendered as a standalone participant page (the early output), mode 0640
    like the hits file itself (fchmod, whatever the umask). Written to a temporary file in the same
    directory and moved into place with os.replace, so a reader never sees a half-written page."""
    title = f"Canary hits: {meta.get('instance') or meta.get('workspace') or 'workspace'}"
    doc = standalone(title, participant_body(meta, hits_list, None)).encode()
    target = Path(path)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    try:
        try:
            os.fchmod(fd, 0o640)
            view = memoryview(doc)
            while view:
                view = view[os.write(fd, view):]
        finally:
            os.close(fd)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _api_host(given: str | None, instance: str | None) -> str | None:
    """--api-host, else the instance's output directory's hosts.yml while it still exists, else None
    (then every URL host in a call's arguments counts as foreign)."""
    if given:
        return given
    if instance and "/" not in instance and instance not in (".", ".."):
        try:
            host = read_hosts(OUTPUT_ROOT / instance).get("api_host")
        except RecordError:
            return None
        return host if isinstance(host, str) and host else None
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan an archived run directory into a canary hits file.")
    parser.add_argument("--archive", required=True, metavar="RUN_DIR", help="the archived run directory")
    parser.add_argument("--out", required=True, metavar="HITS.jsonl", help="the hits file to append to")
    parser.add_argument("--html", metavar="PAGE.html", help="also render a standalone participant page from the whole --out hits file"
                        " (every hit in it, from all runs scanned into it, not only this one)")
    parser.add_argument("--api-host", metavar="HOST", help="the instance's API host (default: its hosts.yml)")
    args = parser.parse_args(argv)
    meta = archive_meta(args.archive)
    api_host = _api_host(args.api_host, meta.get("instance"))
    hits = HitsFile(args.out)
    seen = {dedup_key(h, ARCHIVE_GENERATION) for h in hits.read() if isinstance(h.get("canary"), dict)
            and isinstance(h["canary"].get("token"), str)}
    try:
        count = scan_archive(args.archive, hits, seen, meta, api_host, ARCHIVE_GENERATION)
    except RecordError as e:
        print(f"canary_watch: {args.archive}: {e}", file=sys.stderr)
        return 1
    note = " (hits file full)" if hits.full else ""
    print(f"canary_watch: {count} new hits from {args.archive} into {args.out}{note}"
          f" (workspace {meta.get('workspace') or 'none'}, api host {'known' if api_host else 'unknown'})")
    if args.html:
        write_html(args.html, meta, hits.read())
        print(f"canary_watch: wrote {args.html}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
