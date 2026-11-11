"""The canary hit viewer's reader (spec *Watcher*, *How it pulls*). Sent alone on the watcher's SSH
connection, source on stdin, and run as root on the instance:

    sudo -n python3 - '<offsets JSON>'

Offsets: `{"journals": {"<session uuid>": <int>}, "agent_runs": <int>, "receiver": <int>,
"windows": <int>, "openwebui": <number>}` (a missing key is 0). Prints one JSON object to stdout:

    {"files": {"journal:<uuid>" | "agent_runs" | "receiver" | "windows":
               {"size", "start", "end", "lines", "line_starts"}},
     "openwebui": {"rows": [{"id", "title", "updated_at", "chat"}], "max": <number>} | null,
     "missing": [str], "errors": [str]}

The five sources: AG-UI session journals (one file per session, `<chat-sessions mount>/*.jsonl`,
keyed `journal:<uuid>` where uuid is the file's stem), the agent's run log (`<agent-runs
mount>/runs.jsonl`, keyed `agent_runs`), the test receiver's request log
(`/var/lib/spe-eval-sink/requests.jsonl`, keyed `receiver`), spe-eval's evaluation windows
(`<home of uid 1000>/spe-eval/windows.jsonl`, keyed `windows`; the spe_eval role runs spe-eval as
uid 1000; no such user makes it "missing") and Open WebUI's chats
(`<open-webui-data mount>/webui.db`, keyed `openwebui`, read through sqlite3 rather than lines).
Volume mountpoints come from `docker volume inspect spe-frontend_<name> --format
'{{ .Mountpoint }}'`; a volume that does not exist (e.g. open-webui-data on an agui-only instance)
makes its source "missing", not an error. `missing` names the source that does not exist on this
instance: `sessions`, `agent_runs`, `receiver`, `windows` or `openwebui`; a session simply having no journal
yet is not "missing" (the sessions directory exists, just empty). `errors` carries a source-level
read failure that is not "it does not exist", as `"<name>: <exception class>"` (e.g. Open WebUI's
`chat` table missing, or its database locked).

`start` is where reading began for a file source: 0 when the file is shorter than the given offset
(it was replaced), else the offset given. `end` is the offset just past the last complete line
returned; a partial last line (no trailing newline yet) is left for the next poll. `line_starts`
gives the byte offset in the file of each returned line (the lines are decoded with
errors="replace", so the caller cannot recompute it from them): the watcher re-reads an open run
from its `run_start` line's offset after a restart. `windows` is read first, on a 1 MiB budget
of its own (two short lines per evaluation run: in practice all of it), since the watcher judges the
receiver's lines against it and leaves them for the next poll while it is not read to its end. The
other file sources are then read in this order: the journals (sorted by name), agent_runs, receiver;
they share one 1 MiB budget per call: past it, a source with nothing read yet still gets its first
complete line (so one oversized line cannot stall every source behind it), but nothing budgets it
less than guaranteed; `windows` has the same guarantee within its own budget. Open WebUI has its own 1 MiB budget on `chat` text, with the same
guarantee for its first row; rows are those with `updated_at >= offset` (whole seconds, so a chat
saved in the same second as the last row read is returned again — the caller's dedup keys drop the
repeat), ordered by it; `max` is the newest `updated_at` among the rows actually returned (not
necessarily every row past the offset, if the budget stopped early), so the next poll picks up
where this one left off.

The reader opens every file with `open(path, "rb")` and nothing else, and reads the Open WebUI
database over `sqlite3.connect(f"file:{path}?mode=ro", uri=True)`: strictly read-only (decision 1,
*Nothing on the instance changes*). The test override `SPE_READER_PATHS`, a JSON object
`{"sessions": dir, "agent_runs": file, "receiver": file, "windows": file, "webui_db": file}`, replaces
the docker volume lookup (and the receiver's and windows' otherwise-fixed paths) entirely; a key it omits or sets to null
behaves exactly like a volume that does not exist.

Standard library only, and no import of anything else in this repository: the reader is sent on its
own and has no `__file__` to find the rest of the checkout from.
"""
from __future__ import annotations

import json
import os
import pwd
import sqlite3
import subprocess
import sys
from pathlib import Path

ONE_MIB = 1 << 20
RECEIVER_PATH = "/var/lib/spe-eval-sink/requests.jsonl"
SPE_EVAL_UID = 1000  # the user spe-eval runs as (the spe_eval role asserts it)
# One name each for the files dict key, the offsets key, the SPE_READER_PATHS key and the
# missing/error name: all four happen to coincide for these sources. Read after the journals, in this
# order, on the shared budget; WINDOWS goes before them all, on its own.
FILE_SOURCES = ("agent_runs", "receiver")
WINDOWS = "windows"


def _volume_mountpoint(name: str) -> str | None:
    """The host mountpoint of docker volume `spe-frontend_<name>`, or None if the volume does not
    exist (e.g. an agui-only instance has no open-webui-data volume) or docker cannot be run."""
    try:
        done = subprocess.run(
            ["docker", "volume", "inspect", f"spe-frontend_{name}", "--format", "{{ .Mountpoint }}"],
            capture_output=True, text=True, timeout=10,
        )
    except OSError:
        return None
    if done.returncode != 0:
        return None
    mount = done.stdout.strip()
    return mount or None


def _windows_path() -> str | None:
    """spe-eval's windows.jsonl in the home of uid SPE_EVAL_UID; None when there is no such user."""
    try:
        home = pwd.getpwuid(SPE_EVAL_UID).pw_dir
    except KeyError:
        return None
    return os.path.join(home, "spe-eval", "windows.jsonl")


def _paths() -> dict[str, str | None]:
    """The five source paths: `sessions` (a directory) and `agent_runs`, `receiver`, `windows`,
    `webui_db` (files). `SPE_READER_PATHS` replaces the whole lookup, receiver's and windows' included."""
    override = os.environ.get("SPE_READER_PATHS")
    if override is not None:
        data = json.loads(override)
        return {name: data.get(name) for name in ("sessions", "agent_runs", "receiver", "windows", "webui_db")}
    sessions = _volume_mountpoint("chat-sessions")
    agent_runs = _volume_mountpoint("agent-runs")
    webui = _volume_mountpoint("open-webui-data")
    return {
        "sessions": sessions,
        "agent_runs": os.path.join(agent_runs, "runs.jsonl") if agent_runs else None,
        "receiver": RECEIVER_PATH,
        "windows": _windows_path(),
        "webui_db": os.path.join(webui, "webui.db") if webui else None,
    }


def _read_file(path: str, offset: int, remaining: int) -> tuple[int, int, int, list[str], list[int], int]:
    """(size, start, end, decoded complete lines past start, each line's byte offset, bytes consumed). Reads at most
    `remaining` bytes, except it always reads on to the first complete line, even past that budget
    (so a source given no budget left still returns its first line rather than nothing). `start` is
    0 when the file is shorter than `offset` (it was replaced). Read-only: `open(path, "rb")` only."""
    with open(path, "rb") as f:
        size = os.fstat(f.fileno()).st_size
        start = offset if isinstance(offset, int) and 0 <= offset <= size else 0
        f.seek(start)
        data = f.read(max(remaining, 0))
        while b"\n" not in data:
            chunk = f.read(65536)
            if not chunk:
                break
            data += chunk
    parts = data.split(b"\n")
    complete = parts[:-1]  # the last part is a partial line (or empty, when data ends with "\n")
    starts, at = [], start
    for p in complete:
        starts.append(at)
        at += len(p) + 1
    lines = [p.decode("utf-8", errors="replace") for p in complete]
    return size, start, at, lines, starts, at - start


def _read_source(name: str, paths: dict, offsets: dict, remaining: int, files: dict,
                 missing: list[str], errors: list[str]) -> int:
    """Read one named file source into `files`; the bytes it consumed (0 when missing or failed)."""
    path = paths.get(name)
    if path is None:
        missing.append(name)
        return 0
    try:
        size, start, end, lines, starts, consumed = _read_file(path, offsets.get(name, 0), remaining)
    except FileNotFoundError:
        missing.append(name)
        return 0
    except OSError as e:
        errors.append(f"{name}: {type(e).__name__}")
        return 0
    files[name] = {"size": size, "start": start, "end": end, "lines": lines, "line_starts": starts}
    return consumed


def _collect_files(paths: dict, offsets: dict, missing: list[str], errors: list[str]) -> dict[str, dict]:
    files: dict[str, dict] = {}
    _read_source(WINDOWS, paths, offsets, ONE_MIB, files, missing, errors)  # first, on its own budget
    remaining = ONE_MIB

    sessions_dir = paths.get("sessions")
    if sessions_dir is None or not os.path.isdir(sessions_dir):
        missing.append("sessions")
    else:
        journal_offsets = offsets.get("journals") or {}
        for journal in sorted(Path(sessions_dir).glob("*.jsonl")):
            uuid = journal.stem
            offset = journal_offsets.get(uuid, 0) if isinstance(journal_offsets, dict) else 0
            try:
                size, start, end, lines, starts, consumed = _read_file(str(journal), offset, remaining)
            except OSError as e:
                errors.append(f"journal:{uuid}: {type(e).__name__}")
                continue
            files[f"journal:{uuid}"] = {"size": size, "start": start, "end": end, "lines": lines, "line_starts": starts}
            remaining -= consumed

    for name in FILE_SOURCES:
        remaining -= _read_source(name, paths, offsets, remaining, files, missing, errors)
    return files


def _read_openwebui(path: str | None, offset: object, missing: list[str], errors: list[str]) -> dict | None:
    """Open WebUI's chats with `updated_at >= offset`, ordered by it, up to the 1 MiB budget on `chat`
    text (the module docstring says how).

    Paging is by `updated_at` alone, in whole seconds: should more than 1 MiB of chat text share one
    `updated_at` second, every poll returns the same first rows of that second and `max` never moves
    past it, so paging stalls there. Unlikely (it takes that much chat saved within one second); if it
    ever happens, page by `(updated_at, id)` instead."""
    if not isinstance(offset, (int, float)) or isinstance(offset, bool):
        offset = 0
    if path is None or not os.path.exists(path):
        missing.append("openwebui")
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            cur = conn.execute(
                "SELECT id, title, updated_at, chat FROM chat WHERE updated_at >= ? ORDER BY updated_at",
                (offset,),
            )
            rows: list[dict] = []
            total = 0
            newest = offset
            for row_id, title, updated_at, chat in cur:
                if rows and total >= ONE_MIB:
                    break
                rows.append({"id": row_id, "title": title, "updated_at": updated_at, "chat": chat})
                total += len(chat.encode("utf-8")) if isinstance(chat, str) else 0
                if isinstance(updated_at, (int, float)) and not isinstance(updated_at, bool) and updated_at > newest:
                    newest = updated_at
        finally:
            conn.close()
    except sqlite3.Error as e:
        errors.append(f"openwebui: {type(e).__name__}")
        return None
    return {"rows": rows, "max": newest}


def read(offsets: dict) -> dict:
    """The reader's full reply for one poll, given the offsets it was handed."""
    if not isinstance(offsets, dict):
        offsets = {}
    paths = _paths()
    missing: list[str] = []
    errors: list[str] = []
    files = _collect_files(paths, offsets, missing, errors)
    openwebui = _read_openwebui(paths.get("webui_db"), offsets.get("openwebui", 0), missing, errors)
    return {"files": files, "openwebui": openwebui, "missing": missing, "errors": errors}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        offsets = json.loads(argv[0]) if argv else {}
    except ValueError:
        offsets = {}
    print(json.dumps(read(offsets)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
