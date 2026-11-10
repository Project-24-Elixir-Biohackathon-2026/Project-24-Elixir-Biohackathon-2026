"""sync-template.sh pushes spe and spe-experiments, and keeps one Coder template per branch
named template/<name> or experiment/<name>, sharing the branch loop between the two kinds
(experiments spec, 02-coder-template.md, *Where the options come from*).

Run against a temp git repo (a bare origin and a clone standing in for the portal's checkout),
with a stub `coder` on PATH that logs its argv and succeeds, and a stub `python3` that always
fails: the site build is not under test here, and the script tolerates its failure.
"""
import os
import shutil
import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "platform/coder/deploy/sync-template.sh"
ASSEMBLE = REPO / "platform/coder/experiments-template/assemble.sh"
SEP = "\x1f"  # a unit separator between logged argv fields; tmp paths never contain one


def make_bin_dir(tmp_path: Path, log: Path, fail_push: str | None = None) -> Path:
    """A stub `coder` ahead of any real one on PATH: it logs every call's argv, one call per
    line (fields joined by SEP, so a directory with spaces would not confuse the split).
    It always succeeds, unless `fail_push` names a template: then `templates push
    <fail_push>` exits 1 (still logged), standing in for a real push failure, so tests can
    assert the other pushes are unaffected. A stub `python3` always fails, standing in for a
    missing mkdocs-material."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    coder = bin_dir / "coder"
    fail_check = (
        f'if [[ "$1" == templates && "$2" == push && "$3" == "{fail_push}" ]]; then exit 1; fi\n'
        if fail_push
        else ""
    )
    coder.write_text(
        "#!/usr/bin/env bash\n"
        f'printf \'%s\\x1f\' "$@" >> "{log}"\n'
        f'printf \'\\n\' >> "{log}"\n'
        f"{fail_check}"
        "exit 0\n"
    )
    python3 = bin_dir / "python3"
    python3.write_text("#!/usr/bin/env bash\nexit 1\n")
    for p in (coder, python3):
        p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


def read_calls(log: Path) -> list[list[str]]:
    if not log.exists():
        return []
    return [line.split(SEP)[:-1] for line in log.read_text().splitlines() if line]


def flag(call: list[str], name: str) -> str:
    return call[call.index(name) + 1]


def make_repo(tmp_path: Path) -> tuple[Path, Path]:
    """A bare origin and a clone of it with the minimal files sync-template.sh and
    assemble.sh need: spe's and spe-experiments' template directories (the real assemble.sh,
    copied in, not a stub), run-ansible.sh, one experiment, one mitigation, and the injection
    fixtures."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--quiet", "--bare", str(origin)], check=True)
    repo = tmp_path / "repo"
    subprocess.run(["git", "clone", "--quiet", str(origin), str(repo)], check=True)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}

    def run(*args: str) -> None:
        subprocess.run(args, cwd=repo, env=env, check=True)

    (repo / "platform/site").mkdir(parents=True)
    (repo / "platform/site/build.py").write_text("# stubbed out by the test's python3\n")
    (repo / "platform/coder/template").mkdir(parents=True)
    (repo / "platform/coder/template/main.tf").write_text("# dummy\n")
    run_ansible = repo / "platform/coder/template/run-ansible.sh"
    run_ansible.write_text("#!/usr/bin/env bash\necho dummy\n")
    run_ansible.chmod(0o755)
    (repo / "platform/coder/experiments-template").mkdir(parents=True)
    exp_assemble = repo / "platform/coder/experiments-template/assemble.sh"
    shutil.copy(ASSEMBLE, exp_assemble)
    exp_assemble.chmod(0o755)
    (repo / "platform/coder/experiments-template/main.tf").write_text("# dummy\n")
    (repo / "experiments").mkdir()
    (repo / "experiments/ladder-l0.yml").write_text("name: Ladder L0\n")
    (repo / "mitigations").mkdir()
    (repo / "mitigations/L1.yml").write_text("id: L1\n")
    (repo / "platform/ansible/catalog/injections").mkdir(parents=True)
    (repo / "platform/ansible/catalog/injections/fixtures.json").write_text('{"fixtures": []}\n')

    run("git", "add", "-A")
    run("git", "commit", "--quiet", "-m", "initial")
    run("git", "branch", "--quiet", "-M", "main")
    run("git", "push", "--quiet", "origin", "main")
    return origin, repo


def make_branch(repo: Path, ref: str) -> None:
    """Push `ref` to origin pointing at main's current tip. No local branch is left behind:
    the branch loop reads origin's remote-tracking refs, not local branches."""
    subprocess.run(["git", "push", "--quiet", "origin", f"HEAD:refs/heads/{ref}"], cwd=repo, check=True)


def delete_branch(repo: Path, ref: str) -> None:
    subprocess.run(["git", "push", "--quiet", "origin", "--delete", ref], cwd=repo, check=True)


def run_sync(repo: Path, bin_dir: Path, branch_dir: Path, **extra_env: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
           "SPE_REPO_DIR": str(repo), "SPE_BRANCH": "main", "SPE_TEMPLATE_NAME": "spe-test",
           "SPE_AGENT_URL": "http://agent.example", "SPE_BRANCH_DIR": str(branch_dir), **extra_env}
    return subprocess.run([str(SCRIPT)], env=env, capture_output=True, text=True)


def test_spe_and_spe_experiments_pushed_with_the_right_directories(tmp_path):
    _, repo = make_repo(tmp_path)
    log = tmp_path / "coder.log"
    bin_dir = make_bin_dir(tmp_path, log)
    result = run_sync(repo, bin_dir, tmp_path / "branches")
    assert result.returncode == 0, result.stdout + result.stderr

    pushes = {c[2]: c for c in read_calls(log) if c[:2] == ["templates", "push"]}
    assert set(pushes) >= {"spe-test", "spe-experiments"}
    # Both are pushed with a path relative to the checkout: the script cd's into it first.
    assert flag(pushes["spe-test"], "--directory") == "platform/coder/template"
    exp_dir = repo / flag(pushes["spe-experiments"], "--directory")
    assert exp_dir == repo / "platform/coder/experiments-template"
    # assemble.sh ran on the main checkout before the push: the copied-in files are there.
    assert sorted(p.name for p in (exp_dir / "experiments").glob("*.yml")) == ["ladder-l0.yml"]
    assert (exp_dir / "run-ansible.sh").exists()


def test_experiment_branch_pushed_as_spe_x_name_with_its_worktree_assembled_dir(tmp_path):
    _, repo = make_repo(tmp_path)
    make_branch(repo, "experiment/foo")
    log = tmp_path / "coder.log"
    bin_dir = make_bin_dir(tmp_path, log)
    branch_dir = tmp_path / "branches"
    result = run_sync(repo, bin_dir, branch_dir)
    assert result.returncode == 0, result.stdout + result.stderr

    pushes = [c for c in read_calls(log) if c[:2] == ["templates", "push"]]
    foo = next(c for c in pushes if c[2] == "spe-x-foo")
    worktree_dir = Path(flag(foo, "--directory"))
    # The "x." marker keeps experiment/<name> worktrees distinct from template/<name> ones
    # (whose names can never contain a dot), not "experiment-foo".
    assert worktree_dir == branch_dir / "x.foo/platform/coder/experiments-template"
    assert sorted(p.name for p in (worktree_dir / "mitigations").glob("*.yml")) == ["L1.yml"]
    edits = [c for c in read_calls(log) if c[:2] == ["templates", "edit"] and c[2] == "spe-x-foo"]
    assert edits and flag(edits[0], "--display-name") == "experiment/foo"


def test_a_too_long_experiment_name_is_skipped_with_the_message(tmp_path):
    _, repo = make_repo(tmp_path)
    long_name = "a" * 27  # the limit is 26 (1 + 25), so 27 is one over
    make_branch(repo, f"experiment/{long_name}")
    log = tmp_path / "coder.log"
    bin_dir = make_bin_dir(tmp_path, log)
    result = run_sync(repo, bin_dir, tmp_path / "branches")
    assert result.returncode == 0, result.stdout + result.stderr

    assert not any(c[:2] == ["templates", "push"] and c[2] == f"spe-x-{long_name}" for c in read_calls(log))
    assert f"experiment/{long_name}" in result.stderr
    assert "26 characters at most" in result.stderr
    assert "skipped" in result.stderr


def test_an_experiment_branch_without_the_experiments_template_is_skipped(tmp_path):
    _, repo = make_repo(tmp_path)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    # A commit lacking the experiments template, as on a branch cut before it existed.
    subprocess.run(["git", "checkout", "--quiet", "-b", "old"], cwd=repo, check=True)
    subprocess.run(["git", "rm", "--quiet", "-r", "platform/coder/experiments-template"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "old"], cwd=repo, env=env, check=True)
    make_branch(repo, "experiment/old")
    subprocess.run(["git", "checkout", "--quiet", "main"], cwd=repo, check=True)
    log = tmp_path / "coder.log"
    bin_dir = make_bin_dir(tmp_path, log)
    result = run_sync(repo, bin_dir, tmp_path / "branches")
    assert result.returncode == 0, result.stdout + result.stderr

    assert not any(c[:2] == ["templates", "push"] and c[2] == "spe-x-old" for c in read_calls(log))
    assert "experiment/old" in result.stderr and "skipped" in result.stderr


def test_a_deleted_branchs_template_is_deleted(tmp_path):
    _, repo = make_repo(tmp_path)
    make_branch(repo, "template/to-delete")
    log = tmp_path / "coder.log"
    bin_dir = make_bin_dir(tmp_path, log)
    branch_dir = tmp_path / "branches"
    first = run_sync(repo, bin_dir, branch_dir)
    assert first.returncode == 0, first.stdout + first.stderr
    assert any(c[:2] == ["templates", "push"] and c[2] == "spe-to-delete" for c in read_calls(log))
    # The pre-experiments paths, unprefixed by kind: $branch_dir/<name>, not "template-<name>".
    assert (branch_dir / "to-delete").is_dir()
    assert (branch_dir / ".pushed-to-delete").exists()

    delete_branch(repo, "template/to-delete")
    log.unlink()  # only the second run's calls matter here
    second = run_sync(repo, bin_dir, branch_dir)
    assert second.returncode == 0, second.stdout + second.stderr
    calls = read_calls(log)
    assert any(c[:2] == ["templates", "delete"] and c[2] == "spe-to-delete" for c in calls)
    assert not (branch_dir / ".pushed-to-delete").exists()
    assert "spe-to-delete removed" in second.stdout


def test_template_branch_uses_the_pre_experiments_worktree_and_state_paths(tmp_path):
    """Deploying the experiment kind must change nothing for template/<name> branches already
    synced in production: same worktree dir and state-file name as before c89df2c, with no
    "template-" or "template." marker added."""
    _, repo = make_repo(tmp_path)
    make_branch(repo, "template/foo")
    log = tmp_path / "coder.log"
    bin_dir = make_bin_dir(tmp_path, log)
    branch_dir = tmp_path / "branches"
    result = run_sync(repo, bin_dir, branch_dir)
    assert result.returncode == 0, result.stdout + result.stderr

    assert (branch_dir / "foo").is_dir()
    assert (branch_dir / ".pushed-foo").exists()
    assert not (branch_dir / "template-foo").exists()
    assert not (branch_dir / "template.foo").exists()
    assert not (branch_dir / ".pushed-template-foo").exists()
    assert not (branch_dir / ".pushed-template.foo").exists()


def test_a_spe_experiments_push_failure_does_not_stop_other_pushes(tmp_path):
    """Named risk: spe-experiments' assemble/push runs before the template/ and experiment/
    branch loops. A failure there must not abort the script under set -e and silently skip
    every branch for the cycle."""
    _, repo = make_repo(tmp_path)
    make_branch(repo, "template/foo")
    make_branch(repo, "experiment/bar")
    log = tmp_path / "coder.log"
    bin_dir = make_bin_dir(tmp_path, log, fail_push="spe-experiments")
    branch_dir = tmp_path / "branches"
    result = run_sync(repo, bin_dir, branch_dir)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "spe-experiments" in result.stderr

    pushed_names = {c[2] for c in read_calls(log) if c[:2] == ["templates", "push"]}
    assert "spe-test" in pushed_names  # spe's own push, unaffected (runs first, as before)
    assert "spe-foo" in pushed_names
    assert "spe-x-bar" in pushed_names
    # Not written: retried on the next run.
    assert not (repo / ".git/sperange-pushed-experiments").exists()


def test_a_branch_push_failure_does_not_stop_other_branches(tmp_path):
    """One template/<name> branch failing to push must not abort the experiment/<name> loop
    (or the rest of the template/ loop), and the failed branch's state file must stay unwritten
    so it is retried next run."""
    _, repo = make_repo(tmp_path)
    make_branch(repo, "template/foo")
    make_branch(repo, "experiment/bar")
    log = tmp_path / "coder.log"
    bin_dir = make_bin_dir(tmp_path, log, fail_push="spe-foo")
    branch_dir = tmp_path / "branches"
    result = run_sync(repo, bin_dir, branch_dir)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "spe-foo" in result.stderr

    pushed_names = {c[2] for c in read_calls(log) if c[:2] == ["templates", "push"]}
    assert "spe-test" in pushed_names
    assert "spe-experiments" in pushed_names
    assert "spe-x-bar" in pushed_names
    assert not (branch_dir / ".pushed-foo").exists()


def test_shell_syntax_and_shellcheck():
    assert subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True).returncode == 0
    if shutil.which("shellcheck"):
        p = subprocess.run(["shellcheck", str(SCRIPT)], capture_output=True, text=True)
        assert p.returncode == 0, p.stdout
