"""spe-apply up recreates every container when the compose networks changed since the last up:
Compose 5.3 on Docker 29 recreates a network whose
config changed (the egress overlay gives `tools` its own subnet) but reconnects a container on two
networks without its service alias there, so the sandbox could no longer resolve `agent`. Uses a fake
`docker` on PATH that records its calls (test_spe_apply_lock.py's pattern); `config --format json`
answers with $FAKE_NETWORKS as the networks section.
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[2]  # platform/dev/tests -> platform
SPE_APPLY = HERE / "instance" / "spe-apply"

FAKE_DOCKER = """#!/bin/sh
echo "$*" >> "$FAKE_LOG"
case "$*" in
  *"config --format json"*) printf '{"services": {}, "networks": %s}\\n' "$FAKE_NETWORKS" ;;
esac
exit 0
"""

TOOLS = {"spe-frontend_tools": {"name": "spe-frontend_tools"}}
TOOLS_EGRESS = {"spe-frontend_tools": {"name": "spe-frontend_tools",
                                       "ipam": {"config": [{"subnet": "172.30.0.0/24"}]}}}


@pytest.fixture
def up(tmp_path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / ".env").write_text(f"SPE_REPO_DIR={tmp_path / 'repo'}\nCOMPOSE_PROFILES=none\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text(FAKE_DOCKER)
    (bin_dir / "docker").chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    log = tmp_path / "docker.log"

    def run(networks):
        log.unlink(missing_ok=True)
        env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "SPE_FRONTEND_DIR": str(frontend),
               "HOME": str(home), "FAKE_LOG": str(log), "FAKE_NETWORKS": json.dumps(networks)}
        p = subprocess.run(["bash", str(SPE_APPLY), "up"], env=env, capture_output=True, text=True)
        assert p.returncode == 0, p.stdout + p.stderr
        return [c for c in log.read_text().splitlines() if " up -d" in c]

    return run


def test_the_first_up_recreates_since_the_networks_it_finds_are_unknown(up):
    # An instance from before this check (or a fresh one, where recreating costs nothing).
    assert "--force-recreate" in up(TOOLS)[0]


def test_an_up_with_unchanged_networks_does_not_recreate(up):
    up(TOOLS)
    assert "--force-recreate" not in up(TOOLS)[0]


def test_an_overlay_changing_a_network_recreates_both_ways(up):
    up(TOOLS)
    assert "--force-recreate" in up(TOOLS_EGRESS)[0]   # L3 on
    assert "--force-recreate" not in up(TOOLS_EGRESS)[0]
    assert "--force-recreate" in up(TOOLS)[0]          # L3 off again
