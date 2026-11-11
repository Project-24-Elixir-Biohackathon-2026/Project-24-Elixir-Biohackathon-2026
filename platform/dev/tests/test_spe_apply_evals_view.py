"""spe-apply's evals-view component (task 2): `default_components` adds it only under the
`evals` profile, `build evals-view` runs the documented `docker build`, the unknown-component
message and `--help` both mention it, and `up` waits for `SPE_EVALS_PORT` only under that same
profile. Uses a fake docker and curl on PATH, test_spe_apply_lock.py's and test_spe_apply_up.py's
pattern (a fake tool that records its own calls); no real image is built or port probed.
"""
import os
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[2]  # platform/dev/tests -> platform
SPE_APPLY = HERE / "instance" / "spe-apply"

FAKE_DOCKER = """#!/bin/sh
echo "$*" >> "$FAKE_LOG"
case "$*" in
  *"config --format json"*) printf '{"services": {}, "networks": {}}\\n' ;;
esac
exit 0
"""
FAKE_CURL = """#!/bin/sh
echo "$*" >> "$FAKE_CURL_LOG"
exit 0
"""


@pytest.fixture
def setup(tmp_path):
    repo = tmp_path / "repo"
    sandbox_files = repo / "platform" / "ansible" / "roles" / "sandbox" / "files"
    sandbox_files.mkdir(parents=True)
    (sandbox_files / "Dockerfile.terminal").write_text("FROM scratch\n")  # `install`ed for real, by build()

    frontend = tmp_path / "frontend"
    frontend.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text(FAKE_DOCKER)
    (bin_dir / "docker").chmod(0o755)
    (bin_dir / "curl").write_text(FAKE_CURL)
    (bin_dir / "curl").chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    docker_log = tmp_path / "docker.log"
    curl_log = tmp_path / "curl.log"

    def write_profiles(profiles):
        (frontend / ".env").write_text(
            f"SPE_REPO_DIR={repo}\n"
            f"COMPOSE_PROFILES={profiles}\n"
            "SPE_TERMINAL_IMAGE=spe-open-terminal:test\n"
            "SPE_AGENT_IMAGE=spe-agent:test\n"
            "SPE_CHAT_UI_IMAGE=spe-chat-ui:test\n"
            "SPE_EVALS_VIEW_IMAGE=spe-evals-view:test\n"
            "SPE_EVALS_PORT=8200\n"
            "SPE_WEBUI_PORT=8080\n"
            "SPE_AGUI_AGENT_PORT=8100\n"
            "SPE_AGUI_UI_PORT=3000\n"
        )

    def run(*args):
        docker_log.unlink(missing_ok=True)
        curl_log.unlink(missing_ok=True)
        run_env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "SPE_FRONTEND_DIR": str(frontend),
                   "HOME": str(home), "FAKE_LOG": str(docker_log), "FAKE_CURL_LOG": str(curl_log)}
        p = subprocess.run(["bash", str(SPE_APPLY), *args], env=run_env, capture_output=True, text=True)
        docker_calls = docker_log.read_text().splitlines() if docker_log.exists() else []
        curl_calls = curl_log.read_text().splitlines() if curl_log.exists() else []
        return p.returncode, p.stdout, p.stderr, docker_calls, curl_calls

    return repo, write_profiles, run


def test_default_build_includes_evals_view_only_with_the_evals_profile(setup):
    _repo, write_profiles, run = setup
    write_profiles("evals")
    rc, out, err, *_ = run("build")
    assert rc == 0, err
    assert "== build sandbox" in out
    assert "== build evals-view" in out

    write_profiles("openwebui")
    rc, out, err, *_ = run("build")
    assert rc == 0, err
    assert "== build evals-view" not in out


def test_build_evals_view_runs_the_documented_docker_build(setup):
    repo, write_profiles, run = setup
    write_profiles("evals")
    rc, _out, err, calls, _ = run("build", "evals-view")
    assert rc == 0, err
    assert calls == [
        f"build --provenance=false -t spe-evals-view:test -f {repo}/platform/instance/evals-view/Dockerfile "
        f"{repo}/platform/promptfoo-evals"
    ]


def test_unknown_component_message_lists_evals_view(setup):
    _repo, write_profiles, run = setup
    write_profiles("evals")
    rc, _out, err, *_ = run("build", "bogus")
    assert rc == 2
    assert "unknown component 'bogus' (agent, chat-ui, sandbox, evals-view)" in err


def test_help_mentions_evals_view_and_prints_exactly_the_header_comment(setup):
    _repo, write_profiles, run = setup
    write_profiles("evals")
    rc, out, err, *_ = run("--help")
    assert rc == 0, err
    assert "evals-view" in out
    # Regression check for the header's own line count: --help must print every comment line up
    # to (not including) the first code line, not one short of it.
    lines = SPE_APPLY.read_text().splitlines()
    first_code = next(i for i, line in enumerate(lines) if i > 0 and not line.startswith("#"))
    assert out == "\n".join(lines[1:first_code]) + "\n"


def test_up_waits_for_the_evals_port_only_with_the_evals_profile(setup):
    _repo, write_profiles, run = setup
    write_profiles("evals")
    rc, _out, err, _docker_calls, curl_calls = run("up")
    assert rc == 0, err
    assert any("127.0.0.1:8200/" in c for c in curl_calls)

    write_profiles("openwebui")
    rc, _out, err, _docker_calls, curl_calls = run("up")
    assert rc == 0, err
    assert not any(":8200/" in c for c in curl_calls)
