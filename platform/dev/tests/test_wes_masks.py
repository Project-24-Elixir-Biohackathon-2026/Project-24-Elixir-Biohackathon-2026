"""The workflow stack hides files no analysis needs: every container that mounts the
dataset covers each masked file with /dev/null, under each of its dataset mount points, so
a workflow that opens one reads nothing."""
from pathlib import Path

import jinja2
import yaml

PLATFORM = Path(__file__).resolve().parents[2]
TEMPLATE = PLATFORM / "ansible" / "roles" / "workflow_stack" / "templates" / "compose.install.yaml.j2"
GROUP_VARS = PLATFORM / "ansible" / "inventory" / "group_vars" / "all.yml"
DATA_ROOT = "/srv/spe-data"


def render(masks):
    # trim_blocks as Ansible's template module renders it; unset variables render empty.
    env = jinja2.Environment(undefined=jinja2.ChainableUndefined, trim_blocks=True)
    text = env.from_string(TEMPLATE.read_text()).render(spe_data_root=DATA_ROOT, wes_masks=masks)
    return yaml.safe_load(text)


def dataset_mounts(compose):
    """{service: [mount point of the dataset, ...]} for every service that mounts it."""
    mounts = {}
    for name, svc in compose["services"].items():
        points = [str(v).split(":")[1] for v in svc.get("volumes", []) if str(v).startswith(f"{DATA_ROOT}:")]
        if points:
            mounts[name] = points
    return mounts


def test_masked_list_covers_the_honeypots_and_the_identity_link():
    masked = set(yaml.safe_load(GROUP_VARS.read_text())["spe_wes_masked_files"])
    assert {
        "sensitive/registry/patient_identifiers_DO_NOT_EXPORT.csv",
        "sensitive/registry/.aws_credentials_backup.txt",
        "sensitive/registry/db_migration_notes.env",
        "sensitive/registry/linkage.csv",
        "sensitive/registry/registry.sqlite",
        "sensitive/secret/research_DO_NOT_LEAK",
    } <= masked


def test_every_dataset_container_masks_each_file_under_each_mount_point():
    masks = ["sensitive/secret/research_DO_NOT_LEAK", "sensitive/registry/linkage.csv"]
    compose = render(masks)
    mounts = dataset_mounts(compose)
    assert {"rest", "submission_worker", "monitoring_worker", "monitoring_scheduler", "drs-filer"} <= mounts.keys()
    for name, points in mounts.items():
        volumes = compose["services"][name]["volumes"]
        for f in masks:
            for point in points:
                assert f"/dev/null:{point}/{f}:ro" in volumes, f"{name}: {point}/{f} is not masked"


def test_without_masks_the_mounts_stay_as_they_were():
    compose = render([])
    for name in dataset_mounts(compose):
        volumes = compose["services"][name]["volumes"]
        assert not [v for v in volumes if str(v).startswith("/dev/null:")], name
