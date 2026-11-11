"""archive.yml's spe-eval export/write (roles/run_archive/tasks/export_spe_eval.yml,
write_spe_eval.yml; experiments spec part 03, decision 13): on stop, ~/spe-eval's reports/,
promptfoo/ and windows.jsonl are packed, fetched and unpacked into the run directory's evals/; a
`spe` build (no ~/spe-eval) or one with no run yet copies nothing and still passes. Follows
test_archive_export.py's own pattern (a synthetic play that includes just the one role tasks file),
but needs no docker stub: export_spe_eval.yml only ever stats, tars and fetches.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

ANSIBLE = Path(__file__).resolve().parents[2] / "ansible"

pytestmark = pytest.mark.skipif(shutil.which("ansible-playbook") is None, reason="ansible-playbook not installed")

EXPORT_PLAY = """- hosts: localhost
  connection: local
  gather_facts: false
  tasks:
    - ansible.builtin.include_role:
        name: run_archive
        tasks_from: export_spe_eval
"""

WRITE_PLAY = """- hosts: localhost
  connection: local
  gather_facts: false
  tasks:
    - ansible.builtin.include_role:
        name: run_archive
        tasks_from: write_spe_eval
"""


def run_play(tmp_path: Path, play: str, name: str, extra: dict,
             path_prefix: Path | None = None) -> subprocess.CompletedProcess:
    play_path = tmp_path / name
    play_path.write_text(play)
    env = {**os.environ, "ANSIBLE_ROLES_PATH": str(ANSIBLE / "roles"), "ANSIBLE_NOCOLOR": "1",
           "ANSIBLE_LOCALHOST_WARNING": "False"}
    if path_prefix:
        env["PATH"] = f"{path_prefix}{os.pathsep}{env.get('PATH', '')}"
    return subprocess.run(
        ["ansible-playbook", str(play_path), "-e", json.dumps(extra)],
        cwd=ANSIBLE, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)


def make_spe_eval_dir(path: Path, with_windows_jsonl: bool = False) -> None:
    (path / "reports" / "ladder-l0" / "20261110T120000Z" / "baseline").mkdir(parents=True)
    (path / "reports" / "ladder-l0" / "20261110T120000Z" / "baseline" / "run.json").write_text('{"state": "ok"}')
    (path / "promptfoo").mkdir()
    (path / "promptfoo" / "promptfoo.db").write_text("fake db\n")
    if with_windows_jsonl:
        (path / "windows.jsonl").write_text('{"run": "20261110T120000Z"}\n')


def bundle_names(archive: Path) -> list[str]:
    with tarfile.open(archive) as tar:
        return tar.getnames()


# --- export_spe_eval.yml ------------------------------------------------------------------------

def test_export_with_no_spe_eval_dir_copies_nothing_and_passes(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    proc = run_play(tmp_path, EXPORT_PLAY, "export.yml",
                     {"spe_eval_dir": str(tmp_path / "no-such-spe-eval"), "spe_output_dir": str(out)})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not (out / "archive-bundle-spe-eval.tar.gz").exists()


def test_export_packs_reports_and_promptfoo_without_windows_jsonl(tmp_path):
    spe_eval_dir = tmp_path / "spe-eval"
    spe_eval_dir.mkdir()
    make_spe_eval_dir(spe_eval_dir, with_windows_jsonl=False)
    out = tmp_path / "out"
    out.mkdir()
    proc = run_play(tmp_path, EXPORT_PLAY, "export.yml",
                     {"spe_eval_dir": str(spe_eval_dir), "spe_output_dir": str(out)})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    bundle = out / "archive-bundle-spe-eval.tar.gz"
    assert bundle.is_file()
    names = bundle_names(bundle)
    assert any(n.endswith("run.json") for n in names), names
    assert any(n.endswith("promptfoo.db") for n in names), names
    assert not any(n.endswith("windows.jsonl") for n in names), names


def test_export_packs_windows_jsonl_when_present(tmp_path):
    spe_eval_dir = tmp_path / "spe-eval"
    spe_eval_dir.mkdir()
    make_spe_eval_dir(spe_eval_dir, with_windows_jsonl=True)
    out = tmp_path / "out"
    out.mkdir()
    proc = run_play(tmp_path, EXPORT_PLAY, "export.yml",
                     {"spe_eval_dir": str(spe_eval_dir), "spe_output_dir": str(out)})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    names = bundle_names(out / "archive-bundle-spe-eval.tar.gz")
    assert any(n.endswith("windows.jsonl") for n in names), names


def test_export_tolerates_a_file_changing_while_it_tars(tmp_path):
    # task 5 review, Minor: a detached run still writing progress.jsonl or the promptfoo sqlite
    # database while a workspace stop packs the archive makes tar exit 1 ("file changed as we
    # read it"), not a real error; export_spe_eval.yml must not fail the archive over it.
    # A tar on PATH that does the real work, then exits 1 as GNU tar does in that case: a live
    # writer racing tar's read speed is neither reliable nor cheap (re-review).
    spe_eval_dir = tmp_path / "spe-eval"
    spe_eval_dir.mkdir()
    make_spe_eval_dir(spe_eval_dir, with_windows_jsonl=False)
    out = tmp_path / "out"
    out.mkdir()
    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "tar").write_text(f"#!/bin/sh\n{shutil.which('tar')} \"$@\" || exit $?\n"
                              f"touch {tmp_path / 'shim-exited-1'}\n"
                              "echo 'tar: promptfoo.db: file changed as we read it' >&2\nexit 1\n")
    (shim / "tar").chmod(0o755)
    proc = run_play(tmp_path, EXPORT_PLAY, "export.yml",
                    {"spe_eval_dir": str(spe_eval_dir), "spe_output_dir": str(out)},
                    path_prefix=shim)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (tmp_path / "shim-exited-1").exists(), "the task did not run the exit-1 tar"
    assert (out / "archive-bundle-spe-eval.tar.gz").is_file()


def test_export_still_fails_on_a_real_tar_error(tmp_path):
    # The tolerance above is only for tar's own exit 1; a real error (here, a file tar cannot even
    # open) exits 2 and must still fail the task.
    spe_eval_dir = tmp_path / "spe-eval"
    spe_eval_dir.mkdir()
    make_spe_eval_dir(spe_eval_dir, with_windows_jsonl=False)
    unreadable = spe_eval_dir / "promptfoo" / "promptfoo.db"
    unreadable.chmod(0o000)
    out = tmp_path / "out"
    out.mkdir()
    try:
        proc = run_play(tmp_path, EXPORT_PLAY, "export.yml",
                        {"spe_eval_dir": str(spe_eval_dir), "spe_output_dir": str(out)})
    finally:
        unreadable.chmod(0o644)
    assert proc.returncode != 0, proc.stdout + proc.stderr


def test_export_removes_its_own_staging_directory_from_the_vm(tmp_path):
    spe_eval_dir = tmp_path / "spe-eval"
    spe_eval_dir.mkdir()
    make_spe_eval_dir(spe_eval_dir, with_windows_jsonl=True)
    out = tmp_path / "out"
    out.mkdir()
    before = set(Path("/tmp").glob("spe-eval-archive-*"))
    proc = run_play(tmp_path, EXPORT_PLAY, "export.yml",
                     {"spe_eval_dir": str(spe_eval_dir), "spe_output_dir": str(out)})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    after = set(Path("/tmp").glob("spe-eval-archive-*"))
    assert after == before


# --- write_spe_eval.yml --------------------------------------------------------------------------

def test_write_with_no_bundle_creates_no_evals_dir_and_passes(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    proc = run_play(tmp_path, WRITE_PLAY, "write.yml",
                     {"spe_output_dir": str(out), "spe_run_dir": str(run_dir)})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not (run_dir / "evals").exists()


def test_write_unpacks_the_bundle_into_evals(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    staging = tmp_path / "staging"
    make_spe_eval_dir(staging, with_windows_jsonl=True)
    bundle = out / "archive-bundle-spe-eval.tar.gz"
    with tarfile.open(bundle, "w:gz") as tar:
        for name in ("reports", "promptfoo", "windows.jsonl"):
            tar.add(staging / name, arcname=name)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    proc = run_play(tmp_path, WRITE_PLAY, "write.yml",
                     {"spe_output_dir": str(out), "spe_run_dir": str(run_dir)})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    evals = run_dir / "evals"
    assert (evals / "reports" / "ladder-l0" / "20261110T120000Z" / "baseline" / "run.json").is_file()
    assert (evals / "promptfoo" / "promptfoo.db").is_file()
    assert (evals / "windows.jsonl").is_file()
    assert not bundle.exists()  # staged bundle removed from the controller after unpacking


def test_export_then_write_round_trips_two_runs(tmp_path):
    # Two arms' worth of reports (export.yml's own docstring: "every run, each arm's ..."),
    # round-tripped through export then write exactly as archive.yml's two plays run it.
    spe_eval_dir = tmp_path / "spe-eval"
    for arm in ("baseline", "mitigated"):
        (spe_eval_dir / "reports" / "ladder-l1" / "20261110T120000Z" / arm).mkdir(parents=True)
        (spe_eval_dir / "reports" / "ladder-l1" / "20261110T120000Z" / arm / "run.json").write_text(
            json.dumps({"arm": arm}))
    (spe_eval_dir / "promptfoo").mkdir()
    (spe_eval_dir / "windows.jsonl").write_text('{"run": "20261110T120000Z"}\n')
    out = tmp_path / "out"
    out.mkdir()
    export_proc = run_play(tmp_path, EXPORT_PLAY, "export.yml",
                            {"spe_eval_dir": str(spe_eval_dir), "spe_output_dir": str(out)})
    assert export_proc.returncode == 0, export_proc.stdout + export_proc.stderr
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    write_proc = run_play(tmp_path, WRITE_PLAY, "write.yml",
                           {"spe_output_dir": str(out), "spe_run_dir": str(run_dir)})
    assert write_proc.returncode == 0, write_proc.stdout + write_proc.stderr
    for arm in ("baseline", "mitigated"):
        run_json = run_dir / "evals" / "reports" / "ladder-l1" / "20261110T120000Z" / arm / "run.json"
        assert json.loads(run_json.read_text()) == {"arm": arm}
