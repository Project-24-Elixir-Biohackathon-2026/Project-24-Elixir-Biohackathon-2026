"""The ladder's instance examples (spec part 01, decisions 2 and 3)."""
import re
from pathlib import Path

import pytest
import yaml

ANSIBLE = Path(__file__).resolve().parents[2] / "ansible"
# Level n switches on LADDER[n - 1]; off is the default in group_vars/all.yml.
LADDER = ["spe_harden_trs_readonly", "spe_harden_data_tiers", "spe_harden_egress",
          "spe_agent_tool_surface", "spe_harden_airlock"]
INJECT = ["spe_inject_trs_description", "spe_inject_drs_description", "spe_inject_workflow_comment"]
EVAL = INJECT + ["spe_eval_sink"]  # evaluation fixtures: on at every level, never a ladder step
OFF = {"spe_agent_tool_surface": "shell"}  # every other switch is off when falsy
DEFAULTS = yaml.safe_load((ANSIBLE / "inventory" / "group_vars" / "all.yml").read_text())


def levels() -> dict[int, dict]:
    found = {}
    for path in ANSIBLE.glob("instances/L*.example.yml"):
        m = re.fullmatch(r"L(\d+)\.example\.yml", path.name)
        assert m, f"unexpected ladder file {path.name}"
        found[int(m.group(1))] = yaml.safe_load(path.read_text()) or {}
    return found


def is_off(key, value) -> bool:
    return value == OFF[key] if key in OFF else not value


def test_levels_run_from_L0_without_gaps():
    assert sorted(levels()) == list(range(len(levels()))) and 0 in levels()


@pytest.mark.parametrize("key", LADDER + EVAL)
def test_every_switch_defaults_off(key):
    assert key in DEFAULTS, f"{key} missing from group_vars/all.yml"
    assert is_off(key, DEFAULTS[key]), f"{key} defaults to {DEFAULTS[key]!r}"


def test_plain_example_and_L0_set_no_hardening_switch():
    example = yaml.safe_load((ANSIBLE / "instances" / "example.yml").read_text())
    assert not set(example) & set(LADDER + EVAL)
    assert not set(levels()[0]) & set(LADDER)


def test_each_level_differs_from_the_one_before_by_exactly_its_switch():
    ladder = levels()
    for n in range(1, len(ladder)):
        before, now = ladder[n - 1], ladder[n]
        changed = {k for k in set(before) | set(now) if before.get(k) != now.get(k)}
        assert changed == {LADDER[n - 1]}, f"L{n} vs L{n - 1}: {sorted(changed)}"
        assert not is_off(LADDER[n - 1], now[LADDER[n - 1]]), f"L{n} sets {LADDER[n - 1]} to its off value"


def test_injections_on_and_identical_at_every_level():
    for n, level in levels().items():
        assert {k: level.get(k) for k in EVAL} == {k: True for k in EVAL}, f"L{n}"
        assert not [k for k in level if k.startswith("spe_injection")], f"L{n} changes the payload selection"
        assert level.get("spe_canary_registry_tokens") is True and level.get("spe_canary_flag_file") is True
        assert "gatk-hc-chr20" in level.get("spe_workflows", [])


def test_clean_overlay_turns_off_only_the_injections():
    # Spec part 06, *Clean and injected runs*: layered after a level file, it changes nothing but the three switches.
    clean = yaml.safe_load((ANSIBLE / "instances" / "no-injections.example.yml").read_text())
    assert clean == {k: False for k in INJECT}


def test_level_files_carry_no_host_identity():
    for n, level in levels().items():
        own = [k for k in level if k in ("spe_instance", "spe_seed", "spe_provision") or k.startswith("spe_existing_")]
        assert own == [], f"L{n} sets {own}: those belong in the private instance file"


def test_spe_apply_keeps_every_ladder_switch():
    # spe-apply re-renders from spe_local_vars; a switch missing there falls back to off,
    # and remove_orphans then drops the level's controls under a hardened hardening.json.
    harden = {k for k in DEFAULTS if k.startswith("spe_harden_")}
    assert harden <= set(LADDER)
    assert set(LADDER) <= set(DEFAULTS["spe_local_vars"])
