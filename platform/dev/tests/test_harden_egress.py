"""spe_harden_egress (L3): the sandbox reaches only the API host on 443."""
import os
import subprocess

import yaml

from ansible_render import ANSIBLE, GOLDEN, load_vars, render

ON = {"spe_harden_egress": True}
SCRIPT = ANSIBLE / "roles/egress/files/spe_egress.sh"
INSTANCE = ANSIBLE.parent / "instance"


def test_off_renders_todays_env():
    assert render("sandbox", "frontend.env.j2") == (GOLDEN / "frontend.env.L0").read_text()
    assert load_vars(spe_eval_sink=True)["spe_compose_overlays"] == ["eval-sink"]  # L2: no egress overlay


def test_on_sandbox_has_fixed_address_and_unroutable_dns():
    assert load_vars(spe_eval_sink=True, **ON)["spe_compose_overlays"] == ["eval-sink", "egress"]
    lines = set(render("sandbox", "frontend.env.j2", **ON).splitlines())
    assert {"SPE_COMPOSE_OVERLAYS=egress", "SPE_SANDBOX_SUBNET=172.30.250.0/24",
            "SPE_SANDBOX_IP=172.30.250.10", "SPE_SANDBOX_IP_RANGE=172.30.250.128/25",
            "SPE_SANDBOX_DNS=192.0.2.53"} <= lines
    c = yaml.safe_load((INSTANCE / "compose.egress.yml").read_text())
    # Only the sandbox: the agent keeps its route to the LLM endpoint.
    assert c["services"] == {"sandbox": {"networks": {"tools": {"ipv4_address": "${SPE_SANDBOX_IP}"}},
                                         "dns": ["${SPE_SANDBOX_DNS}"]}}
    assert c["networks"] == {"tools": {"ipam": {"config": [{"subnet": "${SPE_SANDBOX_SUBNET}",
                                                         "ip_range": "${SPE_SANDBOX_IP_RANGE}"}]}}}


def run(tmp_path, action, rc_check=1):
    log = tmp_path / "ipt.log"
    fake = tmp_path / "iptables"
    fake.write_text(f'#!/bin/sh\necho "$*" >> {log}\ncase "$1" in -C|-D) exit {rc_check};; esac\nexit 0\n')
    fake.chmod(0o755)
    env_file = tmp_path / "egress.env"
    env_file.write_text("SANDBOX_IP=172.30.250.10\nAPI_IP=10.0.2.245\nAPI_PORT=443\n")
    env = dict(os.environ, IPTABLES=str(fake), SPE_EGRESS_ENV=str(env_file))
    res = subprocess.run(["sh", str(SCRIPT), action], env=env, capture_output=True, text=True)
    return res, log.read_text().splitlines() if log.exists() else []


def test_apply_allows_replies_and_api_443_then_drops(tmp_path):
    res, calls = run(tmp_path, "apply")
    assert res.returncode == 0, res.stderr
    fwd = [c for c in calls if c.startswith("-A SPE-EGRESS ")]
    assert fwd == [
        "-A SPE-EGRESS -s 172.30.250.10/32 -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN",
        "-A SPE-EGRESS -s 172.30.250.10/32 -p tcp -m conntrack --ctorigdst 10.0.2.245 --ctorigdstport 443 -j RETURN",
        "-A SPE-EGRESS -s 172.30.250.10/32 -j DROP"]
    assert "-I DOCKER-USER 1 -j SPE-EGRESS" in calls and "-I INPUT 1 -j SPE-EGRESS-IN" in calls
    assert calls[-1] == "-I INPUT 1 -j SPE-EGRESS-IN"
    assert "-A SPE-EGRESS-IN -s 172.30.250.10/32 -j DROP" in calls


def test_apply_twice_adds_no_second_jump(tmp_path):
    _, calls = run(tmp_path, "apply", rc_check=0)  # -C finds the jumps already there
    assert not [c for c in calls if c.startswith("-I ")]


def test_remove_deletes_jumps_and_chains(tmp_path):
    res, calls = run(tmp_path, "remove")
    assert res.returncode == 0
    assert "-X SPE-EGRESS" in calls and "-X SPE-EGRESS-IN" in calls


def test_missing_parameters_fail(tmp_path):
    env = dict(os.environ, IPTABLES="true", SPE_EGRESS_ENV=str(tmp_path / "none"))
    assert subprocess.run(["sh", str(SCRIPT), "apply"], env=env, capture_output=True).returncode != 0


def test_status_fails_without_the_jumps(tmp_path):
    res, calls = run(tmp_path, "status", rc_check=1)  # -C: a jump is missing
    assert res.returncode != 0
    res, calls = run(tmp_path, "status", rc_check=0)
    assert res.returncode == 0 and "-C DOCKER-USER -j SPE-EGRESS" in calls and "-C INPUT -j SPE-EGRESS-IN" in calls
