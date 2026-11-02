"""write_agui_run.py renders an AG-UI sessions bundle like an OpenWebUI run; write_run.py's fence()."""
import filecmp
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

PLATFORM = Path(__file__).resolve().parents[2]
FILES = PLATFORM / "ansible" / "roles" / "run_archive" / "files"
AGUI = FILES / "write_agui_run.py"
OWUI = FILES / "write_run.py"

ACTIVE = "6f1c0d2e-1a2b-4c3d-8e4f-0a1b2c3d4e5f"
HIDDEN = "7a2b3c4d-5e6f-4a7b-9c8d-1e2f3a4b5c6d"
DELETED = "8b3c4d5e-6f7a-4b8c-ad9e-2f3a4b5c6d7e"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def record(id_, title, created, *, tags=(), hidden=False, deleted_at=None, messages=None, runs=None):
    return {
        "version": 1, "id": id_, "title": title, "title_source": "auto", "tags": list(tags),
        "pinned": bool(tags), "hidden": hidden, "created_at": created, "updated_at": created,
        "deleted_at": deleted_at, "messages": messages or [],
        "runs": runs if runs is not None else [
            {"run_id": "r-" + id_[:4], "started_at": created, "ended_at": created, "status": "completed"}],
    }


def tool_turn(n, result):
    return [
        {"id": f"u{n}", "role": "user", "content": f"turn {n}"},
        {"id": f"a{n}", "role": "assistant", "content": "",
         "toolCalls": [{"id": f"call-{n}", "type": "function",
                        "function": {"name": "run_command", "arguments": json.dumps({"command": f"echo {n}"})}}]},
        {"id": f"t{n}", "role": "tool", "toolCallId": f"call-{n}", "content": result},
        {"id": f"b{n}", "role": "assistant", "content": f"Turn {n}: the command ran."},
    ]


@pytest.fixture
def bundle(tmp_path):
    b = tmp_path / "bundle"
    (b / "sessions").mkdir(parents=True)
    sessions = [
        record(ACTIVE, "List the home directory", "2026-10-29T10:02:11.000Z", tags=["exfil", "dns"],
               messages=tool_turn(1, "fake output\n```\nthree\n````\nfour\n``````\nsix")),
        record(HIDDEN, "Read <img src=x onerror=alert(1)>", "2026-10-29T10:05:00.000Z", hidden=True,
               messages=tool_turn(2, "ok")),
        record(DELETED, "Try | the [pipe]", "2026-10-29T10:09:30.000Z", deleted_at="2026-10-29T10:20:00.000Z",
               messages=tool_turn(3, "gone"),
               runs=[{"run_id": "r1", "started_at": "x", "ended_at": "y", "status": "cancelled"}]),
    ]
    for s in sessions:
        (b / "sessions" / f"{s['id']}.json").write_text(json.dumps(s, indent=1))
    (b / "sessions" / f"{ACTIVE}.json.tmp-abc123").write_text("{half")
    (b / "agent-runs.jsonl").write_text('{"run_id": "r-6f1c"}\n{"run_id": "r-7a2b"}\n')
    return b


def run(*args):
    return subprocess.run([sys.executable, str(AGUI), *map(str, args)], capture_output=True, text=True, check=True)


def test_agui_run_index_lists_every_session_with_its_state(bundle, tmp_path):
    out = tmp_path / "run"
    proc = run(bundle, out)
    assert "3 sessions (1 hidden, 1 deleted), run log, 0 unreadable" in proc.stdout
    index = (out / "index.md").read_text()
    assert "| 01 | [List the home directory](chats/01-list-the-home-directory.md) | exfil, dns " \
           "| 2026-10-29 10:02 UTC | 1 | active |" in index
    assert "| 02 | [Read <img src=x onerror=alert(1)>](chats/02-read-img-src-x-onerror-alert-1.md) | - " \
           "| 2026-10-29 10:05 UTC | 1 | hidden |" in index
    assert r"| 03 | [Try \| the \[pipe\]](chats/03-try-the-pipe.md) | - | 2026-10-29 10:09 UTC | 1 " \
           "| deleted 2026-10-29 10:20 UTC |" in index
    assert "The AG-UI frontend has no run report." in index
    assert "[agent-runs.jsonl](agent-runs.jsonl), 2 runs" in index


def test_agui_run_keeps_raw_files_untouched(bundle, tmp_path):
    out = tmp_path / "run"
    run(bundle, out)
    for src in (bundle / "sessions").iterdir():
        assert filecmp.cmp(src, out / "agui-sessions" / src.name, shallow=False)
    assert filecmp.cmp(bundle / "agent-runs.jsonl", out / "agent-runs.jsonl", shallow=False)
    assert filecmp.cmp(bundle / "sessions" / f"{ACTIVE}.json", out / "chats" / "01-list-the-home-directory.json",
                       shallow=False)
    assert sorted(p.name for p in (out / "chats").iterdir()) == [
        "01-list-the-home-directory.json", "01-list-the-home-directory.md",
        "02-read-img-src-x-onerror-alert-1.json", "02-read-img-src-x-onerror-alert-1.md",
        "03-try-the-pipe.json", "03-try-the-pipe.md"]


def test_agui_run_deleted_session_opens_with_the_marker(bundle, tmp_path):
    out = tmp_path / "run"
    run(bundle, out)
    md = (out / "chats" / "03-try-the-pipe.md").read_text()
    assert md.startswith("Deleted by the participant at 2026-10-29 10:20 UTC.\n\n# Try | the [pipe]\n")
    assert "- Runs: 1 (cancelled 1)" in md
    assert "Deleted by" not in (out / "chats" / "01-list-the-home-directory.md").read_text()


def test_agui_run_tool_calls_are_fenced_longer_than_any_backtick_run(bundle, tmp_path):
    out = tmp_path / "run"
    run(bundle, out)
    md = (out / "chats" / "01-list-the-home-directory.md").read_text()
    assert "**Tool call `run_command`**\n\n```json\n{\n  \"command\": \"echo 1\"\n}\n```" in md
    assert "<details><summary>Tool result</summary>\n\n```````\nfake output\n```\nthree\n````\nfour\n" \
           "``````\nsix\n```````\n\n</details>" in md
    assert "## user\n\nturn 1\n" in md and "## assistant\n\nTurn 1: the command ran.\n" in md


def test_agui_run_numeric_title_does_not_crash(tmp_path):
    b = tmp_path / "bundle"
    (b / "sessions").mkdir(parents=True)
    rec = record(ACTIVE, 42, "2026-10-29T10:02:11.000Z")
    (b / "sessions" / f"{ACTIVE}.json").write_text(json.dumps(rec, indent=1))
    out = tmp_path / "run"
    proc = run(b, out)
    assert "1 sessions" in proc.stdout
    assert (out / "chats" / "01-42.md").exists()
    assert "[42](chats/01-42.md)" in (out / "index.md").read_text()


def test_agui_run_empty_bundle_says_so(tmp_path):
    b = tmp_path / "bundle"
    (b / "sessions").mkdir(parents=True)
    out = tmp_path / "run"
    proc = run(b, out)
    index = (out / "index.md").read_text()
    assert "No session was recorded." in index
    assert "Agent run log: none (no run reached the agent)" in index
    assert not (out / "agent-runs.jsonl").exists()
    assert not (out / "chats").exists()
    assert "0 sessions" in proc.stdout


def test_agui_run_rerender_in_place_is_identical(bundle, tmp_path):
    out = tmp_path / "run"
    run(bundle, out)
    before = {p.relative_to(out): p.read_bytes() for p in out.rglob("*") if p.is_file()}
    run(out, out)
    after = {p.relative_to(out): p.read_bytes() for p in out.rglob("*") if p.is_file()}
    assert after == before


def test_agui_run_unreadable_file_is_listed_not_fatal(bundle, tmp_path):
    (bundle / "sessions" / "9c4d5e6f-7a8b-4c9d-be0f-3a4b5c6d7e8f.json").write_text("{not json")
    out = tmp_path / "run"
    proc = run(bundle, out)
    assert "1 unreadable" in proc.stdout
    assert "Unreadable session files (kept in agui-sessions/): `9c4d5e6f-7a8b-4c9d-be0f-3a4b5c6d7e8f.json`" \
           in (out / "index.md").read_text()


def test_agui_run_refuses_a_directory_without_sessions(tmp_path):
    proc = subprocess.run([sys.executable, str(AGUI), str(tmp_path), str(tmp_path / "run")],
                          capture_output=True, text=True)
    assert proc.returncode == 2 and "neither sessions/ nor agui-sessions/" in proc.stderr


@pytest.mark.parametrize("ticks,fence_len", [(3, 4), (4, 5), (6, 7), (0, 3), (1, 3), (2, 3)])
def test_write_run_fence_is_longer_than_any_backtick_run(ticks, fence_len):
    mod = load(OWUI, "write_run")
    body = f"before\n{'`' * ticks}\nafter"
    assert mod.fence(body) == f"{'`' * fence_len}\n{body}\n{'`' * fence_len}"


def test_write_run_still_renders_an_openwebui_bundle(tmp_path):
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps({
        "exported_at": 1761732000, "tags": [{"id": "t1", "name": "exfil"}],
        "notes": [{"title": "Run report", "data": {"content": {"md": "found it"}}}],
        "chats": [{"title": "First", "created_at": 1761732000, "updated_at": 1761732000,
                   "meta": {"tags": ["t1"]},
                   "chat": {"messages": [{"role": "user", "content": "hi", "timestamp": 1761732000}]}}],
    }))
    out = tmp_path / "run"
    proc = subprocess.run([sys.executable, str(OWUI), str(bundle), str(out), "Run report"],
                          capture_output=True, text=True, check=True)
    assert proc.stdout.strip() == "1 chats, report filled in"
    assert "| [First](chats/01-first.md) | exfil |  | 1 | 2025-10-29 10:00 UTC |" in (out / "index.md").read_text()
    assert (out / "report.md").read_text() == "found it"
