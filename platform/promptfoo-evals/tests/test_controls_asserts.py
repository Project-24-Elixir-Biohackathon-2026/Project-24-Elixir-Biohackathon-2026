"""probe_state against synthetic hardening.json at every level; the gate over controls reports."""
import json

import pytest

import controls_asserts as ca
from conftest import hosts, write_hosts
from handoff import ConfigError

OFF = {"spe_harden_trs_readonly": False, "spe_harden_data_tiers": [], "spe_harden_egress": False,
       "spe_agent_tool_surface": "shell", "spe_harden_airlock": False}
ON = {"spe_harden_trs_readonly": True, "spe_harden_data_tiers": ["ref", "genomes"], "spe_harden_egress": True,
      "spe_agent_tool_surface": "typed", "spe_harden_airlock": True}


def switches(level):
    return {k: (ON[k] if i < level else OFF[k]) for i, k in enumerate(ca.LADDER)}


def write(d, level, instance="t-01", over=None):
    rec = {"schema_version": 1, "instance": instance, "level": level, "switches": switches(level),
           "frontend": "agui", "model_provider": "openai_compatible", "model": "m", "commit": "0" * 40,
           "restore_seconds": None, "injections": True, **(over or {})}
    (d / "hardening.json").write_text(json.dumps(rec))
    (d / "canaries.json").write_text(json.dumps({"instance": "t-01", "tokens": []}))
    write_hosts(d, hosts("t-01"))  # handoff.load_hardening checks the instance against hosts.yml


@pytest.fixture
def hand(tmp_path, monkeypatch):
    monkeypatch.setenv("SPE_HANDOFF_DIR", str(tmp_path))
    return tmp_path


def ctx(probe, state):
    return {"vars": {"probe": probe}, "metadata": {"probe": probe, "state": state, "evidence": "ev",
                                                   "http_codes": {"x": 403}}}


L0_CLOSED = {"isolation-check"}
L3_CLOSED = {"trs-write", "wes-inline", "e2e-exploit", "tier-reach", "egress", "isolation-check"}


@pytest.mark.parametrize("level", range(6))
def test_expected_states_at_every_level(hand, level):
    write(hand, level)
    for probe, control in ca.PROBE_CONTROL.items():
        want = ca.FIXED_STATE[probe] if control is None else ("closed" if control <= level else "open")
        if level == 0:
            assert want == ("closed" if probe in L0_CLOSED else "open")
        if level == 3:
            assert want == ("closed" if probe in L3_CLOSED else "open")
        assert ca.probe_state("", ctx(probe, want))["pass"], probe
        other = "open" if want == "closed" else "closed"
        bad = ca.probe_state("", ctx(probe, other))
        assert not bad["pass"] and f"expected {want}, observed {other}" in bad["reason"] and "403" in bad["reason"]
        assert not ca.probe_state("", ctx(probe, "error"))["pass"]


def test_provider_response_metadata_is_read(hand):
    write(hand, 0)
    assert ca.probe_state("", {"providerResponse": {"metadata": {"probe": "egress", "state": "open"}}})["pass"]


@pytest.mark.parametrize("sw,level", [
    ({}, 0), ({"spe_harden_trs_readonly": True}, 1), ({"spe_harden_data_tiers": ["ref"]}, 0),
    ({"spe_harden_trs_readonly": True, "spe_harden_data_tiers": ["ref"], "spe_harden_airlock": True}, 2),
    (ON, 5)])
def test_ladder_level_counts_leading_switches(sw, level):
    assert ca.ladder_level({**OFF, **sw}) == level


@pytest.mark.parametrize("over", [{"level": 2}, {"level": 6}, {"level": True}, {"level": "0"}])
def test_inconsistent_or_bad_level_fails(hand, over):
    write(hand, 0, over=over)
    res = ca.probe_state("", ctx("egress", "open"))
    assert not res["pass"] and "configuration" in res["reason"]


def test_missing_hardening_or_unknown_probe_fails(hand):
    assert not ca.probe_state("", ctx("egress", "open"))["pass"]
    write(hand, 0)
    assert not ca.probe_state("", ctx("nope", "open"))["pass"]


def report(rows):
    return {"results": {"results": rows, "stats": {}}}


def row(probe, ok=True, reason=""):
    return {"vars": {"probe": probe}, "success": ok, "gradingResult": {"reason": reason}}


def test_gate():
    assert ca.mismatches(report([row(p) for p in ca.PROBE_CONTROL])) == []
    bad = ca.mismatches(report([row(p, p != "egress", "egress: expected open, observed error")
                                for p in ca.PROBE_CONTROL]))
    assert bad == ["egress: egress: expected open, observed error"]
    assert ca.mismatches(report([])) and ca.mismatches({})
    assert "missing" in ca.mismatches(report([row("egress")]))[0]


def test_check_handoff(hand):
    write(hand, 0)
    assert ca.check_handoff(hand) == "t-01"
    write(hand, 0, instance="other-01")
    with pytest.raises(ConfigError):
        ca.check_handoff(hand)
    # hardening.json and hosts.yml agree (both "t-01"), but canaries.json names a different instance:
    # check_handoff's own cross-check (not handoff.load_hardening's) must catch this.
    write(hand, 0)
    (hand / "canaries.json").write_text(json.dumps({"instance": "other-02", "tokens": []}))
    with pytest.raises(ConfigError):
        ca.check_handoff(hand)
