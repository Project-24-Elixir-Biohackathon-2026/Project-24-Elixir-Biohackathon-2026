"""spe_preflight.py decides whether an existing host may be configured for an instance."""
import importlib.util
import json
from pathlib import Path

import pytest

PLATFORM = Path(__file__).resolve().parents[2]
SCRIPT = PLATFORM / "ansible" / "roles" / "existing_host" / "files" / "spe_preflight.py"


def load():
    spec = importlib.util.spec_from_file_location("spe_preflight", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def pf():
    return load()


class FakeHost:
    """What the host looks like: listening ports, which compose project publishes each, free disk."""

    def __init__(self, listening=(), port_projects=None, projects_running=(), free_gb=100, docker_root=None):
        self.listening = set(listening)
        self.port_projects = port_projects or {}
        self.projects_running = set(projects_running)
        self.free = free_gb
        self.docker_root_dir = docker_root

    def listening_ports(self):
        return self.listening

    def projects_publishing(self, port):
        return self.port_projects.get(port, set())

    def running_projects(self):
        return self.projects_running

    def free_gb(self, path):
        return self.free

    def docker_root(self):
        return self.docker_root_dir


def cfg(tmp_path, **over):
    base = {
        "instance": "dev-local",
        "provision": "existing",
        "marker": str(tmp_path / "etc" / "spe-instance"),
        "manifest": str(tmp_path / "etc" / "spe-instance.json"),
        "paths": {
            "stack_dir": str(tmp_path / "srv" / "workflow-stack"),
            "frontend_dir": str(tmp_path / "srv" / "spe-frontend"),
            "data_root": str(tmp_path / "srv" / "data"),
        },
        "ports": {"443": "workflow-stack", "3000": "spe-frontend", "8100": "spe-frontend"},
        "projects": ["workflow-stack", "spe-frontend"],
        "min_free_gb": 15,
    }
    base.update(over)
    (tmp_path / "etc").mkdir(exist_ok=True)
    (tmp_path / "srv").mkdir(exist_ok=True)
    return base


def own(c, tmp_path, instance="dev-local", paths=None):
    """Make the host look as if `instance` had already been created here."""
    Path(c["marker"]).write_text(instance + "\n")
    Path(c["manifest"]).write_text(json.dumps({
        "instance": instance, "provision": "existing",
        "paths": paths if paths is not None else c["paths"],
        "compose_projects": c["projects"],
    }))


def test_fresh_host_is_accepted(pf, tmp_path):
    c = cfg(tmp_path)
    res = pf.check(c, FakeHost())
    assert res["problems"] == []
    assert res["owner"] == ""
    assert res["resolved"]["stack_dir"] == c["paths"]["stack_dir"]


def test_other_instance_is_refused(pf, tmp_path):
    c = cfg(tmp_path)
    own(c, tmp_path, instance="dev-local")
    res = pf.check({**c, "instance": "intruder"}, FakeHost())
    assert any("belongs to instance 'dev-local', not 'intruder'" in p for p in res["problems"])


def test_unmarked_host_with_stack_dir_is_refused(pf, tmp_path):
    c = cfg(tmp_path)
    Path(c["paths"]["stack_dir"]).mkdir()
    res = pf.check(c, FakeHost())
    assert any("stack_dir" in p and "not owned" in p for p in res["problems"])


def test_unmarked_host_with_443_in_use_is_refused(pf, tmp_path):
    res = pf.check(cfg(tmp_path), FakeHost(listening={443}))
    assert any("443" in p for p in res["problems"])


def test_unmarked_host_with_our_project_running_is_refused(pf, tmp_path):
    res = pf.check(cfg(tmp_path), FakeHost(projects_running={"spe-frontend"}))
    assert any("spe-frontend" in p for p in res["problems"])


def test_owned_host_converges(pf, tmp_path):
    c = cfg(tmp_path)
    own(c, tmp_path)
    for p in c["paths"].values():
        Path(p).mkdir()
    host = FakeHost(listening={443, 3000}, port_projects={443: {"workflow-stack"}, 3000: {"spe-frontend"}},
                    projects_running={"workflow-stack", "spe-frontend"})
    assert pf.check(c, host)["problems"] == []


def test_owned_host_with_foreign_listener_is_refused(pf, tmp_path):
    c = cfg(tmp_path)
    own(c, tmp_path)
    host = FakeHost(listening={3000}, port_projects={3000: {"someone-else"}})
    res = pf.check(c, host)
    assert any("3000" in p for p in res["problems"])


def test_owned_host_with_unrecorded_existing_path_is_refused(pf, tmp_path):
    c = cfg(tmp_path)
    own(c, tmp_path, paths={**c["paths"], "frontend_dir": "/elsewhere"})
    Path(c["paths"]["frontend_dir"]).mkdir()
    res = pf.check(c, FakeHost())
    assert any("frontend_dir" in p for p in res["problems"])


def test_marker_without_manifest_is_refused(pf, tmp_path):
    c = cfg(tmp_path)
    Path(c["marker"]).write_text("dev-local\n")
    res = pf.check(c, FakeHost())
    assert any("manifest" in p for p in res["problems"])


@pytest.mark.parametrize("bad", ["relative/dir", "/", "/home/someone", "/root"])
def test_unsafe_paths_are_refused(pf, tmp_path, bad):
    c = cfg(tmp_path)
    c["paths"]["data_root"] = bad
    res = pf.check(c, FakeHost())
    assert any("data_root" in p for p in res["problems"])


def test_symlinked_path_is_refused(pf, tmp_path):
    c = cfg(tmp_path)
    (tmp_path / "shared").mkdir()
    Path(c["paths"]["data_root"]).symlink_to(tmp_path / "shared")
    res = pf.check(c, FakeHost())
    assert any("data_root" in p and "symlink" in p for p in res["problems"])


def test_low_disk_is_refused(pf, tmp_path):
    res = pf.check(cfg(tmp_path), FakeHost(free_gb=3, docker_root="/var/lib/docker"))
    assert any("3 GB free" in p for p in res["problems"])


def test_path_inside_docker_root_is_refused(pf, tmp_path):
    c = cfg(tmp_path)
    res = pf.check(c, FakeHost(docker_root=str(tmp_path / "srv")))
    assert any("Docker" in p for p in res["problems"])


def test_cli_prints_json(tmp_path):
    import base64
    import subprocess
    import sys
    c = cfg(tmp_path, ports={})
    arg = base64.b64encode(json.dumps(c).encode()).decode()
    out = subprocess.run([sys.executable, str(SCRIPT), arg], check=True, capture_output=True, text=True).stdout
    assert "problems" in json.loads(out)


# --- reset: what destroy.yml may remove from an existing host ------------------------------

class ResetHost(FakeHost):
    """Adds the compose files each project's containers were created from, and mount points."""

    def __init__(self, project_files=None, mounts=("/",), **kw):
        super().__init__(**kw)
        self.project_files = project_files or {}
        self.mount_points = list(mounts)

    def project_config_files(self, project):
        return self.project_files.get(project, set())

    def mounts(self):
        return self.mount_points


def reset_cfg(tmp_path, **over):
    c = cfg(tmp_path)
    p = c["paths"]
    c.update({
        "mode": "reset",
        "projects": {
            "workflow-stack": p["stack_dir"] + "/deployment/compose.install.yaml",
            "spe-frontend": p["frontend_dir"] + "/docker-compose.yml",
        },
        "shared": [str(tmp_path / "dataset")],
    })
    c.pop("ports"); c.pop("min_free_gb")
    c.update(over)
    return c


def created(c, instance="dev-local", provision="existing", paths=None, projects=None):
    """The host as create.yml leaves it: marker, manifest, directories, compose files."""
    Path(c["marker"]).write_text(instance + "\n")
    Path(c["manifest"]).write_text(json.dumps({
        "instance": instance, "provision": provision,
        "paths": paths if paths is not None else c["paths"],
        "compose_projects": projects if projects is not None else sorted(c["projects"]),
    }))
    for d in c["paths"].values():
        Path(d).mkdir(parents=True, exist_ok=True)
    for f in c["projects"].values():
        Path(f).parent.mkdir(parents=True, exist_ok=True)
        Path(f).write_text("services: {}\n")


def running(c):
    return ResetHost(project_files={name: {f} for name, f in c["projects"].items()},
                     projects_running=set(c["projects"]))


def test_reset_of_owned_host_lists_exactly_its_paths_and_projects(pf, tmp_path):
    c = reset_cfg(tmp_path)
    created(c)
    plan = pf.reset_plan(c, running(c))
    assert plan["problems"] == []
    assert sorted(plan["paths"]) == sorted(c["paths"].values())
    assert plan["projects"] == [{"name": n, "file": f} for n, f in sorted(c["projects"].items())]


def test_reset_without_marker_is_refused(pf, tmp_path):
    c = reset_cfg(tmp_path)
    created(c)
    Path(c["marker"]).unlink()
    plan = pf.reset_plan(c, running(c))
    assert any("marker" in p for p in plan["problems"])


def test_reset_of_another_instance_is_refused(pf, tmp_path):
    c = reset_cfg(tmp_path)
    created(c, instance="someone-else")
    plan = pf.reset_plan(c, running(c))
    assert any("someone-else" in p for p in plan["problems"])


def test_reset_with_other_provision_mode_is_refused(pf, tmp_path):
    c = reset_cfg(tmp_path)
    created(c, provision="openstack")
    plan = pf.reset_plan(c, running(c))
    assert any("openstack" in p for p in plan["problems"])


def test_reset_of_path_not_in_manifest_is_refused(pf, tmp_path):
    c = reset_cfg(tmp_path)
    created(c, paths={**c["paths"], "data_root": str(tmp_path / "srv" / "other")})
    plan = pf.reset_plan(c, running(c))
    assert any("data_root" in p and "manifest" in p for p in plan["problems"])


def test_reset_of_shared_dataset_is_refused(pf, tmp_path):
    c = reset_cfg(tmp_path, shared=[str(tmp_path / "srv" / "data" / "ref")])
    created(c)
    plan = pf.reset_plan(c, running(c))
    assert any("data_root" in p and "shared" in p for p in plan["problems"])


def test_reset_of_path_holding_a_mount_is_refused(pf, tmp_path):
    c = reset_cfg(tmp_path)
    created(c)
    host = running(c)
    host.mount_points.append(str(tmp_path / "srv" / "data" / "share"))
    plan = pf.reset_plan(c, host)
    assert any("data_root" in p and "mount" in p for p in plan["problems"])


def test_reset_of_path_in_docker_root_is_refused(pf, tmp_path):
    c = reset_cfg(tmp_path)
    created(c)
    host = running(c)
    host.docker_root_dir = str(tmp_path / "srv")
    plan = pf.reset_plan(c, host)
    assert any("Docker" in p for p in plan["problems"])


@pytest.mark.parametrize("bad", ["/", "/home/ubuntu", "relative"])
def test_reset_of_unsafe_path_is_refused_even_if_recorded(pf, tmp_path, bad):
    c = reset_cfg(tmp_path)
    created(c)
    c["paths"]["data_root"] = bad
    Path(c["manifest"]).write_text(json.dumps({
        "instance": "dev-local", "provision": "existing", "paths": c["paths"],
        "compose_projects": sorted(c["projects"])}))
    plan = pf.reset_plan(c, running(c))
    assert any("data_root" in p for p in plan["problems"])


def test_reset_of_symlinked_path_is_refused(pf, tmp_path):
    c = reset_cfg(tmp_path)
    (tmp_path / "elsewhere").mkdir()
    created(c)
    Path(c["paths"]["data_root"]).rmdir()
    Path(c["paths"]["data_root"]).symlink_to(tmp_path / "elsewhere")
    plan = pf.reset_plan(c, running(c))
    assert any("data_root" in p and "symlink" in p for p in plan["problems"])


def test_reset_takes_a_symlinked_compose_file_down_through_its_link(pf, tmp_path):
    # The frontend's docker-compose.yml links into the repository clone; Compose reads the .env with
    # COMPOSE_PROFILES next to the file it is given, so the resolved path would take nothing down.
    c = reset_cfg(tmp_path)
    c["paths"]["repo_dir"] = str(tmp_path / "srv" / "sperange")
    created(c)
    link = Path(c["projects"]["spe-frontend"])
    target = Path(c["paths"]["repo_dir"]) / "platform" / "instance" / "compose.yml"
    target.parent.mkdir(parents=True)
    target.write_text("services: {}\n")
    link.unlink()
    link.symlink_to(target)
    plan = pf.reset_plan(c, running(c))
    assert plan["problems"] == []
    assert {"name": "spe-frontend", "file": str(link)} in plan["projects"]


def test_reset_with_compose_link_pointing_outside_owned_paths_is_refused(pf, tmp_path):
    c = reset_cfg(tmp_path)
    created(c)
    link = Path(c["projects"]["spe-frontend"])
    target = tmp_path / "elsewhere" / "compose.yml"
    target.parent.mkdir()
    target.write_text("services: {}\n")
    link.unlink()
    link.symlink_to(target)
    plan = pf.reset_plan(c, running(c))
    assert any("spe-frontend" in p and "outside" in p for p in plan["problems"])
    assert plan["projects"] == []


def test_reset_of_project_created_from_another_file_is_refused(pf, tmp_path):
    c = reset_cfg(tmp_path)
    created(c)
    host = running(c)
    host.project_files["spe-frontend"] = {"/opt/other/docker-compose.yml"}
    plan = pf.reset_plan(c, host)
    assert any("spe-frontend" in p and "/opt/other" in p for p in plan["problems"])


def test_reset_of_project_not_in_manifest_is_refused(pf, tmp_path):
    c = reset_cfg(tmp_path)
    created(c, projects=["workflow-stack"])
    plan = pf.reset_plan(c, running(c))
    assert any("spe-frontend" in p for p in plan["problems"])


def test_reset_with_compose_file_outside_owned_paths_is_refused(pf, tmp_path):
    c = reset_cfg(tmp_path)
    created(c)
    c["projects"]["spe-frontend"] = str(tmp_path / "compose.yml")
    Path(c["projects"]["spe-frontend"]).write_text("services: {}\n")
    plan = pf.reset_plan(c, running(c))
    assert any("spe-frontend" in p and "outside" in p for p in plan["problems"])


def test_reset_skips_projects_already_gone(pf, tmp_path):
    c = reset_cfg(tmp_path)
    created(c)
    Path(c["projects"]["spe-frontend"]).unlink()
    host = ResetHost(project_files={"workflow-stack": {c["projects"]["workflow-stack"]}})
    plan = pf.reset_plan(c, host)
    assert plan["problems"] == []
    assert [p["name"] for p in plan["projects"]] == ["workflow-stack"]


def test_reset_of_running_project_without_its_file_is_refused(pf, tmp_path):
    c = reset_cfg(tmp_path)
    created(c)
    Path(c["projects"]["spe-frontend"]).unlink()
    plan = pf.reset_plan(c, running(c))
    assert any("spe-frontend" in p and "missing" in p for p in plan["problems"])


def test_cli_reset_mode(tmp_path):
    import base64
    import subprocess
    import sys
    c = reset_cfg(tmp_path)
    arg = base64.b64encode(json.dumps(c).encode()).decode()
    out = json.loads(subprocess.run([sys.executable, str(SCRIPT), arg], check=True, capture_output=True, text=True).stdout)
    assert out["paths"] == [] and any("marker" in p for p in out["problems"])
