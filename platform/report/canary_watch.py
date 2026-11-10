#!/usr/bin/env python3
"""The canary hit viewer's watcher (spec *Watcher*): a daemon on the portal VM that polls every running
Coder workspace's instance through the reader (canary_reader.py, sent over SSH) and scans each stopped
run's archive once, writing each workspace's hits, state and status to the hits directory.

    canary_watch.py [--reports-dir DIR] [--runs-dir DIR] [--hits-dir DIR] [--output-root DIR]
    canary_watch.py --archive RUN_DIR --out HITS.jsonl [--html PAGE.html] [--api-host HOST]
    canary_watch.py --once --output-dir DIR --out HITS.jsonl

The first form is the daemon (Watcher.run_forever). Per workspace id it keeps, in the hits directory,
`<id>.jsonl` (the hits, 0640), `<id>.state.json` (0600: the generation and the hits line it began at, the reader's offsets, each
journal's open run's start, the dedup keys, the run directories scanned, the run log's titles) and
`<id>.status.json` (0640: `state` running|stopped|unreachable|encrypted|capped, `since`, `last_poll`,
`hits` per kind, `note`), which the pages read. What the reader returns is the participant's (root on
their instance): a line that does not parse or is malformed is dropped, a reply of the wrong shape is a
failed poll, at most 200 hits are kept per poll and 10 MB per hits file.

The second form scans one archived run directory (/data-share/runs/<time>_<instance>/, as the
run_archive role writes it) into a hits file.

The scan reads the run's canaries.json, the AG-UI journals (agui/agui-journals/<session>.jsonl), the
agent's run log (agui/agent-runs.jsonl) and Open WebUI's chats (openwebui-export.json in the run
directory itself, never agui/openwebui-export.json, which is the journals reshaped and would repeat
their hits under Open WebUI's ids). Journals go first, so their copy of a run wins the dedup.

With --html, every hit now in the hits file (not only those appended this run) is also rendered as a
standalone participant page (hits_view.standalone), written with mode 0640 like the hits file itself:
the early output (spec *Early output*).

The third form (--once) is a hand check only (ruling 5): one poll of --output-dir's instance from
zero offsets, through the real SshTransport, appending new hits to --out. It writes nothing under
the hits directory or /data-share (no state file, no status file): the daemon never scans without a
report sidecar, and this never stands in for it.

The daemon's logs carry workspace ids, counts and error classes only, never a canary value, an excerpt, a
line of a source, a file or run directory name (a journal's, an instance's, is the participant's) or a path
under sensitive/ (decision 10).

Standard library only: the portal runs this from its repository checkout with the system Python.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import logging
import math
import os
import re
import selectors
import shlex
import subprocess
import sys
import tempfile
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from canary_hits import (HITS_FILE_MAX, HitsFile, JournalReader, Place, agent_run_places, dedup_key,  # noqa: E402
                         hits_for, openwebui_places, receiver_places)
from canary_record import RecordError, _scalar, load_canaries, read_hosts, vm_argv  # noqa: E402
from hits_view import participant_body, standalone  # noqa: E402

OUTPUT_ROOT = Path(__file__).resolve().parents[1] / "ansible" / "output"  # spe_output_root's default
ARCHIVE_GENERATION = "archive"  # the generation a scan by hand keys its hits under

# Defaults for the daemon; --archive's own flags are unchanged by them.
REPORTS_DIR = "/data-share/reports"
RUNS_DIR = "/data-share/runs"
HITS_DIR = "/data-share/canary-hits"

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _jsonl(path: Path, who: str | None = None, kind: str = "a source"):
    """The parsed lines of a JSON Lines file; lines that do not parse (or nest too deep to) are dropped
    (untrusted input). A file that cannot be read (a PermissionError, a directory in its place) is skipped
    and logged under `who` (the workspace id) by `kind`, a fixed label, never the file's name (a journal's
    is the participant's): one bad source never ends a scan or the daemon."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    yield json.loads(line)
                except (ValueError, RecursionError):
                    continue
    except FileNotFoundError:
        return
    except OSError as e:
        logger.warning("%s: cannot read %s (%s), skipping it", who, kind, type(e).__name__)


def _archive_places(run_dir: Path, who: str | None = None) -> list[Place]:
    """Every place of the archived run. A line, record or chat of the wrong shape (the participant's, or
    the agent's: untrusted) that still makes a source's parser raise is skipped, so the rest still count."""
    places: list[Place] = []
    dropped = 0
    # Only <session id>.jsonl, as polling and the chat app read them: any other name is not a journal.
    journals = [j for j in (run_dir / "agui" / "agui-journals").glob("*.jsonl") if SESSION_ID.fullmatch(j.stem)]
    for journal in sorted(journals):
        reader = JournalReader(journal.stem)
        for line in _jsonl(journal, who, "a journal"):
            try:
                places += reader.feed(line)
            except Exception:
                dropped += 1
    records = list(_jsonl(run_dir / "agui" / "agent-runs.jsonl", who, "agent-runs.jsonl"))
    titles = {r["thread_id"]: r["title"] for r in records
              if isinstance(r, dict) and r.get("type") == "title" and isinstance(r.get("thread_id"), str)
              and isinstance(r.get("title"), str)}
    for record in records:
        try:
            places += agent_run_places(record, titles)
        except Exception:
            dropped += 1
    try:
        export = json.loads((run_dir / "openwebui-export.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, RecursionError):
        export = None
    except OSError as e:
        logger.warning("%s: cannot read openwebui-export.json (%s), skipping it", who, type(e).__name__)
        export = None
    chats = export.get("chats") if isinstance(export, dict) else None
    for chat in chats if isinstance(chats, list) else []:
        if isinstance(chat, dict):
            try:
                places += openwebui_places(chat, "archive")
            except Exception:
                dropped += 1
    if dropped:
        logger.info("%s: %d malformed records dropped from an archived run", who, dropped)
    return places


def scan_archive(run_dir: str, hits: HitsFile, seen: set[str], meta: dict, api_host: str | None,
                 generation: str) -> int:
    """Append to `hits` each hit of the archived run whose dedup key is not in `seen` (and add it there);
    the number appended. Raises RecordError when the run has no usable canaries.json."""
    directory = Path(run_dir)
    canaries = load_canaries(directory)
    count = 0
    for place in _archive_places(directory, meta.get("workspace") or meta.get("instance")):
        try:
            found = hits_for(place, canaries, api_host)
        except Exception:  # a value of the wrong shape (or nested too deep) in one place: the rest still count
            continue
        for hit in found:
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
    except (OSError, ValueError, RecursionError):
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


@dataclass
class Ssh:
    """How to reach the workspace's VM, informational only: Task 7's SshTransport reaches it with
    canary_record.vm_argv(output_dir) directly, which reads hosts.yml itself."""
    user: str | None
    host: str | None
    key: str | None


@dataclass
class Workspace:
    """One Coder workspace the watcher scans (spec *Watcher*, *What it scans*, *Which are
    running*): a report sidecar naming an instance whose output directory has a readable
    hosts.yml. `generation` changes with every rewrite of hosts.yml (a fresh instance); `running`
    while hosts.yml is newer than every archive directory of this instance; `encrypted` when the
    canary record is age-encrypted only (still returned, so its status can say so); `hosts_mtime_ns`
    the mtime of hosts.yml the generation was taken at (None: not checked)."""
    id: str
    owner: str | None
    instance: str
    output_dir: str
    api_host: str | None
    ssh: Ssh
    generation: str
    running: bool
    encrypted: bool
    hosts_mtime_ns: int | None = None


def _is_uuid(stem: str) -> bool:
    try:
        uuid.UUID(stem)
        return True
    except ValueError:
        return False


def _newest_sidecars(reports_dir: Path) -> dict[str, tuple[str, dict]]:
    """{instance: (workspace id, sidecar)}, the newest (by mtime) sidecar per instance. A
    non-UUID filename, a sidecar that is not valid JSON, or one lacking `instance` is skipped
    (untrusted input): discover never raises over one bad sidecar."""
    best: dict[str, tuple[float, str, dict]] = {}
    try:
        paths = sorted(reports_dir.glob("*.json"))
    except OSError:
        return {}
    for path in paths:
        if not _is_uuid(path.stem):
            continue
        try:
            sidecar = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError):
            logger.warning("%s: unreadable report sidecar, skipping", path.stem)
            continue
        instance = sidecar.get("instance") if isinstance(sidecar, dict) else None
        if not isinstance(instance, str) or not instance:
            logger.warning("%s: report sidecar has no instance, skipping", path.stem)
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        current = best.get(instance)
        if current is None or mtime > current[0]:
            best[instance] = (mtime, path.stem, sidecar)
    return {instance: (workspace_id, sidecar) for instance, (_, workspace_id, sidecar) in best.items()}


def _record_status(output_dir: Path) -> tuple[bool, bool]:
    """(usable, encrypted) of this output directory's canary record: encrypted when only
    canaries.json.age is there (still usable: the workspace is discovered, so its status can say
    so); usable (and not encrypted) when canaries.json parses with load_canaries; otherwise
    neither file, or a malformed canaries.json, is not usable at all."""
    has_json = (output_dir / "canaries.json").exists()
    has_age = (output_dir / "canaries.json.age").exists()
    if not has_json and has_age:
        return True, True
    if not has_json:
        return False, False
    try:
        load_canaries(output_dir)
    except RecordError:
        return False, False
    return True, False


def _generation_at(hosts_path: Path) -> tuple[str, int]:
    """SHA-256 of hosts.yml's bytes and mtime: a rewrite with identical content still starts a
    new generation, since its mtime changed (spec *Watcher*, *Which are running*); and that mtime
    (ns), which the watcher compares every tick to see a rewrite between discoveries."""
    mtime_ns = hosts_path.stat().st_mtime_ns
    digest = hashlib.sha256(hosts_path.read_bytes())
    digest.update(str(mtime_ns).encode())
    return digest.hexdigest(), mtime_ns


def _generation(hosts_path: Path) -> str:
    return _generation_at(hosts_path)[0]


def _is_running(hosts_path: Path, runs_dir: Path, instance: str) -> bool:
    """hosts.yml newer than every runs_dir/*_<instance> directory (an exact suffix: "ws1" does
    not match "x_ws10"). No matching archive directory at all: running (vacuously newer)."""
    hosts_mtime = hosts_path.stat().st_mtime
    suffix = f"_{instance}"
    try:
        entries = list(runs_dir.iterdir())
    except OSError:
        entries = []
    for entry in entries:
        if entry.is_dir() and entry.name.endswith(suffix):
            try:
                if entry.stat().st_mtime >= hosts_mtime:
                    return False
            except OSError:
                continue
    return True


def discover(reports_dir: str, output_root: str, runs_dir: str) -> list[Workspace]:
    """Every Coder workspace the watcher scans (decision 9): one per report sidecar whose
    instance has a readable hosts.yml under output_root (the newest sidecar wins when two name
    the same instance); a workspace with neither canaries.json nor canaries.json.age is skipped.
    Never raises over a bad sidecar or record: logs the workspace id and moves on."""
    reports_path, output_root_path, runs_path = Path(reports_dir), Path(output_root), Path(runs_dir)
    workspaces: list[Workspace] = []
    for instance, (workspace_id, sidecar) in _newest_sidecars(reports_path).items():
        output_dir = output_root_path / instance
        try:
            hosts = read_hosts(output_dir)
        except RecordError as e:
            # The class only: its message can name the output directory's path (the instance's name).
            logger.warning("%s: hosts.yml unusable (%s), skipping", workspace_id, type(e).__name__)
            continue
        usable, encrypted = _record_status(output_dir)
        if not usable:
            logger.warning("%s: no usable canary record, skipping", workspace_id)
            continue
        owner = sidecar.get("owner") if isinstance(sidecar.get("owner"), str) else None
        api_host = hosts.get("api_host") if isinstance(hosts.get("api_host"), str) else None
        ssh = Ssh(
            user=hosts.get("ssh_user") if isinstance(hosts.get("ssh_user"), str) else None,
            host=next((v for v in (hosts.get("ssh_target"), hosts.get("floating_ip"), hosts.get("api_host"))
                      if isinstance(v, str) and v), None),
            key=hosts.get("ssh_key") if isinstance(hosts.get("ssh_key"), str) else None,
        )
        generation, mtime_ns = _generation_at(output_dir / "hosts.yml")
        workspaces.append(Workspace(
            id=workspace_id,
            owner=owner,
            instance=instance,
            output_dir=str(output_dir),
            api_host=api_host,
            ssh=ssh,
            generation=generation,
            running=_is_running(output_dir / "hosts.yml", runs_path, instance),
            encrypted=encrypted,
            hosts_mtime_ns=mtime_ns,
        ))
    return workspaces


def once_workspace(output_dir: str) -> Workspace:
    """A Workspace for a hand check of one output directory (--once, ruling 5): no report
    sidecar, so no owner and a fixed id of "once"; always `running` (there is no runs_dir to
    weigh it against: the caller polls exactly once regardless). Raises RecordError for the same
    reasons discover() would skip this instance: hosts.yml unreadable, or neither canaries.json
    nor canaries.json.age present."""
    directory = Path(output_dir)
    hosts = read_hosts(directory)
    usable, encrypted = _record_status(directory)
    if not usable:
        raise RecordError("no usable canary record (canaries.json or canaries.json.age)")
    api_host = hosts.get("api_host") if isinstance(hosts.get("api_host"), str) else None
    ssh = Ssh(
        user=hosts.get("ssh_user") if isinstance(hosts.get("ssh_user"), str) else None,
        host=next((v for v in (hosts.get("ssh_target"), hosts.get("floating_ip"), hosts.get("api_host"))
                  if isinstance(v, str) and v), None),
        key=hosts.get("ssh_key") if isinstance(hosts.get("ssh_key"), str) else None,
    )
    generation, mtime_ns = _generation_at(directory / "hosts.yml")
    return Workspace(id="once", owner=None, instance=directory.name, output_dir=str(directory),
                     api_host=api_host, ssh=ssh, generation=generation, running=True, encrypted=encrypted,
                     hosts_mtime_ns=mtime_ns)


# The daemon (spec *Watcher*, *How it pulls*, *Reader output is untrusted*, *On stop*)

POLL_EVERY = 3.0  # seconds between polls of a running workspace
DISCOVER_EVERY = 15.0  # seconds between discoveries (sidecars, hosts.yml, canaries.json, all over NFS)
BACKOFF = 60.0  # seconds after a failed poll, or a failed write of an archived run's hits
ARCHIVE_WAIT = 600.0  # seconds past a stop's run directory's mtime before it is scanned without its index.md
POLL_TIMEOUT = 30  # seconds for one reader call
REPLY_MAX = 32 << 20  # bytes of reader reply read; past it the poll fails
HITS_PER_POLL = 200
TITLES_MAX = 1000  # titles kept per workspace (run log threads, journals); the oldest go first
READER = Path(__file__).resolve().parent / "canary_reader.py"
# One SSH connection per instance, its socket on local disk (not /data-share's NFS); never a prompt.
SSH_OPTIONS = ["-o", "ControlMaster=auto", "-o", "ControlPath=~/.ssh/cm-%C", "-o", "ControlPersist=60",
               "-o", "BatchMode=yes"]
SESSION_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
OFFSET_KEYS = ("journals", "agent_runs", "receiver", "openwebui")


class PollError(Exception):
    """A failed poll. Its message names what failed, never anything the reply carried."""


class OffsetsError(ValueError):
    """Offsets that may not reach a command line. Its message names the key, never a value."""


def _count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def check_offsets(offsets: object) -> dict:
    """The offsets the reader is handed, checked before they reach a command line: the four known keys,
    journal keys session ids (lowercase UUIDs), byte offsets non-negative integers, Open WebUI's a finite
    number. Raises OffsetsError (a ValueError)."""
    if not isinstance(offsets, dict) or set(offsets) - set(OFFSET_KEYS):
        raise OffsetsError("offsets: unexpected keys")
    journals = offsets.get("journals", {})
    if not isinstance(journals, dict):
        raise OffsetsError("offsets: journals is not an object")
    for key, value in journals.items():
        if not (isinstance(key, str) and SESSION_ID.fullmatch(key) and _count(value)):
            raise OffsetsError("offsets: a journal key or offset is malformed")
    for name in ("agent_runs", "receiver"):
        if name in offsets and not _count(offsets[name]):
            raise OffsetsError(f"offsets: {name} is not a byte offset")
    if "openwebui" in offsets and not _number(offsets["openwebui"]):
        raise OffsetsError("offsets: openwebui is not a number")
    return offsets


def run_capped(argv: list[str], data: bytes, timeout: float, cap: int, env: dict | None = None) -> bytes:
    """Run argv with `data` on its stdin and return its stdout. PollError when it runs past `timeout`
    seconds, writes more than `cap` bytes or exits non-zero. Its stderr is discarded: what the instance
    prints there is the participant's, and could carry a token into the log."""
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
    deadline = time.monotonic() + timeout
    out, pending = bytearray(), memoryview(data)
    selector = selectors.DefaultSelector()
    try:
        selector.register(proc.stdout, selectors.EVENT_READ)
        if pending:
            os.set_blocking(proc.stdin.fileno(), False)
            selector.register(proc.stdin, selectors.EVENT_WRITE)
        else:
            proc.stdin.close()
        while selector.get_map():
            left = deadline - time.monotonic()
            if left <= 0:
                raise PollError(f"timed out after {timeout} s")
            for key, _ in selector.select(left):
                if key.fileobj is proc.stdin:
                    try:
                        pending = pending[os.write(proc.stdin.fileno(), pending[:65536]):]
                    except BrokenPipeError:
                        pending = pending[:0]
                    if not pending:
                        selector.unregister(proc.stdin)
                        proc.stdin.close()
                    continue
                chunk = os.read(proc.stdout.fileno(), 65536)
                if not chunk:
                    selector.unregister(proc.stdout)
                    continue
                out += chunk
                if len(out) > cap:
                    raise PollError(f"reply larger than {cap} bytes")
        try:
            code = proc.wait(timeout=max(deadline - time.monotonic(), 0.1))
        except subprocess.TimeoutExpired:
            raise PollError(f"timed out after {timeout} s") from None
    except BaseException:
        proc.kill()
        proc.wait()
        raise
    finally:
        selector.close()
        for pipe in (proc.stdin, proc.stdout):
            if not pipe.closed:
                pipe.close()
    if code != 0:
        raise PollError(f"exit status {code}")
    return bytes(out)


def _parse_reply(out: bytes) -> object:
    try:
        return json.loads(out)
    except ValueError:
        raise PollError("reply is not JSON") from None


class Transport:
    """How the watcher runs the reader for a workspace: `read(ws, offsets)` returns its parsed reply."""

    def read(self, ws: Workspace, offsets: dict) -> dict:
        raise NotImplementedError


class SshTransport(Transport):
    """The reader over SSH, as the archive playbook connects (canary_record.vm_argv: hosts.yml's user,
    target, key and arguments), with SSH_OPTIONS before the target; on a local controller (vm_argv is
    []) `sudo -n python3 -` runs here (-n: a sudo that would prompt fails the poll instead of hanging it).
    The reader's source goes on stdin, the offsets as its argument."""

    def __init__(self, runner=run_capped):
        self.runner = runner

    def read(self, ws: Workspace, offsets: dict) -> dict:
        payload = json.dumps(check_offsets(offsets), separators=(",", ":"))
        prefix = vm_argv(ws.output_dir)
        if prefix:
            argv = prefix[:-1] + SSH_OPTIONS + [prefix[-1], "sudo -n python3 - " + shlex.quote(payload)]
        else:
            argv = ["sudo", "-n", "python3", "-", payload]
        return _parse_reply(self.runner(argv, READER.read_bytes(), POLL_TIMEOUT, REPLY_MAX))


class LocalTransport(Transport):
    """The reader run here over local paths (SPE_READER_PATHS): a fake instance, for tests."""

    def __init__(self, paths: dict):
        self.paths = paths

    def read(self, ws: Workspace, offsets: dict) -> dict:
        payload = json.dumps(check_offsets(offsets), separators=(",", ":"))
        env = dict(os.environ, SPE_READER_PATHS=json.dumps(self.paths))
        return _parse_reply(run_capped([sys.executable, "-", payload], READER.read_bytes(), POLL_TIMEOUT,
                                       REPLY_MAX, env))


def _check_file(entry: object) -> None:
    if not (isinstance(entry, dict) and all(_count(entry.get(k)) for k in ("size", "start", "end"))):
        raise PollError("reply: a file entry lacks its offsets")
    lines, starts = entry.get("lines"), entry.get("line_starts")
    if not (isinstance(lines, list) and isinstance(starts, list) and len(lines) == len(starts)
            and all(isinstance(line, str) for line in lines) and all(_count(s) for s in starts)):
        raise PollError("reply: a file entry's lines are malformed")


def check_reply(reply: object) -> dict:
    """The reader's reply in the shape canary_reader.py's docstring gives, else PollError. A journal key
    that is not a session id is no error: the chat app does not read such a file either, so it is left out."""
    if not isinstance(reply, dict) or not isinstance(reply.get("files"), dict):
        raise PollError("reply: no files")
    for key, entry in reply["files"].items():
        if key in ("agent_runs", "receiver") or (isinstance(key, str) and key.startswith("journal:")):
            _check_file(entry)
        else:
            raise PollError("reply: an unknown file key")
    openwebui = reply.get("openwebui")
    if openwebui is not None and not (isinstance(openwebui, dict) and isinstance(openwebui.get("rows"), list)
                                      and _number(openwebui.get("max"))):
        raise PollError("reply: openwebui is malformed")
    if not (isinstance(reply.get("missing"), list) and isinstance(reply.get("errors"), list)):
        raise PollError("reply: no missing or errors list")
    return reply


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_atomic(path: Path, text: str, mode: int) -> None:
    """Write `text` to `path` with `mode` (whatever the umask), through a temporary file in the same
    directory and os.replace, so a reader never sees half a file."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        try:
            os.fchmod(fd, mode)
            view = memoryview(text.encode())
            while view:
                view = view[os.write(fd, view):]
        finally:
            os.close(fd)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _bounded(mapping: dict, key: str, value: str) -> None:
    mapping.pop(key, None)
    mapping[key] = value
    while len(mapping) > TITLES_MAX:
        del mapping[next(iter(mapping))]


def _fresh_state(generation: str | None, generation_start: int = 0) -> dict:
    """`generation_start`: the hits file's line count when this generation began; the hits past it are
    this generation's (a hit records no generation of its own)."""
    return {"generation": generation, "generation_start": generation_start,
            "offsets": {"journals": {}, "agent_runs": 0, "receiver": 0, "openwebui": 0},
            "run_starts": {}, "archived": [], "titles": {}, "journal_titles": {}}


def _str_map(value: object, kind: type) -> dict:
    return {k: v for k, v in value.items() if isinstance(k, str) and isinstance(v, kind)} if isinstance(value, dict) else {}


def _load_state(data: object) -> tuple[dict, set[str]]:
    """The state file's content, each part checked (a part of the wrong type starts afresh); and its seen keys."""
    if not isinstance(data, dict):
        return _fresh_state(None), set()
    state = _fresh_state(data.get("generation") if isinstance(data.get("generation"), str) else None,
                         data["generation_start"] if _count(data.get("generation_start")) else 0)
    try:
        state["offsets"] = check_offsets(data.get("offsets"))
        state["offsets"] = _fresh_state(None)["offsets"] | state["offsets"]
    except OffsetsError:
        pass
    state["run_starts"] = {k: v for k, v in _str_map(data.get("run_starts"), int).items()
                           if SESSION_ID.fullmatch(k) and _count(v)}
    state["titles"] = _str_map(data.get("titles"), str)
    state["journal_titles"] = _str_map(data.get("journal_titles"), str)
    archived = data.get("archived")
    state["archived"] = [a for a in archived if isinstance(a, str)] if isinstance(archived, list) else []
    seen = data.get("seen")
    return state, {k for k in seen if isinstance(k, str)} if isinstance(seen, list) else set()


def _apply(w: _Watched, reply: dict, sent: dict, canaries: list[dict], now: float) -> tuple[int, int, int]:
    """Match one reply's lines and rows, append their new hits; (hits added, lines dropped, hits over
    the per-poll limit). Offsets, run starts and titles are committed only once the whole reply is in.
    Only parsing and matching a line or row is guarded: an OSError writing the hits file raises out of
    here, so the poll fails and its offsets are not committed (the re-read is deduplicated by `seen`,
    which gets a key only once its hit is written). Module-level (not Watcher's) so --once can call it on
    a one-shot `_Watched` with no Watcher."""
    state = copy.deepcopy({k: w.state[k] for k in ("offsets", "run_starts", "titles", "journal_titles")})
    offsets, run_starts = state["offsets"], state["run_starts"]
    tally = {"added": 0, "dropped": 0, "over": 0}
    detected = _iso(now)

    def match(places: list[Place]) -> tuple[list[dict], bool]:
        """The hits of these places; and whether one place's matching raised (the others still count)."""
        found, bad = [], False
        for place in places:
            try:
                found += hits_for(place, canaries, w.ws.api_host)
            except Exception:
                bad = True
        return found, bad

    def record(found_hits: list[dict]) -> None:
        """Append the new ones. Not guarded: an OSError here fails the poll."""
        for found in found_hits:
            hit = {"id": None, "detected": detected, "workspace": w.ws.id, "instance": w.ws.instance,
                   "owner": w.ws.owner, **found}
            if hit["at"] is None and hit["source"] == "receiver":
                hit["at"] = detected  # the receiver's log has no time: when it was read
            key = dedup_key(hit, w.ws.generation)
            if key in w.seen or w.hits.full:
                continue
            if tally["added"] >= HITS_PER_POLL:
                tally["over"] += 1
                continue
            if w.hits.append(hit) is None:
                continue
            w.seen.add(key)
            w.kinds[hit["kind"]] += 1
            tally["added"] += 1

    def each(entry: dict, handle) -> None:
        """handle(parsed line, its start) -> its places, per line. A line is the participant's or the agent's:
        one that does not parse, nests too deep, or has a field of the wrong type is dropped, never the poll
        (which would then fail on it every time, its offsets never advancing past it)."""
        for line, start in zip(entry["lines"], entry["line_starts"]):
            try:
                places = handle(json.loads(line), start)
            except Exception:
                tally["dropped"] += 1
                continue
            found, bad = match(places)
            tally["dropped"] += bad
            record(found)

    files = reply["files"]
    for key in sorted(k for k in files if k.startswith("journal:")):  # journals first: their copy wins
        session = key.removeprefix("journal:")
        if not SESSION_ID.fullmatch(session):
            continue
        entry = files[key]
        reader = w.readers.get(session)
        if reader is None or entry["start"] < sent["journals"].get(session, 0):
            if entry["start"] < sent["journals"].get(session, 0):  # replaced: shorter than its offset
                run_starts.pop(session, None)
            reader = w.readers[session] = JournalReader(session)
            reader.title = state["journal_titles"].get(session)

        def journal_line(line: object, start: int, session: str = session,
                         reader: JournalReader = reader) -> list[Place]:
            places = reader.feed(line)
            kind = line.get("type") if isinstance(line, dict) else None
            run_id = line.get("run_id") if isinstance(line, dict) else None
            if (kind == "run_start" and isinstance(run_id, str) and session not in run_starts
                    and run_id in reader.runs):
                run_starts[session] = start  # the earliest open run: re-read from here after a restart
            elif kind == "run_end" and not reader.runs:
                run_starts.pop(session, None)
            return places

        each(entry, journal_line)
        if reader.title is not None and state["journal_titles"].get(session) != reader.title:
            _bounded(state["journal_titles"], session, reader.title)
        offsets["journals"][session] = entry["end"]
    def run_log_line(line: object, _start: int) -> list[Place]:
        if isinstance(line, dict) and line.get("type") == "title":
            if isinstance(line.get("thread_id"), str) and isinstance(line.get("title"), str):
                _bounded(state["titles"], line["thread_id"], line["title"])
            return []
        return agent_run_places(line, state["titles"])

    def receiver_line(line: object, _start: int) -> list[Place]:
        return receiver_places(line) if isinstance(line, dict) else []

    if "agent_runs" in files:
        each(files["agent_runs"], run_log_line)
        offsets["agent_runs"] = files["agent_runs"]["end"]
    if "receiver" in files:
        each(files["receiver"], receiver_line)
        offsets["receiver"] = files["receiver"]["end"]
    if reply["openwebui"] is not None:
        for row in reply["openwebui"]["rows"]:
            try:
                places = openwebui_places(row, "openwebui-db")  # `chat` is the row's JSON text, parsed there
            except Exception:  # a row of the wrong shape, like a line: dropped, never the poll
                tally["dropped"] += 1
                continue
            found, bad = match(places)
            tally["dropped"] += bad
            record(found)
        offsets["openwebui"] = reply["openwebui"]["max"]
    if tally["added"] or any(w.state[k] != v for k, v in state.items()):
        w.state.update(state)
        w.dirty = True
    return tally["added"], tally["dropped"], tally["over"]


@dataclass
class _Watched:
    """What the watcher holds for one workspace between ticks."""
    ws: Workspace
    state: dict
    seen: set[str]
    hits: HitsFile
    kinds: Counter
    status: dict
    readers: dict[str, JournalReader]
    next_poll: float = 0.0
    dirty: bool = True
    status_text: str = ""
    foreign: set[str] | None = None
    errors_seen: int = 0
    scan_retry: float = 0.0  # no archived run is scanned before this (a write of its hits failed)
    stop_note: str | None = None  # the stopped status's note ("archive incomplete")


class Watcher:
    """The daemon's loop body: `tick(now)` discovers the workspaces (at most every `discover_every`
    seconds; in between it keeps the last list), polls each running one whose poll is due, scans each new
    archived run of a workspace once, and writes the state and status files. A stop is still seen on the
    tick its run directory appears: the scan of runs_dir, every tick, marks the workspace stopped. A
    hosts.yml rewritten between discoveries (its mtime, statted every tick, is not the one discovered) is
    not polled under its stale generation: that workspace waits, and the next tick discovers again."""

    def __init__(self, hits_dir: str, reports_dir: str, runs_dir: str, output_root: str, transport: Transport,
                 hits_max: int = HITS_FILE_MAX, discover_every: float = DISCOVER_EVERY):
        self.hits_dir, self.runs_dir = Path(hits_dir), Path(runs_dir)
        self.reports_dir, self.output_root = reports_dir, output_root
        self.transport, self.hits_max = transport, hits_max
        self.discover_every = discover_every
        self.workspaces: list[Workspace] = []
        self.discovered: float | None = None  # when discover last ran
        self.watched: dict[str, _Watched] = {}
        self.hits_dir.mkdir(parents=True, exist_ok=True)

    def run_forever(self) -> None:
        while True:
            started = time.monotonic()
            try:
                self.tick(time.time())
            except Exception as e:  # never end the daemon; the class only (a message could carry data)
                logger.error("tick failed: %s", type(e).__name__)
            time.sleep(max(0.0, 1.0 - (time.monotonic() - started)))

    def tick(self, now: float) -> None:
        # Again when due, and whenever the clock went back (never stuck on a stale list).
        if self.discovered is None or not 0 <= now - self.discovered < self.discover_every:
            self.workspaces = discover(self.reports_dir, self.output_root, str(self.runs_dir))
            self.discovered = now
        current: dict[str, _Watched] = {}
        for ws in self.workspaces:
            w = self.watched.get(ws.id) or self._load(ws)
            w.ws = ws
            current[ws.id] = w
            try:
                self._step(w, now)
            except Exception as e:
                logger.error("%s: %s", ws.id, type(e).__name__)
        self.watched = current

    # loading and saving

    def _path(self, ws_id: str, suffix: str) -> Path:
        return self.hits_dir / f"{ws_id}{suffix}"

    def _load(self, ws: Workspace) -> _Watched:
        try:
            state, seen = _load_state(json.loads(self._path(ws.id, ".state.json").read_text(encoding="utf-8")))
        except FileNotFoundError:
            state, seen = _fresh_state(None), set()
        except (OSError, ValueError):
            logger.warning("%s: unreadable state file, starting afresh", ws.id)
            state, seen = _fresh_state(None), set()
        try:
            status = json.loads(self._path(ws.id, ".status.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            status = None
        if not isinstance(status, dict):
            status = {}
        hits = HitsFile(str(self._path(ws.id, ".jsonl")), self.hits_max)
        existing = hits.read()
        if state["generation"]:  # a hit written just before a crash, whose key the state missed
            # Only this generation's hits: an earlier one's receiver hit (keyed by workspace, generation and
            # canary only) would otherwise block the rebuilt instance's first delivered hit of that canary.
            seen |= {dedup_key(h, state["generation"]) for h in hits.read(after=state["generation_start"])
                     if isinstance(h.get("canary"), dict) and isinstance(h["canary"].get("token"), str)}
        kinds = Counter(h["kind"] for h in existing if isinstance(h.get("kind"), str))
        status = {"state": status.get("state"), "since": status.get("since"), "last_poll": status.get("last_poll"),
                  "hits": dict(kinds), "note": status.get("note")}
        return _Watched(ws=ws, state=state, seen=seen, hits=hits, kinds=kinds, status=status, readers={},
                        foreign=set(), stop_note=status["note"] if status["state"] == "stopped" else None)

    def _save(self, w: _Watched) -> None:
        if w.dirty:
            text = json.dumps(w.state | {"seen": sorted(w.seen)})
            _write_atomic(self._path(w.ws.id, ".state.json"), text, 0o600)
            w.dirty = False
        w.status["hits"] = dict(sorted(w.kinds.items()))
        text = json.dumps(w.status)
        if text != w.status_text:
            _write_atomic(self._path(w.ws.id, ".status.json"), text, 0o640)
            w.status_text = text

    def _set_state(self, w: _Watched, state: str, now: float, note: str | None = None) -> None:
        if w.status["state"] != state:
            w.status["state"], w.status["since"] = state, _iso(now)
        w.status["note"] = note

    # one workspace, one tick

    def _step(self, w: _Watched, now: float) -> None:
        ws = w.ws
        if ws.encrypted:  # the watcher cannot match: never polled, nothing scanned
            self._set_state(w, "encrypted", now, "canary record is encrypted")
            self._save(w)
            return
        try:
            hosts = (Path(ws.output_dir) / "hosts.yml").stat()
        except OSError:
            hosts = None
        if hosts is not None and ws.hosts_mtime_ns is not None and hosts.st_mtime_ns != ws.hosts_mtime_ns:
            # Rewritten since discovery: its generation is stale, so nothing is polled or scanned under it.
            self.discovered = None  # discover again on the next tick
            self._save(w)
            return
        if w.state["generation"] != ws.generation:  # a fresh instance: every offset starts again from 0
            # The last generation's runs first, with its own dedup keys: a stop the watcher was down for is
            # scanned before `seen` is cleared, so what polling already wrote is not written again.
            if (w.state["generation"] is not None and hosts is not None
                    and self._scan_runs(w, now, hosts.st_mtime, w.state["generation"], past=True)):
                self._save(w)  # one is left to scan (its write failed): the reset waits for it
                return
            w.state = _fresh_state(ws.generation, w.hits.count) | {"archived": w.state["archived"]}
            w.seen, w.readers, w.dirty, w.stop_note = set(), {}, True, None
        pending = self._scan_runs(w, now, hosts.st_mtime, ws.generation) if hosts is not None else False
        if w.hits.full:
            self._set_state(w, "capped", now, "hits file full")
        elif ws.running:
            if now >= w.next_poll:
                self._poll(w, now)
        elif not pending:
            self._set_state(w, "stopped", now, w.stop_note)
        self._save(w)

    def _scan_runs(self, w: _Watched, now: float, hosts_mtime: float, generation: str, past: bool = False) -> bool:
        """Scan each archived run of this workspace not yet scanned, once its index.md (written last)
        exists, over the whole directory with `generation`'s dedup keys (`w.seen`): what polling already
        found is not written again. A stop's run directory still without index.md ARCHIVE_WAIT seconds past
        its mtime is scanned as it is, the stop then noted "archive incomplete". A new run directory of this
        workspace newer than hosts.yml is its stop: `w.ws.running` turns false here, without waiting for the
        next discovery (which says the same). An OSError writing the hits leaves the run unscanned, retried
        after BACKOFF seconds. True while a stop's run directory is still to scan.

        `past`: only the run directories older than hosts.yml (the last generation's, before its reset),
        index.md or not (the rebuild that followed means its archive is done); `ws.running` untouched."""
        ws, suffix = w.ws, f"_{w.ws.instance}"
        try:
            entries = sorted(e for e in self.runs_dir.iterdir() if e.name.endswith(suffix))
        except OSError:
            return False
        pending = False
        for entry in entries:
            if entry.name in w.state["archived"] or entry.name in w.foreign or not entry.is_dir():
                continue
            try:
                mtime = entry.stat().st_mtime
            except OSError:
                continue
            stop = mtime >= hosts_mtime  # this generation's stop
            if past and stop:
                continue
            incomplete = not (entry / "index.md").exists()
            if incomplete and not past:
                if not stop:
                    continue  # an older run's directory, never finished: not this stop
                ws.running = False
                if now - mtime < ARCHIVE_WAIT:
                    pending = True
                    continue
            if archive_meta(str(entry)).get("workspace") != ws.id:
                w.foreign.add(entry.name)  # the same instance name, another workspace
                continue
            if stop:
                ws.running = False
            if now < w.scan_retry:
                pending = True
                continue
            before = w.hits.count
            meta = {"workspace": ws.id, "instance": ws.instance, "owner": ws.owner}
            try:
                count = scan_archive(str(entry), w.hits, w.seen, meta, ws.api_host, generation)
            except RecordError as e:  # the class only: its message can name the run's path
                logger.warning("%s: archived run not scanned (%s)", ws.id, type(e).__name__)
                count = 0
            except OSError as e:  # writing its hits: not marked scanned, tried again (`seen` keeps what was written)
                w.kinds.update(h["kind"] for h in w.hits.read(after=before) if isinstance(h.get("kind"), str))
                w.scan_retry, pending = now + BACKOFF, True
                logger.warning("%s: archived run scan failed (%s), again in %d s", ws.id, type(e).__name__, BACKOFF)
                continue
            except Exception as e:  # untrusted content: marked scanned all the same, never rescanned every tick
                logger.warning("%s: archived run scan failed (%s)", ws.id, type(e).__name__)
                count = w.hits.count - before
            w.kinds.update(h["kind"] for h in w.hits.read(after=before) if isinstance(h.get("kind"), str))
            w.state["archived"].append(entry.name)
            w.dirty = True
            if not past:
                w.stop_note = "archive incomplete" if incomplete else None
            logger.info("%s: %d new hits from archived run%s", ws.id, count,
                        " (incomplete: no index.md)" if incomplete else "")
        return pending

    def _offsets(self, w: _Watched) -> dict:
        """The offsets to hand the reader: a journal without a reader in memory (after a restart) is read
        again from its open run's run_start, so the run's pieces are whole again."""
        offsets = copy.deepcopy(w.state["offsets"])
        for uuid_, start in w.state["run_starts"].items():
            if uuid_ in offsets["journals"] and uuid_ not in w.readers:
                offsets["journals"][uuid_] = start
        return offsets

    def _poll(self, w: _Watched, now: float) -> None:
        sent = self._offsets(w)
        try:
            canaries = load_canaries(w.ws.output_dir)
            reply = check_reply(self.transport.read(w.ws, sent))
            added, dropped, over = _apply(w, reply, sent, canaries, now)
        except Exception as e:
            w.readers = {}  # half-fed: re-read from the committed offsets and run starts
            w.next_poll = now + BACKOFF
            self._set_state(w, "unreachable", now)
            # Only our own messages: another exception's could quote the reply (int('<token>') would), and a
            # RecordError's can name the output directory's path (the instance's name).
            reason = str(e) if isinstance(e, (PollError, OffsetsError)) else type(e).__name__
            logger.warning("%s: poll failed (%s), next in %d s", w.ws.id, reason, BACKOFF)
            return
        w.next_poll = now + POLL_EVERY
        w.status["last_poll"] = _iso(now)
        self._set_state(w, "capped" if w.hits.full else "running", now, "hits file full" if w.hits.full else None)
        if added:
            logger.info("%s: %d new hits", w.ws.id, added)
        if dropped:
            logger.info("%s: %d lines or rows that do not parse or are malformed dropped", w.ws.id, dropped)
        if over:
            logger.warning("%s: %d hits past %d in one poll dropped", w.ws.id, over, HITS_PER_POLL)
        errors = len(reply["errors"])
        if errors != w.errors_seen:
            logger.warning("%s: the reader reports %d source errors", w.ws.id, errors)
            w.errors_seen = errors


READER_SOURCES = ("sessions", "agent_runs", "receiver", "openwebui")  # the names `missing` and `errors` use
READER_ERROR = re.compile(r"(?:agent_runs|receiver|openwebui|journal:" + SESSION_ID.pattern + r"): [A-Za-z]+")


def _shown_reply(reply: dict) -> tuple[list[str], list[str], list[str]]:
    """What --once may print of a reply (the participant's): known source names, journal keys that are
    session ids, errors of the reader's own form (`<source>: <exception class>`). Anything else is only
    counted, as `<n> other`."""
    def shown(items, keep) -> list[str]:
        kept = sorted(i for i in items if isinstance(i, str) and keep(i))
        other = sum(1 for i in items if not (isinstance(i, str) and keep(i)))
        return kept + ([f"{other} other"] if other else [])

    def source(name: str) -> bool:
        return name in READER_SOURCES or (name.startswith("journal:")
                                          and SESSION_ID.fullmatch(name.removeprefix("journal:")) is not None)

    return (shown(list(reply["files"]), source), shown(reply["missing"], lambda n: n in READER_SOURCES),
            shown(reply["errors"], lambda e: READER_ERROR.fullmatch(e) is not None))


def once(output_dir: str, out: str, transport: Transport | None = None) -> int:
    """--once: one poll of output_dir's instance from zero offsets, appending new hits to `out`
    (ruling 5: a hand check only; the daemon never scans without a report sidecar). Writes
    nothing under the hits directory or /data-share: no state file, no status file. Prints the
    sources the reader found, what is missing, any source errors, and the hit count per kind --
    never a token, excerpt or line of a source. `transport` defaults to the real SshTransport;
    tests inject a LocalTransport instead."""
    try:
        ws = once_workspace(output_dir)
    except RecordError as e:
        print(f"canary_watch: {output_dir}: {e}", file=sys.stderr)
        return 1
    if ws.encrypted:
        print(f"canary_watch: {output_dir}: canary record is encrypted, not polled")
        return 1
    hits = HitsFile(out)
    kinds = Counter(h["kind"] for h in hits.read() if isinstance(h.get("kind"), str))
    seen = {dedup_key(h, ws.generation) for h in hits.read()
            if isinstance(h.get("canary"), dict) and isinstance(h["canary"].get("token"), str)}
    w = _Watched(ws=ws, state=_fresh_state(ws.generation), seen=seen, hits=hits, kinds=kinds, status={}, readers={})
    sent = w.state["offsets"]
    try:
        canaries = load_canaries(ws.output_dir)
        reply = check_reply((transport or SshTransport()).read(ws, sent))
        added, dropped, over = _apply(w, reply, sent, canaries, time.time())
    except Exception as e:
        # Only our own messages: another exception's could quote the reply.
        reason = str(e) if isinstance(e, (PollError, RecordError, OffsetsError)) else type(e).__name__
        print(f"canary_watch: poll failed ({reason})", file=sys.stderr)
        return 1
    sources, missing, errors = _shown_reply(reply)
    print(f"canary_watch: sources {sources}, missing {missing}, errors {errors}")
    note = f" (dropped {dropped}, over the per-poll cap {over})" if dropped or over else ""
    print(f"canary_watch: {added} new hits into {out}{note}; hits by kind: {dict(sorted(w.kinds.items()))}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Watch every running Coder workspace for canary hits (the daemon),"
                                     " or scan one archived run directory into a hits file (--archive).")
    parser.add_argument("--reports-dir", default=REPORTS_DIR, help="the report sidecars (default: %(default)s)")
    parser.add_argument("--runs-dir", default=RUNS_DIR, help="the archived runs (default: %(default)s)")
    parser.add_argument("--hits-dir", default=HITS_DIR, help="hits, state and status files (default: %(default)s)")
    parser.add_argument("--output-root", default=str(OUTPUT_ROOT), help="the instances' output directories"
                        " (default: this checkout's platform/ansible/output)")
    parser.add_argument("--archive", metavar="RUN_DIR", help="scan this archived run directory instead, then exit")
    parser.add_argument("--once", action="store_true", help="poll --output-dir's instance once, from zero offsets,"
                        " appending new hits to --out, then exit: a hand check only (never the daemon's path)")
    parser.add_argument("--output-dir", metavar="DIR", help="with --once: the instance's output directory to poll")
    parser.add_argument("--out", metavar="HITS.jsonl", help="with --archive or --once: the hits file to append to")
    parser.add_argument("--html", metavar="PAGE.html", help="with --archive: also render a standalone participant page"
                        " from the whole --out hits file (every hit in it, from all runs scanned into it, not only this one)")
    parser.add_argument("--api-host", metavar="HOST", help="with --archive: the instance's API host (default: its hosts.yml)")
    args = parser.parse_args(argv)
    if args.once:
        if args.archive:
            parser.error("--once and --archive are exclusive")
        if not args.output_dir or not args.out:
            parser.error("--once needs --output-dir and --out")
        if args.html or args.api_host:
            parser.error("--html and --api-host go with --archive, not --once")
        return once(args.output_dir, args.out)
    if not args.archive:
        if args.out or args.html or args.api_host:
            parser.error("--out, --html and --api-host go with --archive")
        logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(levelname)s %(message)s")
        watcher = Watcher(args.hits_dir, args.reports_dir, args.runs_dir, args.output_root, SshTransport())
        logger.info("watching %s into %s", args.reports_dir, args.hits_dir)
        watcher.run_forever()
        return 0
    if not args.out:
        parser.error("--archive needs --out")
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
