"""canary_watch.py: the hits file, the scan of one archived run, and discover (decisions 3, 5, 9,
10). The fixture run in fixtures/canary/run/ is laid out as run_archive writes it, with made-up
tokens only."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import canary_hits  # noqa: E402
import canary_record  # noqa: E402
import canary_watch  # noqa: E402
from canary_hits import HitsFile  # noqa: E402

HERE = Path(__file__).resolve().parent
RUN = HERE / "fixtures" / "canary" / "run"
WATCH = HERE.parent / "canary_watch.py"
API_HOST = "api.spe.test"
WORKSPACE = "6f1c2a9e-3b7d-4e1a-9c2f-0a1b2c3d4e5f"
META = {"workspace": WORKSPACE, "instance": "fixture", "owner": "alice"}
TOKENS = [t["token"] for t in canary_record.load_canaries(RUN)]


def scan(tmp_path: Path, seen: set[str] | None = None, run: Path = RUN) -> tuple[HitsFile, int]:
    hits = HitsFile(str(tmp_path / "hits.jsonl"))
    return hits, canary_watch.scan_archive(str(run), hits, set() if seen is None else seen, META, API_HOST, "archive")


def test_archive_one_hit_per_canary_and_place(tmp_path):
    hits, count = scan(tmp_path)
    records = hits.read()
    assert count == len(records)
    r1 = [h for h in records if h["run"] == "r1"]
    keys = [(h["place"], (h["tool"] or {}).get("call_id"), h["canary"]["token"]) for h in r1]
    assert len(keys) == len(set(keys))  # one hit per canary and place, not one per copy
    assert sorted(keys, key=str) == sorted([
        ("prompt", None, "FCANARY-TEST011"),
        ("tool_args", "call1", "FCANARY-TEST01"),
        ("tool_result", "call2", "FCANARY-TEST01"),
        ("tool_args", "call3", "FCANARY-TEST01"),
        ("answer", None, "FCANARY-TEST01"),
    ], key=str)
    assert {h["source"] for h in r1} == {"agui-journal"}  # journals first: their copy wins
    assert {h["frontend"] for h in r1} == {"agui"}
    # The run only the run log has still gives its hit.
    assert [(h["source"], h["kind"]) for h in records if h["run"] == "r9"] == [("agent-runs", "answer")]
    # agui/openwebui-export.json (the journals reshaped) is never read.
    assert not [h for h in records if h["frontend"] == "openwebui" and h["session"]["id"] == "s1"]
    for h in records:
        assert {k: h[k] for k in META} == META
        assert h["detected"].endswith("Z")
        assert set(h) == {"id", "detected", "at", "workspace", "instance", "owner", "frontend", "source", "session",
                          "run", "prompt", "kind", "place", "tool", "canary", "excerpt"}


def test_archive_reads_openwebui_export(tmp_path):
    hits, _ = scan(tmp_path)
    owui = [h for h in hits.read() if h["frontend"] == "openwebui"]
    assert [(h["session"]["id"], h["run"], h["kind"], h["source"]) for h in owui] == [
        ("owc1", "a1", "touched", "archive")]


def test_openwebui_resaved_once(tmp_path):
    seen: set[str] = set()
    hits, first = scan(tmp_path, seen)
    assert first > 0
    assert canary_watch.scan_archive(str(RUN), hits, seen, META, API_HOST, "archive") == 0
    assert len(hits.read()) == first


def test_openwebui_live_then_archive_once(tmp_path):
    """A chat read live from the database, then in the archive's export: one hit per canary and place."""
    hits = HitsFile(str(tmp_path / "hits.jsonl"))
    seen: set[str] = set()
    canaries = canary_record.load_canaries(RUN)
    chat = json.loads((RUN / "openwebui-export.json").read_text())["chats"][0]
    row = {"id": chat["id"], "title": chat["title"], "chat": json.dumps(chat["chat"])}
    for place in canary_hits.openwebui_places(row, "openwebui-db"):
        for hit in canary_hits.hits_for(place, canaries, API_HOST):
            hit |= META
            seen.add(canary_hits.dedup_key(hit, "g1"))
            hits.append(hit)
    canary_watch.scan_archive(str(RUN), hits, seen, META, API_HOST, "g1")
    owui = [h for h in hits.read() if h["frontend"] == "openwebui"]
    assert [h["source"] for h in owui] == ["openwebui-db"]


def test_ids_are_line_numbers(tmp_path):
    hits, _ = scan(tmp_path)
    lines = (tmp_path / "hits.jsonl").read_text().splitlines()
    assert [json.loads(line)["id"] for line in lines] == list(range(1, len(lines) + 1))
    assert [h["id"] for h in hits.read(after=2)] == list(range(3, len(lines) + 1))
    # A second HitsFile on the same path carries on from the last line.
    again = HitsFile(str(tmp_path / "hits.jsonl"))
    assert again.append({"kind": "answer"}) == len(lines) + 1


def test_hits_file_mode_0640(tmp_path):
    old = os.umask(0o077)  # tighter than 0640: only the fchmod gives group read
    try:
        hits = HitsFile(str(tmp_path / "hits.jsonl"))
        hits.append({"kind": "answer"})
    finally:
        os.umask(old)
    assert stat.S_IMODE(os.stat(tmp_path / "hits.jsonl").st_mode) == 0o640


def test_hits_file_read_survives_a_cut_multibyte_line(tmp_path):
    path = tmp_path / "hits.jsonl"
    whole = json.dumps({"id": 1, "excerpt": "\u00e9t\u00e9"}, ensure_ascii=False).encode() + b"\n"
    cut = json.dumps({"id": 2, "excerpt": "\u00e9"}, ensure_ascii=False).encode()[:-3] + b"\xc3"
    path.write_bytes(whole + cut)
    assert [h["id"] for h in HitsFile(str(path)).read()] == [1]


def test_hits_file_cap(tmp_path):
    hits = HitsFile(str(tmp_path / "hits.jsonl"), max_bytes=2000)
    ids = [hits.append({"excerpt": "x" * 300}) for _ in range(10)]
    assert None in ids
    assert hits.full
    kept = [i for i in ids if i is not None]
    assert kept == list(range(1, len(kept) + 1))
    assert ids[len(kept):] == [None] * (10 - len(kept))
    assert os.path.getsize(tmp_path / "hits.jsonl") <= 2000
    assert hits.append({"kind": "answer"}) is None


def test_meta_from_run_yml_without_report(tmp_path):
    run = tmp_path / "run"
    shutil.copytree(RUN, run)
    (run / "report.json").unlink()
    assert canary_watch.archive_meta(str(run)) == {"workspace": None, "instance": "fixture", "owner": "alice"}
    assert canary_watch.archive_meta(str(RUN)) == META


def test_cli_logs_no_token(tmp_path):
    out = tmp_path / "hits.jsonl"
    page = tmp_path / "hits.html"
    done = subprocess.run([sys.executable, str(WATCH), "--archive", str(RUN), "--out", str(out),
                           "--html", str(page), "--api-host", API_HOST], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    logs = done.stdout + done.stderr
    assert logs.strip()
    assert TOKENS
    for token in TOKENS:
        assert token not in logs
    assert "FCANARY" not in logs and "MCANARY" not in logs
    assert stat.S_IMODE(page.stat().st_mode) == 0o640
    assert "<mark>" in page.read_text()
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".")] == []  # no temp file left
    assert len(out.read_text().splitlines()) > 0
    assert {json.loads(line)["workspace"] for line in out.read_text().splitlines()} == {WORKSPACE}


def test_cli_missing_record_fails_without_token(tmp_path):
    run = tmp_path / "run"
    shutil.copytree(RUN, run)
    (run / "canaries.json").unlink()
    done = subprocess.run([sys.executable, str(WATCH), "--archive", str(run), "--out", str(tmp_path / "h.jsonl")],
                          capture_output=True, text=True, timeout=60)
    assert done.returncode != 0
    assert "canaries.json" in done.stderr


def test_lone_surrogate_in_a_source_line(tmp_path):
    """Untrusted JSON can carry a lone surrogate ("\\ud800"): the scan completes, the hit is kept, and
    the hits file stays valid UTF-8 JSON (the surrogate written as U+FFFD, offsets unchanged)."""
    run = tmp_path / "run"
    shutil.copytree(RUN, run)
    record = {"run_id": "r8\udc00", "thread_id": "s8\udc00", "started": 1793714800.0, "input": "go", "tool_calls": [],
              "answer": "\ud800 The flag is FCANARY-TEST01."}
    with open(run / "agui" / "agent-runs.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")  # ensure_ascii: the line holds the \ud800 escape
    hits, count = scan(tmp_path, run=run)
    raw = (tmp_path / "hits.jsonl").read_bytes()
    raw.decode("utf-8")  # strict: valid UTF-8
    records = hits.read()
    assert count == len(records)
    r8 = [h for h in records if h["run"] == "r8\ufffd"]  # a surrogate in the run id too
    assert [(h["kind"], h["canary"]["token"]) for h in r8] == [("answer", "FCANARY-TEST01")]
    excerpt = r8[0]["excerpt"]
    assert excerpt["text"].startswith("� ")
    assert excerpt["text"][excerpt["start"]:excerpt["end"]] == "FCANARY-TEST01"
    assert [h["session"]["id"] for h in records if h["frontend"] == "openwebui"] == ["owc1"]  # later hits kept


def test_cli_rerun_with_surrogate_adds_nothing(tmp_path):
    """The key of a hit read back from the file (surrogate written as U+FFFD) matches a fresh scan's."""
    run = tmp_path / "run"
    shutil.copytree(RUN, run)
    with open(run / "agui" / "agent-runs.jsonl", "a") as f:
        f.write(json.dumps({"run_id": "r8\udc00", "thread_id": "s8", "answer": "FCANARY-TEST01 \ud800"}) + "\n")
    out = tmp_path / "hits.jsonl"
    argv = [sys.executable, str(WATCH), "--archive", str(run), "--out", str(out), "--api-host", API_HOST]
    assert subprocess.run(argv, capture_output=True, timeout=60).returncode == 0
    lines = out.read_text().splitlines()
    done = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0 and " 0 new hits" in done.stdout
    assert out.read_text().splitlines() == lines


# --- discover: which Coder workspaces the watcher scans, and their generations (decision 9) ---

WS1 = "11111111-1111-1111-1111-111111111111"
WS2 = "22222222-2222-2222-2222-222222222222"


def _hosts_yml(path: Path, api_host: str = "api.spe.test", ssh_target: str = "localhost") -> None:
    path.write_text(
        "instance: " + path.parent.name + "\n"
        "api_host: " + api_host + "\n"
        "ssh_user: ubuntu\n"
        "provision: existing\n"
        "ssh_target: " + ssh_target + "\n"
    )


def _sidecar(reports_dir: Path, workspace_id: str, instance: str, owner: str = "alice") -> Path:
    path = reports_dir / f"{workspace_id}.json"
    path.write_text(json.dumps({"owner": owner, "workspace": f"{owner}-ws", "instance": instance,
                                "created": "2026-11-10 14:00 UTC", "parameters": {}}))
    return path


def _output_dir(output_root: Path, instance: str, encrypted: bool = False, no_record: bool = False) -> Path:
    directory = output_root / instance
    directory.mkdir(parents=True)
    _hosts_yml(directory / "hosts.yml")
    if no_record:
        pass
    elif encrypted:
        (directory / "canaries.json.age").write_text("age-encrypted-stub")
    else:
        (directory / "canaries.json").write_text(json.dumps(
            {"tokens": [{"token": "FCANARY-TEST01", "type": "file", "file": "flag.txt"}]}))
    return directory


def _layout(tmp_path: Path) -> tuple[Path, Path, Path]:
    reports = tmp_path / "reports"
    reports.mkdir()
    output_root = tmp_path / "output"
    runs = tmp_path / "runs"
    runs.mkdir()
    return reports, output_root, runs


def test_no_sidecar_never_scanned(tmp_path):
    """An output directory with canaries.json and hosts.yml but no sidecar is not in discover."""
    reports, output_root, runs = _layout(tmp_path)
    _output_dir(output_root, "ws1")
    assert canary_watch.discover(str(reports), str(output_root), str(runs)) == []


def test_newest_sidecar_wins(tmp_path):
    """Two sidecars naming one instance (deleted and recreated under the same name): the newer only."""
    reports, output_root, runs = _layout(tmp_path)
    _output_dir(output_root, "ws1")
    old = _sidecar(reports, WS1, "ws1", owner="old-owner")
    new = _sidecar(reports, WS2, "ws1", owner="new-owner")
    now = time.time()
    os.utime(old, (now - 100, now - 100))
    os.utime(new, (now, now))
    result = canary_watch.discover(str(reports), str(output_root), str(runs))
    assert [w.id for w in result] == [WS2]
    assert [w.owner for w in result] == ["new-owner"]


def test_running_until_archived(tmp_path):
    """running while hosts.yml is newer than every runs_dir/*_<instance> directory; an archive dir
    newer than hosts.yml makes it not running. A run dir for a different instance does not match
    (exact suffix, not a prefix of it: ws1 must not match x_ws10)."""
    reports, output_root, runs = _layout(tmp_path)
    directory = _output_dir(output_root, "ws1")
    _sidecar(reports, WS1, "ws1")
    [w] = canary_watch.discover(str(reports), str(output_root), str(runs))
    assert w.running is True
    assert w.instance == "ws1"
    assert w.output_dir == str(directory)
    assert w.api_host == "api.spe.test"
    assert w.ssh.user == "ubuntu" and w.ssh.host == "localhost"
    assert w.encrypted is False

    unrelated = runs / "20261110T000000_x_ws10"  # must not match instance "ws1"
    unrelated.mkdir()
    [w] = canary_watch.discover(str(reports), str(output_root), str(runs))
    assert w.running is True

    archived = runs / "20261110T010000_ws1"
    archived.mkdir()
    now = time.time()
    os.utime(archived, (now + 1000, now + 1000))  # newer than hosts.yml
    [w] = canary_watch.discover(str(reports), str(output_root), str(runs))
    assert w.running is False


def test_encrypted_record(tmp_path):
    """A workspace whose record is only canaries.json.age is still returned, flagged encrypted."""
    reports, output_root, runs = _layout(tmp_path)
    _output_dir(output_root, "ws1", encrypted=True)
    _sidecar(reports, WS1, "ws1")
    [w] = canary_watch.discover(str(reports), str(output_root), str(runs))
    assert w.encrypted is True


def test_neither_record_file_is_skipped(tmp_path):
    """Neither canaries.json nor canaries.json.age: the workspace is skipped entirely."""
    reports, output_root, runs = _layout(tmp_path)
    _output_dir(output_root, "ws1", no_record=True)
    _sidecar(reports, WS1, "ws1")
    assert canary_watch.discover(str(reports), str(output_root), str(runs)) == []


def test_generation_changes_with_hosts_yml(tmp_path):
    """generation is a SHA-256 of hosts.yml's bytes and mtime: a rewrite with the same bytes but a
    later mtime, and a rewrite with different bytes, both start a new generation."""
    reports, output_root, runs = _layout(tmp_path)
    directory = _output_dir(output_root, "ws1")
    _sidecar(reports, WS1, "ws1")
    hosts_path = directory / "hosts.yml"

    [w1] = canary_watch.discover(str(reports), str(output_root), str(runs))
    data = hosts_path.read_bytes()
    now = time.time()
    os.utime(hosts_path, (now + 10, now + 10))  # same bytes, later mtime
    [w2] = canary_watch.discover(str(reports), str(output_root), str(runs))
    assert hosts_path.read_bytes() == data
    assert w1.generation != w2.generation

    hosts_path.write_text(hosts_path.read_text() + "extra: value\n")  # different bytes
    os.utime(hosts_path, (now + 20, now + 20))
    [w3] = canary_watch.discover(str(reports), str(output_root), str(runs))
    assert w3.generation != w2.generation


def test_bad_or_unmatched_sidecars_are_skipped(tmp_path):
    """A sidecar that is not valid JSON, lacks `instance`, or whose filename is not a UUID: never
    raises out of discover, just skipped. A sidecar naming an instance with no hosts.yml at all is
    skipped too."""
    reports, output_root, runs = _layout(tmp_path)
    _output_dir(output_root, "ws1")
    _sidecar(reports, WS1, "ws1")
    (reports / "not-a-uuid.json").write_text(json.dumps({"instance": "ws1", "owner": "mallory"}))
    (reports / f"{WS2}.json").write_text("{not json")
    third = reports / "33333333-3333-3333-3333-333333333333.json"
    third.write_text(json.dumps({"owner": "eve"}))  # no "instance"
    fourth = reports / "44444444-4444-4444-4444-444444444444.json"
    fourth.write_text(json.dumps({"instance": "no-such-instance", "owner": "eve"}))
    [w] = canary_watch.discover(str(reports), str(output_root), str(runs))
    assert w.instance == "ws1"


def test_once_workspace_has_no_sidecar_and_is_always_running(tmp_path):
    """once_workspace builds a Workspace straight from an output directory: id "once", no owner,
    running True (there is no runs_dir to weigh it against), encrypted/generation as discover
    computes them from the same directory."""
    output_root = tmp_path / "output"
    directory = _output_dir(output_root, "ws1")
    w = canary_watch.once_workspace(str(directory))
    assert w.id == "once" and w.owner is None and w.instance == "ws1"
    assert w.output_dir == str(directory) and w.running is True and w.encrypted is False
    assert w.api_host == "api.spe.test" and w.ssh.user == "ubuntu" and w.ssh.host == "localhost"
    # Matches discover()'s own generation for the same hosts.yml.
    reports, _, runs = _layout(tmp_path)
    _sidecar(reports, WS1, "ws1")
    [discovered] = canary_watch.discover(str(reports), str(output_root), str(runs))
    assert w.generation == discovered.generation


def test_once_workspace_encrypted_record(tmp_path):
    output_root = tmp_path / "output"
    directory = _output_dir(output_root, "ws1", encrypted=True)
    w = canary_watch.once_workspace(str(directory))
    assert w.encrypted is True


def test_once_workspace_no_record_raises(tmp_path):
    output_root = tmp_path / "output"
    directory = _output_dir(output_root, "ws1", no_record=True)
    with pytest.raises(canary_record.RecordError):
        canary_watch.once_workspace(str(directory))


def test_once_workspace_no_hosts_yml_raises(tmp_path):
    output_root = tmp_path / "output"
    directory = output_root / "ws1"
    directory.mkdir(parents=True)
    with pytest.raises(canary_record.RecordError):
        canary_watch.once_workspace(str(directory))


# --- the daemon: polling a fake instance, state, status, the scan on stop (decisions 1, 3, 10) ---

import logging  # noqa: E402
import shlex  # noqa: E402
import sqlite3  # noqa: E402

FIXTURES = HERE / "fixtures" / "canary"
SESSION = "aaaaaaaa-1111-4222-8333-444444444444"
JOURNAL = (FIXTURES / "agui-journals" / "s1.jsonl").read_text().splitlines(keepends=True)
JOURNAL_LINES = [line.rstrip("\n") for line in JOURNAL]
CHAT = json.loads((FIXTURES / "openwebui-export.json").read_text())["chats"][0]
R1_KEYS = sorted([
    ("prompt", None, "FCANARY-TEST011"),
    ("tool_args", "call1", "FCANARY-TEST01"),
    ("tool_result", "call2", "FCANARY-TEST01"),
    ("tool_args", "call3", "FCANARY-TEST01"),
    ("answer", None, "FCANARY-TEST01"),
], key=str)


def _index(event_type: str, call_id: str | None = None) -> int:
    """The index in JOURNAL of the first line carrying this event (and tool call)."""
    for n, line in enumerate(JOURNAL):
        event = json.loads(line).get("event") or {}
        if event.get("type") == event_type and (call_id is None or event.get("toolCallId") == call_id):
            return n
    raise LookupError(event_type)


def _keys(hits: list[dict], run: str = "r1") -> list[tuple]:
    return sorted([(h["place"], (h["tool"] or {}).get("call_id"), h["canary"]["token"])
                   for h in hits if h["run"] == run], key=str)


def _chat_db(path: Path, updated_at: int) -> None:
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE chat (id TEXT, title TEXT, updated_at INTEGER, chat TEXT)")
    conn.execute("INSERT INTO chat VALUES (?, ?, ?, ?)", (CHAT["id"], CHAT["title"], updated_at, json.dumps(CHAT["chat"])))
    conn.commit()
    conn.close()


class Counting(canary_watch.Transport):
    """Wraps a transport, counting its calls; `fail` makes it raise instead."""

    def __init__(self, inner=None, replies=None, fail=False):
        self.inner, self.replies, self.fail, self.calls = inner, list(replies or []), fail, []

    def read(self, ws, offsets):
        self.calls.append(json.loads(json.dumps(offsets)))
        if self.fail:
            raise RuntimeError("connection refused")
        if self.replies:
            return self.replies.pop(0)
        return self.inner.read(ws, offsets)


class Fake:
    """A fake instance on tmp_path (its four sources, read by LocalTransport) and the portal's directories."""

    def __init__(self, tmp_path: Path, encrypted: bool = False):
        self.reports, self.output_root, self.runs = _layout(tmp_path)
        self.out = self.output_root / "fixture"
        self.out.mkdir(parents=True)
        shutil.copy(FIXTURES / "hosts.yml", self.out / "hosts.yml")
        if encrypted:
            (self.out / "canaries.json.age").write_text("age-encrypted-stub")
        else:
            shutil.copy(FIXTURES / "canaries.json", self.out / "canaries.json")
        _sidecar(self.reports, WORKSPACE, "fixture")
        self.instance = tmp_path / "instance"
        (self.instance / "sessions").mkdir(parents=True)
        self.journal = self.instance / "sessions" / f"{SESSION}.jsonl"
        self.agent_runs = self.instance / "runs.jsonl"
        self.receiver = self.instance / "requests.jsonl"
        self.db = self.instance / "webui.db"
        self.hits_dir = tmp_path / "hits"
        self.paths = {"sessions": str(self.instance / "sessions"), "agent_runs": str(self.agent_runs),
                      "receiver": str(self.receiver), "webui_db": str(self.db)}
        self.transport = Counting(canary_watch.LocalTransport(self.paths))

    def watcher(self, transport=None, **kwargs) -> "canary_watch.Watcher":
        return canary_watch.Watcher(str(self.hits_dir), str(self.reports), str(self.runs), str(self.output_root),
                                    transport or self.transport, **kwargs)

    def write_journal(self, lines: list[str], mode: str = "a") -> None:
        with open(self.journal, mode) as f:
            f.writelines(lines)

    def hits(self) -> list[dict]:
        return HitsFile(str(self.hits_dir / f"{WORKSPACE}.jsonl")).read()

    def status(self) -> dict:
        return json.loads((self.hits_dir / f"{WORKSPACE}.status.json").read_text())

    def state(self) -> dict:
        return json.loads((self.hits_dir / f"{WORKSPACE}.state.json").read_text())

    def archive(self, journal_lines: list[str], index: bool = True, workspace: str = WORKSPACE) -> Path:
        """A run directory as run_archive writes it on stop, newer than hosts.yml (so: not running)."""
        run = self.runs / f"20261110T150000Z_{self.out.name}"
        (run / "agui" / "agui-journals").mkdir(parents=True)
        (run / "agui" / "agui-journals" / f"{SESSION}.jsonl").write_text("".join(journal_lines))
        shutil.copy(FIXTURES / "canaries.json", run / "canaries.json")
        report = json.loads((RUN / "report.json").read_text()) | {"workspace_id": workspace}
        (run / "report.json").write_text(json.dumps(report))
        if index:
            (run / "index.md").write_text("# run\n")
        later = time.time() + 100
        os.utime(run, (later, later))
        return run


def _ndjson(records: list[dict]) -> list[str]:
    return [json.dumps(r) + "\n" for r in records]


def test_poll_appends_hits_from_each_source(tmp_path):
    fake = Fake(tmp_path)
    fake.write_journal(JOURNAL)
    shutil.copy(RUN / "agui" / "agent-runs.jsonl", fake.agent_runs)
    request = json.loads((FIXTURES / "requests.jsonl").read_text())
    fake.receiver.write_text("".join(_ndjson([request, request | {"path": "/again"}])))
    _chat_db(fake.db, 1000)
    fake.watcher().tick(1000.0)
    hits = fake.hits()
    assert {h["source"] for h in hits} == {"agui-journal", "agent-runs", "openwebui-db", "receiver"}
    assert _keys(hits) == R1_KEYS and {h["source"] for h in hits if h["run"] == "r1"} == {"agui-journal"}
    assert [(h["source"], h["kind"]) for h in hits if h["run"] == "r9"] == [("agent-runs", "answer")]
    delivered = [h for h in hits if h["source"] == "receiver"]
    assert [h["kind"] for h in delivered] == ["delivered"]  # one per canary per generation, not per request
    assert delivered[0]["at"] == delivered[0]["detected"]  # the receiver has no time: when it was read
    assert [(h["session"]["id"], h["run"], h["kind"]) for h in hits if h["source"] == "openwebui-db"] == [
        ("owc1", "a1", "touched")]
    assert all(h["session"]["title"] == "Find the flag" for h in hits if h["source"] == "agui-journal")
    assert [h["id"] for h in hits] == list(range(1, len(hits) + 1))
    assert {k: hits[0][k] for k in META} == META
    status = fake.status()
    assert status["state"] == "running" and status["note"] is None
    assert status["last_poll"] == status["since"] == "1970-01-01T00:16:40Z"
    assert sum(status["hits"].values()) == len(hits) and status["hits"]["delivered"] == 1
    state = fake.state()
    assert state["offsets"]["journals"][SESSION] == fake.journal.stat().st_size
    assert state["offsets"]["agent_runs"] == fake.agent_runs.stat().st_size
    assert state["offsets"]["openwebui"] == 1000
    assert state["run_starts"] == {}  # every run read has ended
    # Nothing new: the next poll appends nothing, a re-saved chat included.
    fake.watcher().tick(1003.0)
    assert len(fake.hits()) == len(hits)


def test_split_token_across_polls(tmp_path):
    fake = Fake(tmp_path)
    first_args = _index("TOOL_CALL_ARGS", "call1")
    watcher = fake.watcher()
    fake.write_journal(JOURNAL[:first_args + 1])  # the first piece of "FCANA" + "RY-TEST01"
    watcher.tick(1000.0)
    assert [h["place"] for h in fake.hits()] == ["prompt"]
    assert fake.state()["run_starts"][SESSION] == len("".join(JOURNAL[:2]).encode())
    fake.write_journal(JOURNAL[first_args + 1:])
    watcher.tick(1001.0)  # not due yet: 3 s
    assert len(fake.transport.calls) == 1
    watcher.tick(1003.0)
    assert _keys(fake.hits()) == R1_KEYS
    assert [h for h in fake.hits() if (h["tool"] or {}).get("call_id") == "call1"][0]["kind"] == "args"


def test_restart_mid_run_no_loss_no_repeat(tmp_path):
    fake = Fake(tmp_path)
    first_args = _index("TOOL_CALL_ARGS", "call1")
    fake.write_journal(JOURNAL[:first_args + 1])
    fake.watcher().tick(1000.0)
    assert len(fake.hits()) == 1
    fake.write_journal(JOURNAL[first_args + 1:])
    restarted = fake.watcher()  # a new process: no reader in memory, only the state file
    restarted.tick(1000.5)
    assert _keys(fake.hits()) == R1_KEYS  # the split call1 found, the prompt not repeated
    assert all(h["session"]["title"] == "Find the flag" for h in fake.hits())  # the title kept over the restart
    run_start = len("".join(JOURNAL[:2]).encode())
    assert fake.transport.calls[-1]["journals"][SESSION] == run_start
    assert fake.state()["run_starts"] == {}


def test_new_generation_resets_offsets(tmp_path):
    fake = Fake(tmp_path)
    fake.write_journal(JOURNAL)
    _chat_db(fake.db, 1000)
    watcher = fake.watcher()
    watcher.tick(1000.0)
    first = fake.hits()
    generation = fake.state()["generation"]
    assert {h["source"] for h in first} == {"agui-journal", "openwebui-db"}
    # A rebuild: hosts.yml rewritten, the journal truncated and written again (the same length, so the old
    # offset would read nothing), Open WebUI's database made anew with an older updated_at.
    hosts = fake.out / "hosts.yml"
    hosts.write_text(hosts.read_text())
    later = time.time() + 50
    os.utime(hosts, (later, later))
    fake.write_journal(JOURNAL, mode="w")
    _chat_db(fake.db, 500)
    watcher.tick(1000.0 + canary_watch.DISCOVER_EVERY)  # the rebuild is seen at the next discovery
    assert fake.state()["generation"] != generation
    hits = fake.hits()
    assert len(hits) == 2 * len(first)
    assert _keys(hits[len(first):]) == R1_KEYS
    assert [h["source"] for h in hits[len(first):] if h["frontend"] == "openwebui"] == ["openwebui-db"]
    assert fake.state()["offsets"]["openwebui"] == 500


def test_restart_after_rebuild_keeps_new_generation_hits(tmp_path):
    """A restart rebuilds the dedup keys from the hits file only for the current generation's hits: a
    receiver hit (keyed by workspace, generation and canary only) from before a rebuild does not block the
    rebuilt instance's first delivered hit of the same canary."""
    fake = Fake(tmp_path)
    request = (FIXTURES / "requests.jsonl").read_text()
    fake.receiver.write_text(request)
    fake.watcher().tick(1000.0)
    assert [h["kind"] for h in fake.hits()] == ["delivered"]
    hosts = fake.out / "hosts.yml"  # the rebuild: a new generation, the receiver's log empty again
    hosts.write_text(hosts.read_text())
    later = time.time() + 50
    os.utime(hosts, (later, later))
    fake.receiver.write_text("")
    fake.watcher().tick(1003.0)
    assert fake.state()["generation_start"] == 1
    restarted = fake.watcher()
    fake.receiver.write_text(request)
    restarted.tick(1006.0)
    assert [h["kind"] for h in fake.hits()] == ["delivered", "delivered"]


def _reply(files: dict | None = None, openwebui: dict | None = None) -> dict:
    return {"files": files or {}, "openwebui": openwebui, "missing": [], "errors": []}


def _file(lines: list[str]) -> dict:
    starts, at = [], 0
    for line in lines:
        starts.append(at)
        at += len(line.encode()) + 1
    return {"size": at, "start": 0, "end": at, "lines": lines, "line_starts": starts}


def test_reader_output_untrusted(tmp_path):
    fake = Fake(tmp_path)
    records = [{"run_id": f"x{n}", "thread_id": "t", "answer": "FCANARY-TEST01"} for n in range(300)]
    lines = ["not json", "{", "[1, 2", "\"FCANARY-TEST01\""] + [json.dumps(r) for r in records]
    transport = Counting(replies=[
        _reply({"agent_runs": _file(lines)}),
        {"files": [], "openwebui": None, "missing": [], "errors": []},  # not the expected shape
        _reply({"agent_runs": _file(["{}"]) | {"line_starts": [0, 5]}}),  # starts not one per line
        _reply(openwebui={"rows": [], "max": "1000"}),
    ])
    watcher = fake.watcher(transport)
    watcher.tick(1000.0)
    hits = fake.hits()
    assert len(hits) == 200 and {h["kind"] for h in hits} == {"answer"}
    assert fake.status()["state"] == "running"
    assert fake.state()["offsets"]["agent_runs"] == _file(lines)["end"]
    for n, now in enumerate((1003.0, 1063.0, 1123.0)):
        watcher.tick(now)
        assert len(transport.calls) == n + 2
        assert fake.status()["state"] == "unreachable"
    assert fake.state()["offsets"]["agent_runs"] == _file(lines)["end"]  # a failed poll moves nothing
    assert len(fake.hits()) == 200


def test_journal_not_a_session_id_skipped(tmp_path):
    """The chat app reads only <uuid>.jsonl as a journal (lib/export.ts): any other file is skipped, not a
    failed poll, and never becomes an offset key."""
    fake = Fake(tmp_path)
    good = _file(JOURNAL_LINES)
    transport = Counting(replies=[_reply({"journal:../../etc/passwd": _file(JOURNAL_LINES),
                                          f"journal:{SESSION}": good})])
    fake.watcher(transport).tick(1000.0)
    assert fake.status()["state"] == "running"
    assert _keys(fake.hits()) == R1_KEYS
    assert fake.state()["offsets"]["journals"] == {SESSION: good["end"]}


def test_failed_poll_backs_off(tmp_path):
    fake = Fake(tmp_path)
    transport = Counting(fail=True)
    watcher = fake.watcher(transport)
    watcher.tick(1000.0)
    status = fake.status()
    assert status["state"] == "unreachable" and status["since"] == "1970-01-01T00:16:40Z"
    assert status["last_poll"] is None
    for now in (1003.0, 1030.0, 1059.0):
        watcher.tick(now)
    assert len(transport.calls) == 1
    watcher.tick(1060.0)
    assert len(transport.calls) == 2
    assert fake.status()["since"] == "1970-01-01T00:16:40Z"  # still unreachable since the first failure
    transport.fail = False
    transport.inner = canary_watch.LocalTransport(fake.paths)
    watcher.tick(1120.0)
    assert len(transport.calls) == 3
    status = fake.status()
    assert status["state"] == "running" and status["last_poll"] == "1970-01-01T00:18:40Z"
    watcher.tick(1123.0)
    assert len(transport.calls) == 4  # back to every 3 s


def test_scan_waits_for_index_md(tmp_path):
    fake = Fake(tmp_path)
    watcher = fake.watcher()
    watcher.tick(1000.0)
    run = fake.archive(JOURNAL, index=False)
    watcher.tick(1003.0)
    assert fake.hits() == [] and fake.state()["archived"] == []
    assert fake.status()["state"] != "stopped"
    (run / "index.md").write_text("# run\n")
    watcher.tick(1004.0)
    assert _keys(fake.hits()) == R1_KEYS
    assert fake.state()["archived"] == [run.name]
    assert fake.status()["state"] == "stopped"


def test_on_stop_scans_archive_once(tmp_path):
    fake = Fake(tmp_path)
    watcher = fake.watcher()
    end_call1 = _index("TOOL_CALL_END", "call1")
    fake.write_journal(JOURNAL[:end_call1 + 1])
    watcher.tick(1000.0)
    live = fake.hits()
    assert sorted(h["place"] for h in live) == ["prompt", "tool_args"]
    fake.archive(JOURNAL)  # the stop: the lines past the last poll are only in the archive now
    fake.write_journal(JOURNAL[end_call1 + 1:])
    polls = len(fake.transport.calls)
    watcher.tick(1003.0)
    assert len(fake.transport.calls) == polls  # stopped: not polled
    hits = fake.hits()
    assert _keys(hits) == R1_KEYS  # the later hits, and the earlier ones not again
    assert hits[:len(live)] == live
    assert fake.status()["state"] == "stopped"
    for now in (1006.0, 1009.0):
        watcher.tick(now)
    fake.watcher().tick(1012.0)  # a restart scans it no more either
    assert fake.hits() == hits


def test_archive_of_another_workspace_not_scanned(tmp_path):
    fake = Fake(tmp_path)
    fake.archive(JOURNAL, workspace="99999999-9999-9999-9999-999999999999")
    fake.watcher().tick(1000.0)
    assert fake.hits() == []
    assert fake.state()["archived"] == []


def test_encrypted_never_polled(tmp_path):
    fake = Fake(tmp_path, encrypted=True)
    fake.write_journal(JOURNAL)
    fake.watcher().tick(1000.0)
    assert fake.transport.calls == []
    status = fake.status()
    assert status["state"] == "encrypted" and status["note"] == "canary record is encrypted"


def test_hits_file_full_is_capped(tmp_path):
    fake = Fake(tmp_path)
    fake.write_journal(JOURNAL)
    watcher = fake.watcher(hits_max=1500)
    watcher.tick(1000.0)
    status = fake.status()
    assert status["state"] == "capped" and status["note"] == "hits file full"
    assert 0 < os.path.getsize(fake.hits_dir / f"{WORKSPACE}.jsonl") <= 1500
    watcher.tick(1003.0)
    assert len(fake.transport.calls) == 1  # nothing more is written, so nothing more is read


def test_logs_carry_no_token(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    fake = Fake(tmp_path)
    fake.write_journal(JOURNAL[:5])
    shutil.copy(RUN / "agui" / "agent-runs.jsonl", fake.agent_runs)
    shutil.copy(FIXTURES / "requests.jsonl", fake.receiver)
    _chat_db(fake.db, 1000)
    watcher = fake.watcher()
    watcher.tick(1000.0)
    fake.archive(JOURNAL)
    watcher.tick(1003.0)
    (tmp_path / "other").mkdir()
    bad = Fake(tmp_path / "other")
    bad.watcher(Counting(replies=[_reply({"agent_runs": {"lines": ["FCANARY-TEST01"]}}) | {
        "errors": ["FCANARY-TEST01: x"]}])).tick(1000.0)
    assert fake.hits() and caplog.records
    assert WORKSPACE in caplog.text
    for token in TOKENS:
        assert token not in caplog.text
    assert "sensitive/" not in caplog.text and "CANARY" not in caplog.text


def test_state_file_modes(tmp_path):
    fake = Fake(tmp_path)
    fake.write_journal(JOURNAL)
    old = os.umask(0o022)
    try:
        fake.watcher().tick(1000.0)
    finally:
        os.umask(old)
    modes = {p.name.removeprefix(WORKSPACE): stat.S_IMODE(p.stat().st_mode) for p in fake.hits_dir.iterdir()}
    assert modes == {".state.json": 0o600, ".status.json": 0o640, ".jsonl": 0o640}


def test_unreadable_source_skipped(tmp_path, caplog):
    """A source the scan cannot read (here a directory where a file should be: an OSError even as root) is
    skipped and logged with the workspace id; the rest of the run is still scanned."""
    caplog.set_level(logging.WARNING)
    run = tmp_path / "run"
    shutil.copytree(RUN, run)
    (run / "agui" / "agent-runs.jsonl").unlink()
    (run / "agui" / "agent-runs.jsonl").mkdir()
    (run / "agui" / "agui-journals" / "bbbbbbbb-1111-4222-8333-444444444444.jsonl").mkdir()
    hits, count = scan(tmp_path, run=run)
    assert count > 0 and _keys(hits.read()) == R1_KEYS
    assert WORKSPACE in caplog.text and "agent-runs.jsonl" in caplog.text
    assert "cannot read a journal" in caplog.text and "bbbbbbbb" not in caplog.text  # never a journal's name


def test_archive_journal_not_a_session_id_skipped(tmp_path):
    """The archive scan reads only <session id>.jsonl as a journal, as polling does: another name is skipped."""
    run = tmp_path / "run"
    shutil.copytree(RUN, run)
    journals = run / "agui" / "agui-journals"
    (journals / f"{SESSION}.jsonl").rename(journals / "notes.jsonl")
    hits, _ = scan(tmp_path, run=run)
    records = hits.read()
    assert records and not [h for h in records if h["source"] == "agui-journal"]
    assert {h["source"] for h in records if h["run"] == "r1"} == {"agent-runs"}  # the run log's copy only


# Lines that parse but whose fields have the wrong type, or that nest too deep to parse: each once made the
# whole poll (or the archive scan) raise, so one such line blinded the workspace for its whole life.
POISON_RUNS = ['{"run_id": "x", "thread_id": [1], "input": "hi"}', '{"run_id": "y", "tool_calls": 5}',
               "[" * 200000]
POISON_JOURNAL = ['{"type": "run_start", "run_id": [1]}', "[" * 200000]
GOOD_RUN = {"run_id": "g1", "thread_id": "t", "answer": "FCANARY-TEST01"}


def test_poisoned_lines_never_blind_polling(tmp_path):
    fake = Fake(tmp_path)
    fake.agent_runs.write_text("".join(line + "\n" for line in POISON_RUNS) + json.dumps(GOOD_RUN) + "\n")
    fake.write_journal([line + "\n" for line in POISON_JOURNAL] + JOURNAL[:5])
    watcher = fake.watcher()
    watcher.tick(1000.0)
    assert fake.status()["state"] == "running"
    offsets = fake.state()["offsets"]
    assert offsets["agent_runs"] == fake.agent_runs.stat().st_size
    assert offsets["journals"][SESSION] == fake.journal.stat().st_size
    assert [h["run"] for h in fake.hits() if h["source"] == "agent-runs"] == ["g1"]
    # Later valid lines still come in on the next poll, after the poisoned ones.
    with open(fake.agent_runs, "a") as f:
        f.write(json.dumps(GOOD_RUN | {"run_id": "g2"}) + "\n")
    fake.write_journal(JOURNAL[5:])
    watcher.tick(1003.0)
    assert fake.status()["state"] == "running"
    hits = fake.hits()
    assert [h["run"] for h in hits if h["source"] == "agent-runs"] == ["g1", "g2"]
    assert _keys(hits) == R1_KEYS
    assert fake.state()["offsets"]["agent_runs"] == fake.agent_runs.stat().st_size


def test_poisoned_archive_scanned_once(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    fake = Fake(tmp_path)
    watcher = fake.watcher()
    watcher.tick(1000.0)
    run = fake.archive([line + "\n" for line in POISON_JOURNAL] + JOURNAL)
    (run / "agui" / "agent-runs.jsonl").write_text(
        "".join(line + "\n" for line in POISON_RUNS) + json.dumps(GOOD_RUN) + "\n")
    for now in (1003.0, 1004.0, 1005.0):
        watcher.tick(now)
    assert fake.state()["archived"] == [run.name]
    hits = fake.hits()
    assert _keys(hits) == R1_KEYS
    assert [h["run"] for h in hits if h["source"] == "agent-runs"] == ["g1"]
    assert fake.status()["state"] == "stopped"
    assert sum("from archived run" in r.getMessage() for r in caplog.records) == 1


def test_archive_scan_that_raises_is_marked_scanned(tmp_path, caplog, monkeypatch):
    """Whatever still makes a scan raise marks the run scanned all the same: logged once, by the workspace
    id and the exception class only, never rescanned every tick."""
    caplog.set_level(logging.INFO)
    fake = Fake(tmp_path)
    watcher = fake.watcher()
    watcher.tick(1000.0)
    run = fake.archive(JOURNAL)
    calls = []

    def boom(*args, **kwargs):
        calls.append(args)
        raise TypeError("FCANARY-TEST01")

    monkeypatch.setattr(canary_watch, "scan_archive", boom)
    for now in (1003.0, 1004.0, 1005.0):
        watcher.tick(now)
    assert len(calls) == 1
    assert fake.state()["archived"] == [run.name]
    failures = [r.getMessage() for r in caplog.records if "scan failed" in r.getMessage()]
    assert failures == [f"{WORKSPACE}: archived run scan failed (TypeError)"]
    assert "CANARY" not in caplog.text


def test_discovery_throttled_stop_still_seen(tmp_path, monkeypatch):
    """discover (sidecars, hosts.yml, canaries.json over NFS) runs at most every DISCOVER_EVERY seconds, and
    again when the clock goes back; a stop is still seen on the tick its run directory appears."""
    fake = Fake(tmp_path)
    fake.write_journal(JOURNAL[:5])
    real, runs = canary_watch.discover, []
    monkeypatch.setattr(canary_watch, "discover", lambda *a: runs.append(a) or real(*a))
    watcher = fake.watcher()
    watcher.tick(1000.0)
    watcher.tick(1003.0)
    assert len(runs) == 1 and len(fake.transport.calls) == 2
    fake.archive(JOURNAL)
    watcher.tick(1006.0)
    assert len(runs) == 1
    assert fake.status()["state"] == "stopped" and len(fake.transport.calls) == 2
    assert _keys(fake.hits()) == R1_KEYS
    watcher.tick(1000.0 + canary_watch.DISCOVER_EVERY)
    assert len(runs) == 2 and fake.status()["state"] == "stopped"
    watcher.tick(900.0)  # the clock went back: discover again rather than wait
    assert len(runs) == 3


# --- the transports ---

def _remote_ws(tmp_path: Path, target: str = "10.0.0.5") -> "canary_watch.Workspace":
    out = tmp_path / "out"
    out.mkdir()
    (out / "hosts.yml").write_text(f"ssh_user: ubuntu\nprovision: existing\nssh_target: {target}\n"
                                   "ssh_key: /keys/id\nssh_args: -p 2222\n")
    return canary_watch.Workspace(id=WORKSPACE, owner=None, instance="x", output_dir=str(out), api_host=None,
                                  ssh=canary_watch.Ssh(None, None, None), generation="g", running=True,
                                  encrypted=False)


def test_offsets_quoted_and_checked(tmp_path):
    seen = []

    def runner(argv, data, timeout, cap):
        seen.append((argv, data, timeout, cap))
        return json.dumps(_reply()).encode()

    transport = canary_watch.SshTransport(runner=runner)
    ws = _remote_ws(tmp_path)
    offsets = {"journals": {SESSION: 12}, "agent_runs": 3, "receiver": 0, "openwebui": 1000.5}
    assert transport.read(ws, offsets) == _reply()
    [(argv, data, timeout, cap)] = seen
    assert argv[:5] == ["ssh", "-i", "/keys/id", "-p", "2222"]
    assert argv[5:13] == ["-o", "ControlMaster=auto", "-o", "ControlPath=~/.ssh/cm-%C", "-o", "ControlPersist=60",
                          "-o", "BatchMode=yes"]
    assert argv[13] == "ubuntu@10.0.0.5" and len(argv) == 15
    assert shlex.split(argv[14])[:4] == ["sudo", "-n", "python3", "-"]
    assert json.loads(shlex.split(argv[14])[4]) == offsets
    assert data == (HERE.parent / "canary_reader.py").read_bytes()
    assert timeout == 30 and cap == 32 << 20
    for bad in ({"journals": {"x'; rm -rf /; '": 0}}, {"journals": {SESSION: "1; rm"}}, {"journals": {SESSION: True}},
                {"journals": {SESSION: -1}}, {"journals": []}, {"agent_runs": "0"}, {"receiver": 1.5},
                {"openwebui": float("nan")}, {"openwebui": True}, {"other": 1}):
        with pytest.raises(ValueError):
            transport.read(ws, bad)
    assert len(seen) == 1


def test_local_target_runs_sudo_without_ssh(tmp_path):
    seen = []
    transport = canary_watch.SshTransport(runner=lambda argv, *rest: seen.append(argv) or b'{"files": {}}')
    transport.read(_remote_ws(tmp_path, target="localhost"), {"agent_runs": 4})
    assert seen == [["sudo", "-n", "python3", "-", json.dumps({"agent_runs": 4}, separators=(",", ":"))]]


def test_run_capped(tmp_path):
    echo = [sys.executable, "-c", "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"]
    big = b"x" * 300_000  # past a pipe's buffer, both ways
    assert canary_watch.run_capped(echo, big, 30, 1 << 20) == big
    with pytest.raises(canary_watch.PollError, match="larger than"):
        canary_watch.run_capped(echo, big, 30, 1000)
    with pytest.raises(canary_watch.PollError, match="exit status 3"):
        canary_watch.run_capped([sys.executable, "-c", "raise SystemExit(3)"], b"", 30, 1000)
    with pytest.raises(canary_watch.PollError, match="timed out"):
        canary_watch.run_capped([sys.executable, "-c", "import time; time.sleep(5)"], b"", 0.5, 1000)


# --- --once: a hand check, no sidecar, no state or status file (ruling 5) ---

def test_once_polls_and_appends_without_touching_the_hits_root(tmp_path, capsys):
    fake = Fake(tmp_path)
    fake.write_journal(JOURNAL)
    out = tmp_path / "hits.jsonl"
    rc = canary_watch.once(str(fake.out), str(out), transport=canary_watch.LocalTransport(fake.paths))
    assert rc == 0
    hits = HitsFile(str(out)).read()
    assert _keys(hits) == R1_KEYS
    assert {k: hits[0][k] for k in ("workspace", "owner")} == {"workspace": "once", "owner": None}
    # Nothing is written anywhere near a hits root: only --out exists.
    assert not fake.hits_dir.exists()
    assert sorted(p.name for p in tmp_path.iterdir() if p.is_file()) == ["hits.jsonl"]
    captured = capsys.readouterr()
    for token in TOKENS:
        assert token not in captured.out and token not in captured.err
    assert "sources" in captured.out and "missing" in captured.out and "errors" in captured.out
    assert "hits by kind" in captured.out


def test_once_is_idempotent_on_rerun(tmp_path):
    """Run twice into the same --out: the second run's dedup (by this instance's generation) adds
    nothing new, since the instance (and so its canary record and hosts.yml) has not changed."""
    fake = Fake(tmp_path)
    fake.write_journal(JOURNAL)
    out = tmp_path / "hits.jsonl"
    transport = canary_watch.LocalTransport(fake.paths)
    canary_watch.once(str(fake.out), str(out), transport=transport)
    first = HitsFile(str(out)).read()
    canary_watch.once(str(fake.out), str(out), transport=transport)
    assert HitsFile(str(out)).read() == first


def test_once_encrypted_record_not_polled(tmp_path, capsys):
    fake = Fake(tmp_path, encrypted=True)
    out = tmp_path / "hits.jsonl"
    rc = canary_watch.once(str(fake.out), str(out), transport=canary_watch.LocalTransport(fake.paths))
    assert rc == 1
    assert not out.exists()
    assert "encrypted" in capsys.readouterr().out


def test_once_prints_only_known_names(tmp_path, capsys):
    """--once prints of the reply only known source names, journal keys that are session ids and errors of
    the reader's own form; anything else the participant controls is counted, never printed."""
    fake = Fake(tmp_path)
    reply = _reply({f"journal:{SESSION}": _file(JOURNAL_LINES), "journal:FCANARY-TEST01": _file([])})
    reply["missing"] = ["receiver", "FCANARY-TEST01"]
    reply["errors"] = ["openwebui: OperationalError", f"journal:{SESSION}: PermissionError",
                       "agent_runs: FCANARY-TEST01 leaked", "FCANARY-TEST01: x", 5]
    rc = canary_watch.once(str(fake.out), str(tmp_path / "hits.jsonl"), transport=Counting(replies=[reply]))
    assert rc == 0
    out = capsys.readouterr().out
    for token in TOKENS:
        assert token not in out
    assert "CANARY" not in out
    assert f"sources ['journal:{SESSION}', '1 other']" in out
    assert "missing ['receiver', '1 other']" in out
    assert (f"errors ['journal:{SESSION}: PermissionError', 'openwebui: OperationalError', '3 other']"
            in out)


def test_once_no_record_fails_without_a_token(tmp_path, capsys):
    output_root = tmp_path / "output"
    directory = _output_dir(output_root, "ws1", no_record=True)
    out = tmp_path / "hits.jsonl"
    rc = canary_watch.once(str(directory), str(out))
    assert rc == 1
    assert not out.exists()
    assert "no usable canary record" in capsys.readouterr().err


def test_once_cli_needs_output_dir_and_out(tmp_path):
    with pytest.raises(SystemExit):
        canary_watch.main(["--once"])
    with pytest.raises(SystemExit):
        canary_watch.main(["--once", "--output-dir", str(tmp_path)])
    with pytest.raises(SystemExit):
        canary_watch.main(["--once", "--archive", str(tmp_path), "--out", str(tmp_path / "h.jsonl")])


def test_nothing_on_the_instance_changes():
    """decision 1: no file under platform/instance/ or platform/ansible/roles/ is touched by this
    branch. Skipped outside a git checkout, or when origin/main is not available (as CI and a
    fresh upstream clone may lack it)."""
    repo = Path(__file__).resolve().parents[3]
    if not (repo / ".git").exists():
        pytest.skip("not a git checkout")
    check = subprocess.run(["git", "rev-parse", "--verify", "origin/main"], cwd=repo,
                           capture_output=True, text=True)
    if check.returncode != 0:
        pytest.skip("origin/main is not available")
    diff = subprocess.run(["git", "diff", "--name-only", "origin/main...HEAD"], cwd=repo,
                          capture_output=True, text=True, check=True)
    changed = [line for line in diff.stdout.splitlines() if line]
    touched = [line for line in changed if line.startswith(("platform/instance/", "platform/ansible/roles/"))]
    assert touched == []


# --- the local review round (#78): write failures, a stop missed across a rebuild, a rebuild between
# discoveries, a stop whose archive never finishes ---

def _failing_append(monkeypatch, after: int) -> dict:
    """HitsFile.append raises OSError once `after` hits have been written, until `box["fail"]` is False."""
    real, box = canary_hits.HitsFile.append, {"fail": True, "written": 0}

    def append(self, hit):
        if box["fail"] and box["written"] >= after:
            raise OSError(28, "No space left on device")
        box["written"] += 1
        return real(self, hit)

    monkeypatch.setattr(canary_hits.HitsFile, "append", append)
    return box


def test_hits_write_failure_fails_the_poll(tmp_path, monkeypatch, caplog):
    """An OSError writing the hits file is a failed poll, not a dropped line: the offsets stay, and the hits
    come out once (no more, no fewer) when the write works again."""
    caplog.set_level(logging.INFO)
    fake = Fake(tmp_path)
    fake.write_journal(JOURNAL)
    box = _failing_append(monkeypatch, after=2)
    watcher = fake.watcher()
    watcher.tick(1000.0)
    assert len(fake.hits()) == 2
    assert fake.status()["state"] == "unreachable"
    assert fake.state()["offsets"]["journals"] == {}  # not advanced past the lines whose hits were lost
    assert "poll failed (OSError)" in caplog.text and "dropped" not in caplog.text
    box["fail"] = False
    watcher.tick(1000.0 + canary_watch.BACKOFF)
    assert _keys(fake.hits()) == R1_KEYS
    assert fake.status()["state"] == "running"
    assert fake.state()["offsets"]["journals"][SESSION] == fake.journal.stat().st_size


def test_archive_write_failure_is_retried(tmp_path, monkeypatch, caplog):
    """An OSError writing an archived run's hits leaves the run unscanned (the workspace not yet stopped),
    tried again after BACKOFF; its hits then come out once."""
    caplog.set_level(logging.INFO)
    fake = Fake(tmp_path)
    watcher = fake.watcher()
    watcher.tick(1000.0)
    run = fake.archive(JOURNAL)
    box = _failing_append(monkeypatch, after=1)
    watcher.tick(1003.0)
    assert fake.state()["archived"] == [] and len(fake.hits()) == 1
    assert fake.status()["state"] != "stopped"
    assert f"{WORKSPACE}: archived run scan failed (OSError), again in 60 s" in caplog.text
    box["fail"] = False
    watcher.tick(1004.0)  # not yet: BACKOFF
    assert fake.state()["archived"] == []
    watcher.tick(1003.0 + canary_watch.BACKOFF)
    assert fake.state()["archived"] == [run.name]
    assert _keys(fake.hits()) == R1_KEYS
    assert fake.status()["state"] == "stopped"


def _rebuild(fake: Fake, later: float) -> None:
    hosts = fake.out / "hosts.yml"
    hosts.write_text(hosts.read_text())
    os.utime(hosts, (later, later))


def test_stop_and_rebuild_while_down_scanned_under_the_old_generation(tmp_path):
    """The watcher down across a stop and a rebuild: the stop's run directory is scanned with the last
    generation's keys before they are cleared, so what polling wrote is not written again."""
    fake = Fake(tmp_path)
    end_call1 = _index("TOOL_CALL_END", "call1")
    fake.write_journal(JOURNAL[:end_call1 + 1])
    fake.watcher().tick(1000.0)
    live = fake.hits()
    assert len(live) == 2
    generation = fake.state()["generation"]
    run = fake.archive(JOURNAL)  # the stop, then the rebuild: hosts.yml newer than the run directory
    _rebuild(fake, time.time() + 200)
    fake.write_journal([], mode="w")
    fake.watcher().tick(1003.0)  # the restart
    hits = fake.hits()
    assert _keys(hits) == R1_KEYS and hits[:2] == live
    state = fake.state()
    assert state["archived"] == [run.name]
    assert state["generation"] != generation and state["generation_start"] == len(R1_KEYS)
    assert fake.status()["state"] == "running"


def test_rebuild_between_discoveries_not_polled_under_the_stale_generation(tmp_path):
    """hosts.yml rewritten while discovery is throttled: that workspace is not polled under its stale
    generation; the next tick discovers again, and the rebuilt instance's hits are written once."""
    fake = Fake(tmp_path)
    watcher = fake.watcher()
    watcher.tick(1000.0)
    assert fake.hits() == []
    _rebuild(fake, time.time() + 50)
    fake.write_journal(JOURNAL)
    watcher.tick(1003.0)
    assert len(fake.transport.calls) == 1  # not polled: its generation is stale
    watcher.tick(1004.0)  # discovered again
    assert len(fake.transport.calls) == 2
    assert _keys(fake.hits()) == R1_KEYS
    for now in (1007.0, 1010.0, 1004.0 + canary_watch.DISCOVER_EVERY):
        watcher.tick(now)
    assert len(fake.hits()) == len(R1_KEYS)


def test_archive_without_index_md_scanned_after_a_while(tmp_path):
    """A stop whose archive never writes index.md: ARCHIVE_WAIT seconds past its run directory's mtime it is
    scanned as it is, and the workspace is stopped, noted "archive incomplete" (kept over a restart)."""
    fake = Fake(tmp_path)
    watcher = fake.watcher()
    watcher.tick(1000.0)
    run = fake.archive(JOURNAL, index=False)
    mtime = run.stat().st_mtime
    watcher.tick(mtime + 10)
    assert fake.state()["archived"] == [] and fake.status()["state"] == "running"
    watcher.tick(mtime + canary_watch.ARCHIVE_WAIT + 1)
    assert fake.state()["archived"] == [run.name]
    assert _keys(fake.hits()) == R1_KEYS
    status = fake.status()
    assert status["state"] == "stopped" and status["note"] == "archive incomplete"
    fake.watcher().tick(mtime + canary_watch.ARCHIVE_WAIT + 5)
    assert fake.status()["note"] == "archive incomplete" and len(fake.hits()) == len(R1_KEYS)
