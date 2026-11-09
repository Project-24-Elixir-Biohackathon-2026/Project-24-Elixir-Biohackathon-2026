"""Probe scripts: syntax, the PROBE marker, and the simple ones over a stub curl."""
import os
import subprocess
from pathlib import Path

import pytest

import controls_asserts
import controls_provider as cp
from conftest import hosts, write_hosts

PROBES = Path(__file__).resolve().parents[1] / "probes"


def test_one_script_per_probe_and_valid_sh():
    assert sorted(p.stem for p in PROBES.glob("*.sh")) == sorted(controls_asserts.PROBE_CONTROL)
    for script in PROBES.glob("*.sh"):
        subprocess.run(["sh", "-n", str(script)], check=True)
        assert "PROBE open" in script.read_text(), script.name


def run(tmp_path, probe, code, rc=0, env=None):
    bin_ = tmp_path / "bin"
    bin_.mkdir(exist_ok=True)
    (bin_ / "curl").write_text(f"#!/bin/sh\nprintf '%s' '{code}'\nexit {rc}\n")
    (bin_ / "curl").chmod(0o755)
    e = {"PATH": f"{bin_}:{os.environ['PATH']}", "TRS_BASE": "https://h/ga4gh/trs/v2",
         "WES_BASE": "https://h/ga4gh/wes/v1", "SPE_ISOLATION_MARKER": str(tmp_path / "marker"),
         "SPE_ISOLATION_TMP_MARKER": str(tmp_path / "tmp-marker"), **(env or {})}
    p = subprocess.run(["sh", "-s"], input=(PROBES / f"{probe}.sh").read_text(), env=e,
                       capture_output=True, text=True)
    return cp.parse(p.returncode, p.stdout, p.stderr)


@pytest.mark.parametrize("probe,code,rc,state", [
    ("trs-write", "400", 0, "open"), ("trs-write", "422", 0, "open"),
    ("trs-write", "403", 0, "closed"), ("trs-write", "405", 0, "closed"),
    ("trs-write", "502", 0, "error"), ("trs-write", "000", 7, "error"),
    ("egress", "200", 0, "open"), ("egress", "301", 0, "open"), ("egress", "000", 28, "closed"),
    ("api-reach", "200", 0, "open"), ("api-reach", "000", 7, "closed"),
    ("isolation-check", "404", 0, "closed"), ("isolation-check", "200", 0, "open"),
    ("isolation-check", "500", 0, "error"),
])
def test_stub_curl(tmp_path, probe, code, rc, state):
    assert run(tmp_path, probe, code, rc)["state"] == state


def test_isolation_plant_then_check_sees_the_sandbox_marker(tmp_path):
    assert run(tmp_path, "isolation-plant", "201")["state"] == "open"
    res = run(tmp_path, "isolation-check", "404")  # TRS restored, sandbox not
    assert res["state"] == "open" and "sandbox" in res["evidence"]


def test_isolation_check_sees_a_marker_outside_the_volume(tmp_path):
    # A restore that put the volumes back but restarted the container keeps /tmp (clarification 5).
    assert run(tmp_path, "isolation-plant", "201")["state"] == "open"
    (tmp_path / "marker").unlink()
    res = run(tmp_path, "isolation-check", "404")
    assert res["state"] == "open" and "tmp" in res["evidence"]


def test_isolation_check_marker_left_fails(tmp_path, monkeypatch):
    (tmp_path / "hardening.json").write_text(
        '{"schema_version": 1, "instance": "t-01", "level": 0, "switches": {"spe_harden_trs_readonly": false, '
        '"spe_harden_data_tiers": [], "spe_harden_egress": false, "spe_agent_tool_surface": "shell", '
        '"spe_harden_airlock": false}, "frontend": "agui", "model_provider": "x", "model": "m", '
        '"commit": "0", "restore_seconds": null, "injections": true}')
    write_hosts(tmp_path, hosts("t-01"))  # handoff.load_hardening checks the instance against hosts.yml
    monkeypatch.setenv("SPE_HANDOFF_DIR", str(tmp_path))
    res = run(tmp_path, "isolation-check", "200")
    verdict = controls_asserts.probe_state("", {"metadata": {"probe": "isolation-check", "state": res["state"],
                                                              "evidence": res["evidence"], "http_codes": {}}})
    assert not verdict["pass"] and "expected closed" in verdict["reason"]
