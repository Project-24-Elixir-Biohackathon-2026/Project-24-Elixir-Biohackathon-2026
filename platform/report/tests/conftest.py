"""Shared test helpers: the portal's directories as the watcher sees them (report sidecars, the
playbooks' output, the archived runs) and a fake instance whose sources live on tmp_path, read by
canary_watch.LocalTransport (the reader run here, no SSH). Used by test_canary_watch.py (the watcher)
and test_hits_service.py (the latency from a journal line to the participant's event stream).
Fixtures use made-up tokens only (fixtures/canary/canaries.json)."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import canary_watch  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "canary"
WORKSPACE = "6f1c2a9e-3b7d-4e1a-9c2f-0a1b2c3d4e5f"  # the fake instance's workspace id (its report sidecar)
SESSION = "aaaaaaaa-1111-4222-8333-444444444444"  # a session id, the name of a journal on the fake instance


def hosts_yml(path: Path, api_host: str = "api.spe.test", ssh_target: str = "localhost") -> None:
    path.write_text(
        "instance: " + path.parent.name + "\n"
        "api_host: " + api_host + "\n"
        "ssh_user: ubuntu\n"
        "provision: existing\n"
        "ssh_target: " + ssh_target + "\n"
    )


def sidecar(reports_dir: Path, workspace_id: str, instance: str, owner: str = "alice") -> Path:
    path = reports_dir / f"{workspace_id}.json"
    path.write_text(json.dumps({"owner": owner, "workspace": f"{owner}-ws", "instance": instance,
                                "created": "2026-11-10 14:00 UTC", "parameters": {}}))
    return path


def output_dir(output_root: Path, instance: str, encrypted: bool = False, no_record: bool = False) -> Path:
    directory = output_root / instance
    directory.mkdir(parents=True)
    hosts_yml(directory / "hosts.yml")
    if no_record:
        pass
    elif encrypted:
        (directory / "canaries.json.age").write_text("age-encrypted-stub")
    else:
        (directory / "canaries.json").write_text(json.dumps(
            {"tokens": [{"token": "FCANARY-TEST01", "type": "file", "file": "flag.txt"}]}))
    return directory


def layout(tmp_path: Path) -> tuple[Path, Path, Path]:
    reports = tmp_path / "reports"
    reports.mkdir()
    output_root = tmp_path / "output"
    runs = tmp_path / "runs"
    runs.mkdir()
    return reports, output_root, runs


def make_fake_instance(tmp_path: Path, encrypted: bool = False
                       ) -> tuple["canary_watch.LocalTransport", Path, Path, Path]:
    """A fake instance named `fixture` (workspace WORKSPACE, owner alice): its output directory
    (fixtures' hosts.yml and canaries.json, or only canaries.json.age), its report sidecar, and its
    four sources under tmp_path/instance, none written yet. The transport's `paths` name them:
    `sessions` (a journal per session, SESSION's among them), `agent_runs`, `receiver`, `webui_db`.
    Returns (transport, output_root, reports_dir, runs_dir)."""
    reports, output_root, runs = layout(tmp_path)
    out = output_root / "fixture"
    out.mkdir(parents=True)
    shutil.copy(FIXTURES / "hosts.yml", out / "hosts.yml")
    if encrypted:
        (out / "canaries.json.age").write_text("age-encrypted-stub")
    else:
        shutil.copy(FIXTURES / "canaries.json", out / "canaries.json")
    sidecar(reports, WORKSPACE, "fixture")
    instance = tmp_path / "instance"
    (instance / "sessions").mkdir(parents=True)
    paths = {"sessions": str(instance / "sessions"), "agent_runs": str(instance / "runs.jsonl"),
             "receiver": str(instance / "requests.jsonl"), "webui_db": str(instance / "webui.db")}
    return canary_watch.LocalTransport(paths), output_root, reports, runs


@pytest.fixture
def fake_instance(tmp_path):
    return make_fake_instance(tmp_path)
