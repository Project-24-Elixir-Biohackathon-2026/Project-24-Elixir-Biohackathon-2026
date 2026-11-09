"""spe_harden_data_tiers (L2): WESkit services and workflow containers see only the listed tiers."""
import importlib.util
import json

import yaml

from ansible_render import ANSIBLE, GOLDEN, environment, load_vars, render

WESKIT = ["rest", "submission_worker", "monitoring_worker", "monitoring_scheduler"]
ON = {"spe_harden_data_tiers": ["ref", "genomes"]}


def compose(**sw):
    return yaml.safe_load(render("workflow_stack", "compose.install.yaml.j2", **sw))


def data_volumes(svc):
    return [v for v in svc["volumes"] if ":/drs-data" in v or ":/data-share" in v]


def test_off_renders_todays_compose():
    golden = (GOLDEN / "compose.install.L0.yaml").read_text()
    assert render("workflow_stack", "compose.install.yaml.j2") == golden
    assert render("workflow_stack", "compose.install.yaml.j2", spe_harden_data_tiers=[]) == golden


def test_tier_dirs_match_drs_registration():
    spec = importlib.util.spec_from_file_location("drs_register", ANSIBLE / "roles/drs_register/files/drs_register.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert {k: [v] for k, v in load_vars()["spe_tier_dirs"].items()} == mod.TIER_DIRS


def test_on_weskit_services_mount_only_listed_tiers():
    c = compose(**ON)
    want = ["/data-share/ref:/drs-data/ref:ro", "/data-share/ref:/data-share/ref:ro",
            "/data-share/sensitive/genomes:/drs-data/sensitive/genomes:ro",
            "/data-share/sensitive/genomes:/data-share/sensitive/genomes:ro"]
    for name in WESKIT:
        svc = c["services"][name]
        assert data_volumes(svc) == want, name
        mounts = json.loads(svc["environment"]["WESKIT_CONTAINER_MOUNTS"])
        assert sorted(m["target"] for m in mounts) == sorted(
            ["/drs-data/ref", "/data-share/ref", "/drs-data/sensitive/genomes", "/data-share/sensitive/genomes"])
        assert all(m["mode"] == "ro" and m["source"] == m["target"] for m in mounts)
        assert not [v for v in svc["volumes"] if "registry" in v or "secret" in v], name


def test_on_drs_filer_keeps_the_full_mount():
    assert "/data-share:/drs-data:ro" in compose(**ON)["services"]["drs-filer"]["volumes"]


def smoke_drs_uri(**sw):
    tasks = yaml.safe_load((ANSIBLE / "roles/verify/tasks/main.yml").read_text())
    task = next(t for t in tasks if t.get("name") == "Smoke run through WES with a DRS input")
    expr = task["ansible.builtin.command"]["argv"][-1]
    inv = [{"path": "sensitive/secret/f", "tier": "secret", "drs_uri": "drs://h/secret"},
           {"path": "PROVENANCE.md", "tier": "root", "drs_uri": "drs://h/root"},
           {"path": "ref/x.fa", "tier": "ref", "drs_uri": "drs://h/ref"}]
    return environment().from_string(expr).render(load_vars(verify_inventory=inv, **sw))


def test_smoke_run_input_is_in_a_mounted_tier():
    assert smoke_drs_uri() == "drs://h/root"
    assert smoke_drs_uri(**ON) == "drs://h/ref"
