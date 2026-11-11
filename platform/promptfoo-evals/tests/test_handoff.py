"""Hand-off loaders on synthetic hand-off directories (conftest.py). No instance, no real canaries."""
import json

import pytest

import handoff
from conftest import CANARIES, ENTRY_SHAPE, TOKENS, hardening, hosts, write_hosts


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


def test_read_hosts_reads_a_list_of_scalars(tmp_path):
    # The handoff role writes spe_frontends as a block list, and an empty list as [] (to_nice_yaml).
    write_hosts(tmp_path, hosts(frontends=["agui", "openwebui"], none=[]))
    record = handoff.read_hosts(tmp_path)
    assert record["frontends"] == ["agui", "openwebui"]
    assert record["none"] == []
    assert record["instance"] == "ladder-l0"


@pytest.mark.parametrize("text", ["a:\n  b: c\n", "- a\n", "a: [1, 2]\n", "a: 'open\n", "novalue\n",
                                  "a: b\n- c\n", "a:\n- [1]\n", "a:\n-   - b\n"])
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
    {"restore_seconds": "61"}, {"injections": None}, {"injections": "yes"},
    # Review Fix round 1: injections not in (True, False, "mixed") let 1 == True, 0 == False, 1.0 == True
    # through (Python equality, not identity); isinstance(..., bool) or == "mixed" does not.
    {"injections": 1}, {"injections": 0}, {"injections": 1.0}])
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


def test_hardening_accepts_mixed_injections(handoff_dir):
    # R4: an experiment's arm that plants only some fixtures; check_hardening alone accepts it
    # (condition(), the ladder's own route, still refuses it: test_mixed_is_refused).
    (handoff_dir / "hardening.json").write_text(json.dumps(hardening(injections="mixed")))
    assert handoff.load_hardening(handoff_dir)["injections"] == "mixed"


def test_hardening_accepts_mitigations_and_experiment(handoff_dir):
    record = hardening(mitigations=["L1", "trs-guard"], experiment="trs-guard")
    (handoff_dir / "hardening.json").write_text(json.dumps(record))
    loaded = handoff.load_hardening(handoff_dir)
    assert loaded["mitigations"] == ["L1", "trs-guard"] and loaded["experiment"] == "trs-guard"


def test_hardening_accepts_the_spe_experiments_defaults(handoff_dir):
    # platform/ansible/README.md: a spe_experiments build with no experiment selected writes
    # mitigations: [] and experiment: "", not absent.
    record = hardening(mitigations=[], experiment="")
    (handoff_dir / "hardening.json").write_text(json.dumps(record))
    loaded = handoff.load_hardening(handoff_dir)
    assert loaded["mitigations"] == [] and loaded["experiment"] == ""


@pytest.mark.parametrize("change", [{"mitigations": "L1"}, {"mitigations": [1]}, {"mitigations": [""]},
                                     {"experiment": 1}, {"experiment": True}])
def test_malformed_mitigations_or_experiment(handoff_dir, change):
    (handoff_dir / "hardening.json").write_text(json.dumps(hardening(**change)))
    with pytest.raises(handoff.ConfigError, match="hardening.json"):
        handoff.load_hardening(handoff_dir)


def test_mitigation_probes(repo_root):
    mitigations = repo_root / "mitigations"
    mitigations.mkdir(parents=True)
    (mitigations / "trs-guard.yml").write_text("id: trs-guard\nname: x\nprobes: [trs-write, wes-inline]\n")
    (mitigations / "none.yml").write_text("id: none\nprobes: []\n")
    assert handoff.mitigation_probes("trs-guard", repo_root) == frozenset({"trs-write", "wes-inline"})
    assert handoff.mitigation_probes("none", repo_root) == frozenset()


def test_mitigation_probes_reads_the_real_ladder_files():
    # Sanity check against the repository's own mitigations/*.yml, with the real REPO_ROOT.
    assert handoff.mitigation_probes("L1") == frozenset({"trs-write", "wes-inline", "e2e-exploit"})


@pytest.mark.parametrize("mitigation_id", ["nope", "../../etc/passwd", "L1/../../etc"])
def test_mitigation_probes_unknown_or_unsafe_id(repo_root, mitigation_id):
    with pytest.raises(handoff.ConfigError):
        handoff.mitigation_probes(mitigation_id, repo_root)


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


# --- conditions: clean and injected builds of one level (spec part 06, *Clean and injected runs*) ---
def write_fixtures(repo_root):
    # The catalogue's shape (slice 4, catalog/injections/fixtures.json): only canary_file is read here.
    path = repo_root / handoff.FIXTURES
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"fixtures": [{"id": i, "canary_file": e[2]} for i, e in ENTRY_SHAPE.items()]}))


def make_clean(directory, manifest_file=True):
    (directory / "hardening.json").write_text(json.dumps(hardening(injections=False)))
    if manifest_file:
        (directory / "injections.json").write_text(json.dumps({"schema_version": 1, "injections": []}))
    else:
        (directory / "injections.json").unlink()


def test_condition_injected(handoff_dir, repo_root):
    assert handoff.condition(handoff_dir, repo_root) == "injected"


@pytest.mark.parametrize("manifest_file", [True, False])
def test_condition_clean(handoff_dir, repo_root, manifest_file):
    write_fixtures(repo_root)
    make_clean(handoff_dir, manifest_file)
    assert handoff.condition(handoff_dir, repo_root) == "clean"


def test_injected_without_placements_is_refused(handoff_dir, repo_root):
    (handoff_dir / "injections.json").write_text(json.dumps({"schema_version": 1, "injections": []}))
    with pytest.raises(handoff.ManifestError, match="lists no injection"):
        handoff.condition(handoff_dir, repo_root)


def test_clean_with_placements_is_refused(handoff_dir, repo_root):
    write_fixtures(repo_root)
    (handoff_dir / "hardening.json").write_text(json.dumps(hardening(injections=False)))
    with pytest.raises(handoff.ManifestError, match="lists injections"):
        handoff.condition(handoff_dir, repo_root)


def test_mixed_is_refused(handoff_dir, repo_root):
    # check_hardening now accepts "mixed" (an experiment's arm, R4); condition() still refuses it
    # by default (allow_mixed=False): the ladder's own route only ever builds clean or fully injected.
    (handoff_dir / "hardening.json").write_text(json.dumps(hardening(injections="mixed")))
    with pytest.raises(handoff.ConfigError, match="not a ladder condition"):
        handoff.condition(handoff_dir, repo_root)


def test_mixed_is_accepted_with_allow_mixed(handoff_dir, repo_root):
    # fix round 1, cross-task gap: spe-eval run on an experiment naming only some of the
    # catalogue's injections (run.sh's --suite/--reports-dir/--description path) passes
    # allow_mixed=True; the result is "injected", exactly as for injections: true, since
    # handoff_dir's own injections.json already lists placements.
    (handoff_dir / "hardening.json").write_text(json.dumps(hardening(injections="mixed")))
    assert handoff.condition(handoff_dir, repo_root, allow_mixed=True) == "injected"


def test_mixed_with_allow_mixed_and_no_placements_is_still_refused(handoff_dir, repo_root):
    (handoff_dir / "hardening.json").write_text(json.dumps(hardening(injections="mixed")))
    (handoff_dir / "injections.json").write_text(json.dumps({"schema_version": 1, "injections": []}))
    with pytest.raises(handoff.ManifestError, match="lists no injection"):
        handoff.condition(handoff_dir, repo_root, allow_mixed=True)


def test_clean_build_without_a_target_canary_is_refused(handoff_dir, repo_root):
    # Matched builds: removing the injections must not remove a target file or its canary.
    write_fixtures(repo_root)
    make_clean(handoff_dir)
    record = json.loads((handoff_dir / "canaries.json").read_text())
    record["tokens"] = [t for t in record["tokens"] if t["type"] != "flag-file"]
    (handoff_dir / "canaries.json").write_text(json.dumps(record))
    with pytest.raises(handoff.ConfigError, match="research_DO_NOT_LEAK") as refused:
        handoff.condition(handoff_dir, repo_root)
    assert not [t for t in TOKENS if t in str(refused.value)]


def test_canaries_digest_ignores_order_and_time_but_not_tokens(handoff_dir, tmp_path):
    digest = handoff.canaries_digest(handoff_dir)
    assert len(digest) == 64 and not [t for t in TOKENS if t in digest]
    record = json.loads((handoff_dir / "canaries.json").read_text())
    other = tmp_path / "other"
    other.mkdir()
    (other / "canaries.json").write_text(json.dumps(
        {**record, "generated_at": "2026-11-09T00:00:00Z", "tokens": record["tokens"][::-1]}))
    assert handoff.canaries_digest(other) == digest
    (other / "canaries.json").write_text(json.dumps(
        {**record, "tokens": [{**record["tokens"][0], "token": "Ngo"}, *record["tokens"][1:]]}))
    assert handoff.canaries_digest(other) != digest
