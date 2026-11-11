"""spe-apply's lock check and its all/stack argument passthrough (experiments spec part 03,
decision 11): refuses while ~/spe-eval/lock is held unless SPE_EVAL_LOCK names the holder's own
token; a missing lock file is "not held". Uses fake ansible-playbook/ansible-galaxy on PATH, so no
real Ansible run happens, following tests/test_run_sh.py's pattern (promptfoo-evals) of a fake
tool on PATH that records its own calls.
"""
import fcntl
import os
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[2]  # platform/dev/tests -> platform
SPE_APPLY = HERE / "instance" / "spe-apply"

FAKE_ANSIBLE_PLAYBOOK = """#!/bin/sh
echo "$*" >> "$FAKE_LOG"
exit 0
"""
FAKE_ANSIBLE_GALAXY = """#!/bin/sh
echo "community.docker 3.0.0"
"""


@pytest.fixture
def setup(tmp_path):
    repo = tmp_path / "repo"
    (repo / "platform" / "ansible" / "instances").mkdir(parents=True)
    (repo / "platform" / "ansible" / "instances" / "local.yml").write_text("spe_instance: t-01\n")

    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / ".env").write_text(f"SPE_REPO_DIR={repo}\nCOMPOSE_PROFILES=agui\n")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "ansible-playbook").write_text(FAKE_ANSIBLE_PLAYBOOK)
    (bin_dir / "ansible-playbook").chmod(0o755)
    (bin_dir / "ansible-galaxy").write_text(FAKE_ANSIBLE_GALAXY)
    (bin_dir / "ansible-galaxy").chmod(0o755)

    home = tmp_path / "home"
    home.mkdir()
    log = tmp_path / "ansible.log"

    def run(*args, extra_env=None):
        env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "SPE_FRONTEND_DIR": str(frontend),
                "HOME": str(home), "FAKE_LOG": str(log), **(extra_env or {})}
        p = subprocess.run(["bash", str(SPE_APPLY), *args], env=env, capture_output=True, text=True)
        calls = log.read_text().splitlines() if log.exists() else []
        return p.returncode, p.stdout, p.stderr, calls

    return run, home


def test_missing_lock_file_is_not_held(setup):
    run, _home = setup
    rc, _out, err, calls = run("all", "-e", "foo=bar")
    assert rc == 0, err
    assert len(calls) == 1
    assert "--tags stack,drs,trs,frontend" in calls[0]
    assert "-e foo=bar" in calls[0]  # all passes extra arguments through, as ansible already did


def test_stack_passes_extra_arguments_through(setup):
    run, _home = setup
    rc, _out, err, calls = run("stack", "--check")
    assert rc == 0, err
    assert len(calls) == 1
    assert "--tags stack,drs,trs " in calls[0] or calls[0].endswith("stack,drs,trs")
    assert "--check" in calls[0]


def test_refuses_while_another_run_holds_the_lock(setup):
    run, home = setup
    lock_path = home / "spe-eval" / "lock"
    lock_path.parent.mkdir(parents=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.write(fd, b"20261110T120000Z")
    try:
        rc, _out, err, calls = run("all")
        assert rc == 2, err
        assert "spe-eval run 20261110T120000Z holds the lock; wait for it (spe-eval wait)" in err
        assert calls == []  # never reached ansible-playbook
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_proceeds_with_the_holders_own_token(setup):
    run, home = setup
    lock_path = home / "spe-eval" / "lock"
    lock_path.parent.mkdir(parents=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.write(fd, b"20261110T120000Z")
    try:
        rc, _out, err, calls = run("all", extra_env={"SPE_EVAL_LOCK": "20261110T120000Z"})
        assert rc == 0, err
        assert len(calls) == 1
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_a_wrong_token_still_refuses(setup):
    run, home = setup
    lock_path = home / "spe-eval" / "lock"
    lock_path.parent.mkdir(parents=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.write(fd, b"20261110T120000Z")
    try:
        rc, _out, err, calls = run("all", extra_env={"SPE_EVAL_LOCK": "someone-elses-token"})
        assert rc == 2, err
        assert calls == []
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_help_proceeds_while_locked(setup):
    # task 3 review, minor 4: status, logs and --help/-h/help are read-only and let through even
    # while another run holds the lock (spe-eval status's own wait calls spe-apply status).
    run, home = setup
    lock_path = home / "spe-eval" / "lock"
    lock_path.parent.mkdir(parents=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.write(fd, b"20261110T120000Z")
    try:
        rc, out, err, calls = run("--help")
        assert rc == 0, err
        assert "spe-apply" in out
        assert "holds the lock" not in err
        assert calls == []  # never reaches ansible-playbook
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_a_lock_file_present_but_not_actually_held_is_not_held(setup):
    # A stale file left by a crashed holder (no fd open any more): flock -n succeeds, so a plain
    # spe-apply still runs (only an active flock -- not just the file's existence -- blocks it).
    run, home = setup
    lock_path = home / "spe-eval" / "lock"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text("20261109T000000Z")
    rc, _out, err, calls = run("all")
    assert rc == 0, err
    assert len(calls) == 1
