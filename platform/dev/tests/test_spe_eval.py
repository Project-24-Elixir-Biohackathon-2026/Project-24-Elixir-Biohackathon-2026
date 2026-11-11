"""platform/instance/spe_eval.py: experiments, arms, the suite config, run id/reports layout and
the lock (experiments spec part 03, `docs/specs/2026-11-10-experiments-design/03-evaluation-in-
workspace.md`, decisions 7, 9 and 11). Arm and creation-time tests read the repository's own
`experiments/`/`mitigations/` files (the ladder), as `test_ladder_experiments.py` does, so they
exercise the real catalogue rather than a copy that could drift from it.
"""
import re
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "platform" / "instance"))
import spe_eval  # noqa: E402


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


# --- which experiment / arms ------------------------------------------------------------------

def test_load_experiment_reads_the_real_file():
    experiment = spe_eval.load_experiment("ladder-l2")
    assert experiment["parameters"]["experiment"] == "ladder-l2"
    assert experiment["experiment"]["mitigation"] == "L2"


def test_load_experiment_missing_file_is_a_config_error():
    with pytest.raises(spe_eval.ConfigError):
        spe_eval.load_experiment("no-such-experiment")


def test_load_local_vars_reads_instances_local_yml(tmp_path):
    instances = tmp_path / "platform" / "ansible" / "instances"
    instances.mkdir(parents=True)
    (instances / "local.yml").write_text("spe_experiment: ladder-l2\nspe_instance: t-01\n")
    local_vars = spe_eval.load_local_vars(tmp_path)
    assert local_vars == {"spe_experiment": "ladder-l2", "spe_instance": "t-01"}


def test_load_local_vars_missing_file_is_a_config_error(tmp_path):
    with pytest.raises(spe_eval.ConfigError, match="local re-apply"):
        spe_eval.load_local_vars(tmp_path)


def test_default_experiment_name_reads_spe_experiment():
    assert spe_eval.default_experiment_name({"spe_experiment": "ladder-l2"}) == "ladder-l2"


def test_default_experiment_name_missing_is_a_config_error():
    with pytest.raises(spe_eval.ConfigError, match="spe_experiment"):
        spe_eval.default_experiment_name({})


@pytest.mark.parametrize("name,arms", [
    ("ladder-l0", ("baseline",)),
    ("ladder-l1", ("baseline", "mitigated")),
    ("ladder-l2", ("baseline", "mitigated")),
    ("ladder-l3", ("baseline", "mitigated")),
])
def test_experiment_arms(name, arms):
    assert spe_eval.experiment_arms(spe_eval.load_experiment(name)) == arms


def test_arm_mitigations_ladder_l2():
    experiment = spe_eval.load_experiment("ladder-l2")
    assert spe_eval.arm_mitigations(experiment, "baseline") == ["L1"]
    assert spe_eval.arm_mitigations(experiment, "mitigated") == ["L1", "L2"]


def test_arm_mitigations_unknown_arm_raises():
    experiment = spe_eval.load_experiment("ladder-l0")  # one arm only
    with pytest.raises(ValueError, match="mitigated"):
        spe_eval.arm_mitigations(experiment, "mitigated")


# --- arm_vars (decision 9) ----------------------------------------------------------------------

def test_arm_vars_ladder_l2_baseline_is_l1_on_l2_l3_off():
    values = spe_eval.arm_vars(spe_eval.load_experiment("ladder-l2"), "baseline")
    assert values["spe_harden_trs_readonly"] is True       # L1 on
    assert values["spe_harden_data_tiers"] == []            # L2 off
    assert values["spe_harden_egress"] is False             # L3 off
    assert values["spe_mitigations"] == ["L1"]
    assert values["spe_experiment"] == "ladder-l2"


def test_arm_vars_ladder_l2_mitigated_is_l1_and_l2_on():
    values = spe_eval.arm_vars(spe_eval.load_experiment("ladder-l2"), "mitigated")
    assert values["spe_harden_trs_readonly"] is True
    assert values["spe_harden_data_tiers"] == ["ref", "genomes"]
    assert values["spe_harden_egress"] is False              # L3 still off: not in base or under test
    assert values["spe_mitigations"] == ["L1", "L2"]


def test_arm_vars_ladder_l0_one_arm_every_mitigation_off():
    values = spe_eval.arm_vars(spe_eval.load_experiment("ladder-l0"), "baseline")
    assert values["spe_harden_trs_readonly"] is False
    assert values["spe_harden_data_tiers"] == []
    assert values["spe_harden_egress"] is False
    assert values["spe_mitigations"] == []
    assert values["spe_experiment"] == "ladder-l0"


def test_arm_vars_mitigation_outside_the_experiment_is_off_in_both_arms():
    # ladder-l1 names only L1; L2 and L3 stay off in both arms, whatever a participant also
    # selected on the creation form (decision 9's acceptance): arm_vars never looks at the
    # running build at all, only at the experiment file and the mitigation catalogue.
    experiment = spe_eval.load_experiment("ladder-l1")
    for arm in spe_eval.experiment_arms(experiment):
        values = spe_eval.arm_vars(experiment, arm)
        assert values["spe_harden_data_tiers"] == []     # L2 off
        assert values["spe_harden_egress"] is False       # L3 off


def test_arm_vars_injection_switches_are_the_same_in_both_arms():
    experiment = spe_eval.load_experiment("ladder-l2")
    baseline = spe_eval.arm_vars(experiment, "baseline")
    mitigated = spe_eval.arm_vars(experiment, "mitigated")
    switches = ["spe_inject_trs_description", "spe_inject_drs_description", "spe_inject_workflow_comment"]
    for switch in switches:
        assert baseline[switch] is True   # ladder-l2 lists all three injections
        assert baseline[switch] == mitigated[switch]


def test_write_json_round_trips(tmp_path):
    values = {"spe_mitigations": ["L1"], "spe_harden_trs_readonly": True}
    path = spe_eval.write_json(values, tmp_path / "arm" / "vars.json")
    assert path.exists()
    import json
    assert json.loads(path.read_text()) == values


# --- creation-time check (decision 7) ------------------------------------------------------------

def matching_local_vars(experiment: dict) -> dict:
    """A `local.yml` that matches `experiment`'s `parameters`, `vars` and injection switches
    exactly (task 5 review item 2: every fixture's `spe_inject_*` switch persists for every build,
    not only the ones an experiment names)."""
    params = experiment["parameters"]
    all_canary_types = ["registry_tokens", "honeypot_files", "vcf_variants", "flag_file",
                         "drs_metadata", "trs_descriptions", "workflow_comments", "service_info"]
    injection_ids = (experiment.get("experiment") or {}).get("injections") or []
    local_vars = {
        "spe_samples": params["samples"],
        "spe_tiers": params["tiers"],
        "spe_workflows": params["workflows"],
        "spe_run_smoke_test": params["smoke_test"],
        **{f"spe_canary_{t}": (t in params["canaries"]) for t in all_canary_types},
        **spe_eval.injections_schema.switches(injection_ids),
        **(experiment.get("vars") or {}),
    }
    return local_vars


def test_check_creation_time_no_mismatch_when_the_build_matches():
    experiment = spe_eval.load_experiment("ladder-l0")
    assert spe_eval.check_creation_time(experiment, matching_local_vars(experiment)) == []
    spe_eval.check_build_matches(experiment, matching_local_vars(experiment))  # does not raise


def test_check_creation_time_names_every_differing_key():
    experiment = spe_eval.load_experiment("ladder-l0")
    local_vars = matching_local_vars(experiment)
    local_vars["spe_tiers"] = ["ref"]                       # a parameter key, differs
    local_vars["spe_canary_flag_file"] = not local_vars["spe_canary_flag_file"]  # a canaries key, differs
    local_vars["spe_eval_sink"] = not local_vars["spe_eval_sink"]  # a vars key, differs
    mismatches = spe_eval.check_creation_time(experiment, local_vars)
    assert mismatches == sorted(["spe_tiers", "spe_canary_flag_file", "spe_eval_sink"])


def test_check_creation_time_list_params_are_order_insensitive():
    # task 3 review, minor 1: spe_samples/spe_tiers/spe_workflows differing only in order (a build
    # whose form held the experiment's own set in a different order) is not a false mismatch.
    experiment = spe_eval.load_experiment("ladder-l0")
    local_vars = matching_local_vars(experiment)
    local_vars["spe_tiers"] = list(reversed(local_vars["spe_tiers"]))
    local_vars["spe_workflows"] = list(reversed(local_vars["spe_workflows"]))
    assert local_vars["spe_tiers"] != experiment["parameters"]["tiers"]  # reordered, not equal
    assert spe_eval.check_creation_time(experiment, local_vars) == []
    spe_eval.check_build_matches(experiment, local_vars)  # does not raise


def test_check_creation_time_skips_flavor_which_local_yml_never_holds():
    # spe_flavor is VM sizing, done once at creation: it is not in spe_local_vars, so a local.yml
    # with no such key at all must not be reported as a mismatch.
    experiment = spe_eval.load_experiment("ladder-l0")
    assert "flavor" in experiment["parameters"]
    local_vars = matching_local_vars(experiment)
    assert "spe_flavor" not in local_vars
    assert spe_eval.check_creation_time(experiment, local_vars) == []


def test_check_creation_time_excludes_experiment_and_mitigations():
    experiment = spe_eval.load_experiment("ladder-l2")
    local_vars = matching_local_vars(experiment)
    local_vars["spe_experiment"] = "some-other-experiment"
    local_vars["spe_mitigations"] = ["L3"]
    assert spe_eval.check_creation_time(experiment, local_vars) == []


def test_check_build_matches_raises_config_error_naming_the_keys():
    experiment = spe_eval.load_experiment("ladder-l0")
    local_vars = matching_local_vars(experiment)
    local_vars["spe_tiers"] = ["ref"]
    with pytest.raises(spe_eval.ConfigError, match="spe_tiers"):
        spe_eval.check_build_matches(experiment, local_vars)


def test_check_creation_time_flags_an_injection_switch_the_build_never_planted():
    # ladder-l0 names all three injections: a build with one of them off (planted differently
    # than the experiment names) must refuse (task 5 review item 2).
    experiment = spe_eval.load_experiment("ladder-l0")
    local_vars = matching_local_vars(experiment)
    local_vars["spe_inject_drs_description"] = False
    mismatches = spe_eval.check_creation_time(experiment, local_vars)
    assert mismatches == ["spe_inject_drs_description"]
    with pytest.raises(spe_eval.ConfigError, match="spe_inject_drs_description"):
        spe_eval.check_build_matches(experiment, local_vars)


def test_check_creation_time_flags_an_injection_switch_the_build_planted_that_the_experiment_does_not_name():
    experiment = spe_eval.load_experiment("ladder-l0")
    local_vars = matching_local_vars(experiment)
    local_vars["spe_inject_trs_description"] = False
    local_vars["spe_inject_drs_description"] = False
    local_vars["spe_inject_workflow_comment"] = False
    mismatches = spe_eval.check_creation_time(experiment, local_vars)
    assert mismatches == sorted(["spe_inject_trs_description", "spe_inject_drs_description",
                                  "spe_inject_workflow_comment"])


def test_check_creation_time_treats_a_missing_injection_switch_as_false():
    # A local.yml from before this comparison existed: no spe_inject_* key at all is "off", the
    # Ansible default, not "unknown" (not a false mismatch for an experiment with no injections).
    experiment = spe_eval.load_experiment("ladder-l0")  # injections: [registry-preflight, drs-integrity, workflow-preflight]
    local_vars = {k: v for k, v in matching_local_vars(experiment).items() if not k.startswith("spe_inject_")}
    mismatches = spe_eval.check_creation_time(experiment, local_vars)
    assert mismatches == sorted(["spe_inject_trs_description", "spe_inject_drs_description",
                                  "spe_inject_workflow_comment"])


# --- the suite (R1) --------------------------------------------------------------------------

def test_suite_config_with_no_tests_returns_agent_yaml_unchanged():
    experiment = spe_eval.load_experiment("ladder-l0")  # tests: []
    path = spe_eval.suite_config(experiment, Path("/does/not/matter"))
    assert path == REPO / "platform" / "promptfoo-evals" / "agent.yaml"
    assert path.exists()


def test_suite_config_with_named_tests_plus_utility_group(tmp_path):
    experiment = {"experiment": {"tests": ["summarise-workflows"], "injections": []}}
    out = spe_eval.suite_config(experiment, tmp_path)
    assert out == tmp_path / "suite.yaml"
    config = load_yaml(out)
    ids = [t["metadata"]["id"] for t in config["tests"]]
    assert ids[0] == "summarise-workflows"          # the named test first
    assert "list-workflows" in ids                   # a utility test, not named, pulled in
    assert "inventory-drs" in ids                     # another utility test
    # Every utility test is present (R1: "plus every test of the utility group").
    utility_file = REPO / "platform" / "promptfoo-evals" / "tests" / "utility.yaml"
    utility_cases = yaml.safe_load(utility_file.read_text())
    utility_ids = {c["metadata"]["id"] for c in utility_cases}
    assert utility_ids <= set(ids)
    # Paths made absolute, so the suite runs from any directory (R1).
    assert config["providers"][0]["id"] == f"file://{REPO / 'platform/promptfoo-evals/agui_provider.py'}"


def test_suite_config_unknown_test_id_is_a_config_error(tmp_path):
    experiment = {"experiment": {"tests": ["no-such-test"]}}
    with pytest.raises(spe_eval.ConfigError, match="no-such-test"):
        spe_eval.suite_config(experiment, tmp_path)


# --- run id, home, reports layout ---------------------------------------------------------------

def test_run_id_format():
    assert re.fullmatch(r"\d{8}T\d{6}Z", spe_eval.run_id())


def test_spe_eval_home_and_reports_dir(tmp_path):
    home = spe_eval.spe_eval_home(tmp_path)
    assert home == tmp_path / "spe-eval"
    reports = spe_eval.reports_dir("ladder-l2", "20261110T120000Z", "baseline", tmp_path)
    assert reports == tmp_path / "spe-eval" / "reports" / "ladder-l2" / "20261110T120000Z" / "baseline"


# --- promptfoo_env (task 5 review item 1) --------------------------------------------------------

def write_hosts_yml(handoff_dir: Path, **fields) -> Path:
    handoff_dir.mkdir(parents=True, exist_ok=True)
    path = handoff_dir / "hosts.yml"
    path.write_text(yaml.safe_dump(fields))
    return path


def test_promptfoo_env_sets_agent_url_from_hosts_yml(tmp_path):
    handoff = tmp_path / "handoff"
    write_hosts_yml(handoff, agent_url="http://127.0.0.1:8100/agent", provision="existing")
    env = spe_eval.promptfoo_env(handoff, tmp_path / "promptfoo", tmp_path / "progress.jsonl", base_env={})
    assert env["SPE_AGENT_URL"] == "http://127.0.0.1:8100/agent"
    assert env["SPE_AGENT_API_KEY_FILE"] == str(handoff / "agent_api_key")
    assert env["SPE_LLM_API_KEY_FILE"] == str(handoff / "llm_api_key")
    assert env["PROMPTFOO_DISABLE_TELEMETRY"] == "1"
    assert env["PROMPTFOO_DISABLE_SHARING"] == "1"
    assert env["PROMPTFOO_DISABLE_UPDATE"] == "1"
    assert env["PROMPTFOO_CONFIG_DIR"] == str(tmp_path / "promptfoo")
    assert env["SPE_EVAL_PROGRESS"] == str(tmp_path / "progress.jsonl")


def test_promptfoo_env_no_agent_url_when_hosts_yml_has_none(tmp_path):
    # A build with no agui frontend: hosts.yml has no agent_url key at all (vm_handoff.yml).
    handoff = tmp_path / "handoff"
    write_hosts_yml(handoff, provision="existing")
    env = spe_eval.promptfoo_env(handoff, tmp_path / "promptfoo", tmp_path / "progress.jsonl", base_env={})
    assert "SPE_AGENT_URL" not in env


def test_promptfoo_env_no_hosts_yml_at_all(tmp_path):
    handoff = tmp_path / "handoff"
    handoff.mkdir()
    env = spe_eval.promptfoo_env(handoff, tmp_path / "promptfoo", tmp_path / "progress.jsonl", base_env={})
    assert "SPE_AGENT_URL" not in env
    assert env["SPE_AGENT_API_KEY_FILE"] == str(handoff / "agent_api_key")


def test_promptfoo_env_puts_usr_local_bin_first_on_path(tmp_path):
    handoff = tmp_path / "handoff"
    handoff.mkdir()
    env = spe_eval.promptfoo_env(handoff, tmp_path / "promptfoo", tmp_path / "progress.jsonl",
                                  base_env={"PATH": "/usr/bin:/bin"})
    assert env["PATH"] == "/usr/local/bin:/usr/bin:/bin"


def test_promptfoo_env_does_not_duplicate_usr_local_bin_already_on_path(tmp_path):
    handoff = tmp_path / "handoff"
    handoff.mkdir()
    env = spe_eval.promptfoo_env(handoff, tmp_path / "promptfoo", tmp_path / "progress.jsonl",
                                  base_env={"PATH": "/usr/local/bin:/usr/bin"})
    assert env["PATH"] == "/usr/local/bin:/usr/bin"


def test_promptfoo_env_never_reads_the_key_files_themselves(tmp_path):
    # No key value ever printed (task 5 review item 1): promptfoo_env only ever builds paths, it
    # never opens agent_api_key or llm_api_key, so a secret in either never passes through this
    # function at all, let alone into a string that could be logged.
    handoff = tmp_path / "handoff"
    handoff.mkdir()
    (handoff / "agent_api_key").write_text("super-secret-agent-key\n")
    (handoff / "llm_api_key").write_text("super-secret-llm-key\n")
    env = spe_eval.promptfoo_env(handoff, tmp_path / "promptfoo", tmp_path / "progress.jsonl", base_env={})
    assert "super-secret-agent-key" not in repr(env)
    assert "super-secret-llm-key" not in repr(env)


def test_promptfoo_env_drops_an_inherited_agent_and_llm_key(tmp_path):
    # task 5 review, Minor 1: asserts._secret prefers the bare SPE_AGENT_API_KEY/SPE_LLM_API_KEY
    # over the _FILE variant, so a caller's shell still carrying either (the controller's own docs
    # tell an operator to export SPE_LLM_API_KEY by hand) must not override the VM hand-off.
    handoff = tmp_path / "handoff"
    handoff.mkdir()
    env = spe_eval.promptfoo_env(handoff, tmp_path / "promptfoo", tmp_path / "progress.jsonl",
                                  base_env={"SPE_AGENT_API_KEY": "stale-agent-key",
                                            "SPE_LLM_API_KEY": "stale-llm-key"})
    assert "SPE_AGENT_API_KEY" not in env
    assert "SPE_LLM_API_KEY" not in env
    assert env["SPE_AGENT_API_KEY_FILE"] == str(handoff / "agent_api_key")


def test_promptfoo_env_drops_a_stale_inherited_agent_url_when_hosts_yml_has_none(tmp_path):
    handoff = tmp_path / "handoff"
    write_hosts_yml(handoff, provision="existing")  # no agent_url: no agui frontend
    env = spe_eval.promptfoo_env(handoff, tmp_path / "promptfoo", tmp_path / "progress.jsonl",
                                  base_env={"SPE_AGENT_URL": "http://127.0.0.1:9999/agent"})
    assert "SPE_AGENT_URL" not in env


def test_promptfoo_env_replaces_a_stale_inherited_agent_url_when_hosts_yml_has_one(tmp_path):
    handoff = tmp_path / "handoff"
    write_hosts_yml(handoff, agent_url="http://127.0.0.1:8100/agent")
    env = spe_eval.promptfoo_env(handoff, tmp_path / "promptfoo", tmp_path / "progress.jsonl",
                                  base_env={"SPE_AGENT_URL": "http://127.0.0.1:9999/agent"})
    assert env["SPE_AGENT_URL"] == "http://127.0.0.1:8100/agent"


def test_promptfoo_env_drops_an_inherited_spe_handoff_dir(tmp_path):
    # SPE_HANDOFF_DIR is run.sh's own controller-tunnel variable (handoff.handoff_dir()); a stale
    # one inherited from the caller's shell must not leak into run.sh's own environment either.
    handoff = tmp_path / "handoff"
    handoff.mkdir()
    env = spe_eval.promptfoo_env(handoff, tmp_path / "promptfoo", tmp_path / "progress.jsonl",
                                  base_env={"SPE_HANDOFF_DIR": "/some/other/path"})
    assert "SPE_HANDOFF_DIR" not in env


# --- the lock (decision 11) -------------------------------------------------------------------

def test_lock_holder_is_none_without_a_lock_file(tmp_path):
    assert spe_eval.Lock(tmp_path / "lock").holder() is None


def test_lock_second_acquire_refuses_naming_the_holder(tmp_path):
    path = tmp_path / "lock"
    first = spe_eval.Lock(path)
    first.acquire("20261110T120000Z")
    try:
        second = spe_eval.Lock(path)
        with pytest.raises(spe_eval.LockHeld) as exc_info:
            second.acquire("20261110T130000Z")
        assert exc_info.value.token == "20261110T120000Z"
        assert "20261110T120000Z" in str(exc_info.value)
    finally:
        first.release()


def test_lock_release_lets_another_acquire(tmp_path):
    path = tmp_path / "lock"
    first = spe_eval.Lock(path)
    first.acquire("tok-1")
    first.release()
    second = spe_eval.Lock(path)
    second.acquire("tok-2")
    assert second.holder() == "tok-2"
    second.release()


def test_lock_holder_reports_a_stale_token_as_free(tmp_path):
    # task 5 review, Important 4a: a process that died before release() (e.g. SIGKILLed) leaves
    # its token in the file, but the flock itself goes with the process, so holder() must call
    # this "free", not "held by that dead token forever".
    path = tmp_path / "lock"
    path.write_text("20261111T000000Z")
    assert spe_eval.Lock(path).holder() is None
    # a later acquire (as if from a fresh process) still works: the file is genuinely unheld.
    lock = spe_eval.Lock(path)
    lock.acquire("20261111T010000Z")
    try:
        assert lock.holder() == "20261111T010000Z"
    finally:
        lock.release()


def test_lock_holder_reports_a_genuinely_held_lock(tmp_path):
    path = tmp_path / "lock"
    held = spe_eval.Lock(path)
    held.acquire("tok-held")
    try:
        assert spe_eval.Lock(path).holder() == "tok-held"
    finally:
        held.release()


def test_lock_acquire_rides_out_a_momentary_probe(tmp_path):
    # re-review N3: holder()'s probe (status, wait polling) takes the free lock for an instant;
    # an acquire that lands in that instant retries instead of refusing.
    import fcntl
    import os
    import threading

    path = tmp_path / "lock"
    path.write_text("")
    fd = os.open(path, os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    timer = threading.Timer(0.15, lambda: (fcntl.flock(fd, fcntl.LOCK_UN), os.close(fd)))
    timer.start()
    lock = spe_eval.Lock(path)
    try:
        lock.acquire("tok-after-probe")
        assert lock.holder() == "tok-after-probe"
    finally:
        timer.join()
        lock.release()
