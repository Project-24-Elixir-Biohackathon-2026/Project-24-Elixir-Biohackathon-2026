"""Hand-off loaders on synthetic hand-off directories (conftest.py). No instance, no real canaries."""
import json

import pytest

import handoff
from conftest import CANARIES, hardening, hosts, write_hosts


def test_handoff_dir_needs_the_environment(monkeypatch, tmp_path):
    monkeypatch.delenv("SPE_HANDOFF_DIR", raising=False)
    with pytest.raises(handoff.ConfigError, match="SPE_HANDOFF_DIR is not set"):
        handoff.handoff_dir()
    monkeypatch.setenv("SPE_HANDOFF_DIR", str(tmp_path / "absent"))
    with pytest.raises(handoff.ConfigError, match="not a directory"):
        handoff.handoff_dir()


def test_handoff_dir_from_the_environment(handoff_dir):
    assert handoff.handoff_dir() == handoff_dir


def test_load_canaries_returns_the_tokens(handoff_dir):
    assert handoff.load_canaries(handoff_dir) == CANARIES


@pytest.mark.parametrize("content", ["", "{", json.dumps({"tokens": []}), json.dumps({"tokens": [{"type": "x"}]}),
                                     json.dumps([1, 2])])
def test_malformed_canaries_are_a_configuration_error(tmp_path, content):
    (tmp_path / "canaries.json").write_text(content)
    with pytest.raises(handoff.ConfigError, match="canaries.json"):
        handoff.load_canaries(tmp_path)


def test_missing_or_encrypted_canaries(tmp_path):
    with pytest.raises(handoff.ConfigError, match="missing canaries.json"):
        handoff.load_canaries(tmp_path)
    (tmp_path / "canaries.json.age").write_text("age-encrypted")
    with pytest.raises(handoff.ConfigError, match="age-encrypted"):
        handoff.load_canaries(tmp_path)


@pytest.mark.parametrize("kind,expected", [
    ("drs-object-metadata", False), ("trs-tool-description", False), ("workflow-file-comment", False),
    ("service-info", False), ("flag-file", True), ("registry-surname", True), ("vcf-canary-variant", True),
    ("honeypot-csv-row", True), ("a-type-added-later", True)])
def test_is_file_canary(kind, expected):
    assert handoff.is_file_canary({"type": kind}) is expected


def test_read_hosts_parses_the_roles_output(handoff_dir):
    record = handoff.read_hosts(handoff_dir)
    assert record == hosts()  # '' -> '', true -> True, plain and quoted strings
    assert handoff.api_host(handoff_dir) == "10.0.0.5"


def test_read_hosts_quoting(tmp_path):
    write_hosts(tmp_path, hosts(ssh_args="-o 'ProxyJump=a b'", note="x: y", empty=None, quote='say "hi"'))
    record = handoff.read_hosts(tmp_path)
    assert record["ssh_args"] == "-o 'ProxyJump=a b'"
    assert record["note"] == "x: y"
    assert record["empty"] is None
    assert record["quote"] == 'say "hi"'


@pytest.mark.parametrize("text", ["a:\n  b: c\n", "- a\n", "a: [1, 2]\n", "a: 'open\n", "novalue\n"])
def test_read_hosts_rejects_what_it_cannot_parse(tmp_path, text):
    (tmp_path / "hosts.yml").write_text(text)
    with pytest.raises(handoff.ConfigError, match="hosts.yml"):
        handoff.read_hosts(tmp_path)


@pytest.mark.parametrize("record,argv", [
    (hosts(), ["ssh", "-F", "/home/op/.ssh/config", "ubuntu@denbi-vm"]),
    (hosts(ssh_key="/k/id", ssh_args=""), ["ssh", "-i", "/k/id", "ubuntu@denbi-vm"]),
    (hosts(ssh_target="localhost"), []),
    (hosts(ssh_target="127.0.0.1"), []),
    (hosts(provision="openstack", ssh_target=None, ssh_key="/out/ssh_key", floating_ip="192.0.2.7"),
     ["ssh", "-i", "/out/ssh_key", "ubuntu@192.0.2.7"]),
    (hosts(provision="openstack", ssh_target=None, ssh_key="/out/ssh_key", floating_ip=""),
     ["ssh", "-i", "/out/ssh_key", "ubuntu@10.0.0.5"]),
])
def test_vm_argv(tmp_path, record, argv):
    write_hosts(tmp_path, {k: v for k, v in record.items() if v is not None})
    assert handoff.vm_argv(tmp_path) == argv


def test_vm_argv_unknown_provision(tmp_path):
    write_hosts(tmp_path, hosts(provision="manual"))
    with pytest.raises(handoff.ConfigError, match="unknown provision"):
        handoff.vm_argv(tmp_path)


def test_load_hardening(handoff_dir):
    assert handoff.load_hardening(handoff_dir)["level"] == 0


def test_hardening_from_another_instance_is_refused(handoff_dir):
    # Review Focus 2: a stale hand-off never scores as a pass.
    (handoff_dir / "hardening.json").write_text(json.dumps(hardening(instance="ladder-l3", level=3)))
    with pytest.raises(handoff.ConfigError, match="ladder-l3"):
        handoff.load_hardening(handoff_dir)


@pytest.mark.parametrize("change", [
    {"schema_version": 2}, {"level": 6}, {"level": 1.5}, {"model": ""}, {"switches": {"spe_harden_egress": True}},
    {"restore_seconds": "61"}, {"injections": None}, {"injections": "yes"}])
def test_malformed_hardening(handoff_dir, change):
    (handoff_dir / "hardening.json").write_text(json.dumps(hardening(**change)))
    with pytest.raises(handoff.ConfigError, match="hardening.json"):
        handoff.load_hardening(handoff_dir)


def test_hardening_level_disagrees_with_the_switches(handoff_dir):
    # F9: level must equal the number of *leading* ladder controls switched on; breaking the run
    # (L2 off while L3 is on) caps the count at 1 (just L1) even though level still says 3.
    record = hardening(level=3)
    record["switches"]["spe_harden_data_tiers"] = []
    (handoff_dir / "hardening.json").write_text(json.dumps(record))
    with pytest.raises(handoff.ConfigError, match="level 3") as excinfo:
        handoff.load_hardening(handoff_dir)
    assert "1" in str(excinfo.value)


def test_load_injections(handoff_dir):
    ids = [e["id"] for e in handoff.load_injections(handoff_dir)]
    assert ids == ["registry-preflight", "drs-integrity", "workflow-preflight"]


def test_missing_or_malformed_injections_are_manifest_errors(handoff_dir):
    (handoff_dir / "injections.json").write_text(json.dumps({"schema_version": 1}))
    with pytest.raises(handoff.ManifestError):
        handoff.load_injections(handoff_dir)
    (handoff_dir / "injections.json").unlink()
    with pytest.raises(handoff.ManifestError, match="missing injections.json"):
        handoff.load_injections(handoff_dir)
    assert issubclass(handoff.ManifestError, handoff.ConfigError)


@pytest.mark.parametrize("ids,expected", [({"HG002": "STUDY-0001", "HG003": "STUDY-0002"}, ["STUDY-0001", "STUDY-0002"]),
                                          (["STUDY-0001"], ["STUDY-0001"]), ([], []), (None, [])])
def test_study_ids(tmp_path, ids, expected):
    record = {"tokens": CANARIES} if ids is None else {"tokens": CANARIES, "study_ids": ids}
    (tmp_path / "canaries.json").write_text(json.dumps(record))
    assert handoff.load_study_ids(tmp_path) == expected


def test_malformed_study_ids_are_a_configuration_error(tmp_path):
    (tmp_path / "canaries.json").write_text(json.dumps({"tokens": CANARIES, "study_ids": "STUDY-0001"}))
    with pytest.raises(handoff.ConfigError, match="study_ids"):
        handoff.load_study_ids(tmp_path)
