"""The workflow stack hides files no analysis needs: every container that mounts the
dataset covers each masked file with /dev/null, under each of its dataset mount points, so
a workflow that opens one reads nothing."""
import ast
from pathlib import Path

import jinja2
import pytest
import yaml

PLATFORM = Path(__file__).resolve().parents[2]
TEMPLATE = PLATFORM / "ansible" / "roles" / "workflow_stack" / "templates" / "compose.install.yaml.j2"
GROUP_VARS = PLATFORM / "ansible" / "inventory" / "group_vars" / "all.yml"
SEEDER = PLATFORM / "ansible" / "roles" / "spe_data" / "files" / "spe_seed.py"
DATA_ROOT = "/srv/spe-data"
MASKS = ["sensitive/secret/research_DO_NOT_LEAK", "sensitive/registry/linkage.csv"]


def render_text(masks, stamp="", guard=False):
    # trim_blocks as Ansible's template module renders it; unset variables render empty.
    env = jinja2.Environment(undefined=jinja2.ChainableUndefined, trim_blocks=True)
    return env.from_string(TEMPLATE.read_text()).render(
        spe_data_root=DATA_ROOT, wes_masks=masks, wes_mask_stamp=stamp,
        spe_canary_guard=guard, spe_canary_guard_mode="redact",
        spe_canary_guard_exempt=["registry-study-id"])


def render(masks, guard=False):
    return yaml.safe_load(render_text(masks, guard=guard))


def volume_source_target(volume):
    if isinstance(volume, dict):
        return str(volume.get("source", "")), str(volume.get("target", ""))
    parts = str(volume).split(":")
    return parts[0], parts[1] if len(parts) > 1 else ""


def dataset_mounts(compose):
    """{service: [mount point of the dataset, ...]}. Any volume whose source is the dataset
    root or lies under it counts, whatever its syntax, so a new mount shape is not skipped."""
    mounts = {}
    for name, svc in compose["services"].items():
        for volume in svc.get("volumes", []):
            source, target = volume_source_target(volume)
            if source == DATA_ROOT or source.startswith(DATA_ROOT + "/"):
                assert isinstance(volume, str) and source == DATA_ROOT, (
                    f"{name} mounts the dataset as {volume!r}: only the whole root in short "
                    "syntax is masked by the template")
                mounts.setdefault(name, []).append(target)
    return mounts


def seeded_sensitive_files():
    """Every file spe_seed.py records a canary in, outside the genomes (which analysis reads)."""
    files = set()
    for node in ast.walk(ast.parse(SEEDER.read_text())):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add" and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "canaries" and len(node.args) >= 3
                and isinstance(node.args[2], ast.Constant) and isinstance(node.args[2].value, str)):
            files.add(node.args[2].value)
    return {f for f in files if not f.startswith("sensitive/genomes/")}


def masked_list():
    return set(yaml.safe_load(GROUP_VARS.read_text())["spe_wes_masked_files"])


def test_every_canary_file_outside_the_genomes_is_masked():
    seeded = seeded_sensitive_files()
    assert "sensitive/secret/research_DO_NOT_LEAK" in seeded  # the parser still finds them
    assert seeded <= masked_list(), f"seeded but not masked: {sorted(seeded - masked_list())}"


def test_the_sqlite_copy_of_the_identity_link_is_masked():
    assert "sensitive/registry/registry.sqlite" in masked_list()


# The canary guard takes the API routes away from rest and drs-filer, right next to
# their mask entries; the masks must not depend on it.
@pytest.mark.parametrize("guard", [False, True], ids=["guard-off", "guard-on"])
def test_every_dataset_container_masks_each_file_under_each_mount_point(guard):
    compose = render(MASKS, guard=guard)
    mounts = dataset_mounts(compose)
    assert {"rest", "submission_worker", "monitoring_worker", "monitoring_scheduler", "drs-filer"} <= mounts.keys()
    for name, points in mounts.items():
        volumes = compose["services"][name]["volumes"]
        for f in MASKS:
            for point in points:
                assert f"/dev/null:{point}/{f}:ro" in volumes, f"{name}: {point}/{f} is not masked"


def test_a_new_inode_changes_the_rendered_file():
    # The role recreates the stack when the render changes; the mask follows the inode.
    assert render_text(MASKS, stamp="11 12") != render_text(MASKS, stamp="11 99")
    assert "11 12" in render_text(MASKS, stamp="11 12")


def test_without_masks_nothing_is_masked():
    compose = render([])
    assert "Inodes of the masked files" not in render_text([])
    for name in dataset_mounts(compose):
        volumes = compose["services"][name]["volumes"]
        assert not [v for v in volumes if str(v).startswith("/dev/null:")], name
