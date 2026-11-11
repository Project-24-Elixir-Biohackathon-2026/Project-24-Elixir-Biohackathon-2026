"""canary_reader.py: the script the watcher sends over SSH to read new lines and Open WebUI chats
(spec *Watcher*, *How it pulls*; decision 1, nothing on the instance changes; decision 10, read-only).
Run as a subprocess, as the watcher would: SPE_READER_PATHS stands in for the docker volume lookup."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

READER = Path(__file__).resolve().parents[1] / "canary_reader.py"
ONE_MIB = 1 << 20


def run_reader(offsets: dict, paths: dict) -> dict:
    env = dict(os.environ)
    env["SPE_READER_PATHS"] = json.dumps(paths)
    done = subprocess.run([sys.executable, str(READER), json.dumps(offsets)],
                          capture_output=True, text=True, timeout=30, env=env)
    assert done.returncode == 0, done.stderr
    assert done.stderr == ""
    return json.loads(done.stdout)


def make_chat_db(path: Path, rows: list[tuple]) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE chat (id TEXT, title TEXT, updated_at INTEGER, chat TEXT)")
    conn.executemany("INSERT INTO chat (id, title, updated_at, chat) VALUES (?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()


def test_reads_complete_lines_only(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    journal = sessions / "11111111-1111-1111-1111-111111111111.jsonl"
    journal.write_bytes(b'{"a": 1}\n{"a": 2}\npartial, no newline yet')
    result = run_reader({}, {"sessions": str(sessions)})
    key = "journal:11111111-1111-1111-1111-111111111111"
    entry = result["files"][key]
    assert entry["lines"] == ['{"a": 1}', '{"a": 2}']
    assert entry["start"] == 0
    assert entry["end"] == len(b'{"a": 1}\n{"a": 2}\n')
    assert entry["size"] == journal.stat().st_size
    assert "receiver" in result["missing"] and "agent_runs" in result["missing"]


def test_replaced_file_read_from_zero(tmp_path):
    agent_runs = tmp_path / "runs.jsonl"
    agent_runs.write_bytes(b'{"run_id": "r1"}\n')
    # The offset is past the (replaced, now shorter) file's size: read from 0, not from the offset.
    result = run_reader({"agent_runs": 10_000}, {"agent_runs": str(agent_runs)})
    entry = result["files"]["agent_runs"]
    assert entry["start"] == 0
    assert entry["lines"] == ['{"run_id": "r1"}']
    assert entry["end"] == len(b'{"run_id": "r1"}\n')


def test_cap_one_mib(tmp_path):
    # agent_runs alone is well past the 1 MiB budget; receiver is small. The budget is shared, but
    # receiver (read after agent_runs) still gets its one line: it is not stalled by agent_runs.
    line = b'{"x": "' + b"y" * 1000 + b'"}'
    agent_runs = tmp_path / "runs.jsonl"
    agent_runs.write_bytes((line + b"\n") * 2000)  # ~ 2 MiB
    receiver = tmp_path / "requests.jsonl"
    receiver.write_bytes(b'{"request": 1}\n')
    result = run_reader({}, {"agent_runs": str(agent_runs), "receiver": str(receiver)})
    runs_entry = result["files"]["agent_runs"]
    assert runs_entry["end"] < runs_entry["size"]  # not all of it: the rest waits for the next poll
    assert runs_entry["end"] <= ONE_MIB
    assert result["files"]["receiver"]["lines"] == ['{"request": 1}']  # still returned, not stalled


def test_source_not_stalled_when_budget_already_spent(tmp_path):
    # One giant single-line journal with no newline until its very end: reading it forces the
    # shared budget deeply negative (the only way to return even its first line is to read past
    # the cap). agent_runs, read after it, must still get its one line: the guarantee holds even
    # when the budget left for it is negative, not just small.
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    giant = b'{"a": "' + b"z" * (2 * ONE_MIB) + b'"}\n'
    (sessions / "33333333-3333-3333-3333-333333333333.jsonl").write_bytes(giant)
    agent_runs = tmp_path / "runs.jsonl"
    agent_runs.write_bytes(b'{"run_id": "r1"}\n')
    result = run_reader({}, {"sessions": str(sessions), "agent_runs": str(agent_runs)})
    journal_entry = result["files"]["journal:33333333-3333-3333-3333-333333333333"]
    assert journal_entry["end"] == len(giant)  # the one line, read in full despite the cap
    assert result["files"]["agent_runs"]["lines"] == ['{"run_id": "r1"}']


def test_openwebui_rows_since(tmp_path):
    db = tmp_path / "webui.db"
    make_chat_db(db, [
        ("c1", "first", 100, '{"history": {}}'),
        ("c2", "second", 200, '{"history": {}}'),
        ("c3", "third", 300, '{"history": {}}'),
    ])
    result = run_reader({"openwebui": 150}, {"webui_db": str(db)})
    owui = result["openwebui"]
    assert [r["id"] for r in owui["rows"]] == ["c2", "c3"]
    assert owui["max"] == 300
    assert result["errors"] == []


def test_openwebui_missing_table_is_error(tmp_path):
    db = tmp_path / "webui.db"
    sqlite3.connect(str(db)).close()  # a database file, but no `chat` table
    result = run_reader({}, {"webui_db": str(db)})
    assert result["openwebui"] is None
    assert len(result["errors"]) == 1
    assert result["errors"][0].startswith("openwebui: ")
    assert "openwebui" not in result["missing"]  # it exists; the query just failed


def test_missing_source_listed(tmp_path):
    result = run_reader({}, {})
    assert set(result["missing"]) == {"sessions", "agent_runs", "receiver", "windows", "openwebui"}
    assert result["files"] == {}
    assert result["openwebui"] is None


def test_reader_is_read_only(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    journal = sessions / "22222222-2222-2222-2222-222222222222.jsonl"
    journal.write_bytes(b'{"a": 1}\n')
    agent_runs = tmp_path / "runs.jsonl"
    agent_runs.write_bytes(b'{"run_id": "r1"}\n')
    receiver = tmp_path / "requests.jsonl"
    receiver.write_bytes(b'{"request": 1}\n')
    db = tmp_path / "webui.db"
    make_chat_db(db, [("c1", "t", 1, '{}')])

    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (journal, agent_runs, receiver, db)}
    run_reader({}, {"sessions": str(sessions), "agent_runs": str(agent_runs),
                    "receiver": str(receiver), "webui_db": str(db)})
    for p, (data, mtime) in before.items():
        assert p.read_bytes() == data
        assert p.stat().st_mtime_ns == mtime

    source = READER.read_text()
    for forbidden in ('"w"', "'w'", '"a"', "'a'", '"r+"', "'r+'", "unlink(", "rename(", "os.remove("):
        assert forbidden not in source, forbidden


def test_line_starts_are_byte_offsets(tmp_path):
    """Each returned line's byte offset, from which the watcher re-reads an open run after a restart: exact
    even past bytes that are not UTF-8 (the lines are decoded with errors="replace")."""
    agent_runs = tmp_path / "runs.jsonl"
    raw = [b'{"a": "\xc3\xa9t\xc3\xa9"}', b'{"b": "\xff\xfe"}', b'{"c": 3}']
    agent_runs.write_bytes(b"\n".join(raw) + b"\n" + b"partial")
    first = len(raw[0]) + 1
    result = run_reader({"agent_runs": first}, {"agent_runs": str(agent_runs)})
    entry = result["files"]["agent_runs"]
    assert entry["start"] == first
    assert entry["line_starts"] == [first, first + len(raw[1]) + 1]
    assert len(entry["line_starts"]) == len(entry["lines"])
    data = agent_runs.read_bytes()
    for start, line in zip(entry["line_starts"], entry["lines"]):
        assert data[start:].split(b"\n", 1)[0].decode("utf-8", errors="replace") == line


def test_windows_is_a_file_source(tmp_path):
    windows = tmp_path / "windows.jsonl"
    line = b'{"run": "t1", "experiment": "x", "start": "2026-11-11T10:00:00Z", "end": null}\n'
    windows.write_bytes(line + b'{"run": "t1"')
    result = run_reader({"windows": 0}, {"windows": str(windows)})
    assert result["files"]["windows"]["lines"] == [line.decode().rstrip("\n")]
    assert result["files"]["windows"]["end"] == len(line)
    assert "windows" not in result["missing"]
    again = run_reader({"windows": len(line)}, {"windows": str(windows)})
    assert again["files"]["windows"]["lines"] == [] and again["files"]["windows"]["start"] == len(line)
    gone = run_reader({}, {"windows": str(tmp_path / "nope.jsonl")})
    assert "windows" in gone["missing"] and "windows" not in gone["files"] and gone["errors"] == []


def test_windows_path_is_uid_1000s_home(monkeypatch):
    sys.path.insert(0, str(READER.parent))
    import canary_reader
    import pwd
    monkeypatch.delenv("SPE_READER_PATHS", raising=False)
    monkeypatch.setattr(canary_reader, "_volume_mountpoint", lambda name: None)
    seen = []

    def getpwuid(uid):
        seen.append(uid)
        return pwd.struct_passwd(("ubuntu", "x", 1000, 1000, "", "/home/ubuntu", "/bin/bash"))

    monkeypatch.setattr(canary_reader.pwd, "getpwuid", getpwuid)
    assert canary_reader._paths()["windows"] == "/home/ubuntu/spe-eval/windows.jsonl" and seen == [1000]

    def no_user(uid):
        raise KeyError(uid)

    monkeypatch.setattr(canary_reader.pwd, "getpwuid", no_user)
    assert canary_reader._paths()["windows"] is None


def test_windows_read_first_and_outside_the_shared_budget(tmp_path):
    # A journal well past the shared 1 MiB budget: windows, read before it on a budget of its own, still
    # comes back whole (the watcher judges receiver lines against it), and the receiver gets its guarantee.
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    line = b'{"x": "' + b"y" * 1000 + b'"}\n'
    (sessions / "44444444-4444-4444-4444-444444444444.jsonl").write_bytes(line * 2000)  # ~ 2 MiB
    windows = tmp_path / "windows.jsonl"
    opened = b'{"run": "t1", "experiment": "x", "start": "2026-11-11T10:00:00Z", "end": null}\n'
    closed = b'{"run": "t1", "experiment": "x", "start": "2026-11-11T10:00:00Z", "end": "2026-11-11T10:05:00Z"}\n'
    earlier = b'{"run": "e", "experiment": "' + b"x" * 200 + b'", "start": "2026-11-10T10:00:00Z", "end": null}\n'
    windows.write_bytes(opened + earlier * 400 + closed)  # past the 64 KiB read on to a first line
    receiver = tmp_path / "requests.jsonl"
    receiver.write_bytes(b'{"request": 1}\n')
    result = run_reader({}, {"sessions": str(sessions), "windows": str(windows), "receiver": str(receiver)})
    assert list(result["files"])[0] == "windows"
    entry = result["files"]["windows"]
    assert entry["end"] == entry["size"] == windows.stat().st_size and len(entry["lines"]) == 402
    journal = result["files"]["journal:44444444-4444-4444-4444-444444444444"]
    assert journal["end"] < journal["size"]  # the shared budget ran out in the journal
    assert result["files"]["receiver"]["lines"] == ['{"request": 1}']
