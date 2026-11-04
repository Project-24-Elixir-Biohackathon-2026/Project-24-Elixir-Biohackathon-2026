#!/usr/bin/env python3
"""Decide whether an existing host may be configured for an SPE instance.

Runs on the host before anything changes it. Argument: base64 of a JSON object
  {instance, provision, marker, manifest, paths: {name: abs path},
   ports: {"port": compose project}, projects: [compose projects], min_free_gb}
Prints {"owner": ..., "problems": [...], "resolved": {name: path}} on stdout.

The host is free for the instance when its marker (/etc/spe-instance) is
absent or names the instance. A missing marker means nothing of ours is here:
any existing instance path, listener on a requested port or running compose
project of ours belongs to someone else. A matching marker must come with the
manifest written at creation, and every path, listener and project must be
the ones it records: the marker alone excuses nothing.

With "mode": "reset" (destroy.yml) the argument is instead
  {mode, instance, provision, marker, manifest, paths: {name: abs path},
   projects: {compose project: compose file}, shared: [paths never to remove]}
and the output {"problems": [...], "paths": [...], "projects": [{name, file}]}
names exactly what may be removed: the marker and the manifest must name this
instance and mode, every path must be the one recorded, safe, not a symlink,
not a mount or holding one, clear of Docker's data root and the shared paths,
and every compose project must be recorded and built from its own file. A
project's file is the path given (a link is kept, so Compose reads the .env
beside it); the checks use its resolved target.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys


class Host:
    """The real host. Tests substitute a fake with the same methods."""

    def listening_ports(self) -> set[int]:
        try:
            out = subprocess.run(["ss", "-Htln"], check=True, capture_output=True, text=True).stdout
        except (OSError, subprocess.CalledProcessError):
            return set()
        ports = set()
        for line in out.splitlines():
            cols = line.split()
            if len(cols) >= 4 and ":" in cols[3]:
                tail = cols[3].rsplit(":", 1)[1]
                if tail.isdigit():
                    ports.add(int(tail))
        return ports

    def _docker(self, *args: str) -> list[str]:
        if shutil.which("docker") is None:
            return []
        try:
            res = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            return []
        return [line for line in res.stdout.splitlines() if line.strip()] if res.returncode == 0 else []

    def projects_publishing(self, port: int) -> set[str]:
        return set(self._docker("ps", "--filter", f"publish={port}",
                                "--format", '{{.Label "com.docker.compose.project"}}'))

    def running_projects(self) -> set[str]:
        return set(self._docker("ps", "-a", "--format", '{{.Label "com.docker.compose.project"}}'))

    def free_gb(self, path: str) -> int:
        st = os.statvfs(existing_ancestor(path))
        return st.f_bavail * st.f_frsize // 2**30

    def docker_root(self) -> str | None:
        out = self._docker("info", "--format", "{{.DockerRootDir}}")
        return out[0].strip() if out else None

    def project_config_files(self, project: str) -> set[str]:
        labels = self._docker("ps", "-a", "--filter", f"label=com.docker.compose.project={project}",
                              "--format", '{{.Label "com.docker.compose.project.config_files"}}')
        return {f for line in labels for f in line.split(",") if f}

    def mounts(self) -> list[str]:
        try:
            with open("/proc/self/mounts") as f:
                # Octal escapes (\040 for a space) as in fstab.
                return [line.split()[1].encode().decode("unicode_escape") for line in f if line.strip()]
        except OSError:
            return ["/"]


def existing_ancestor(path: str) -> str:
    p = os.path.abspath(path)
    while not os.path.exists(p):
        p = os.path.dirname(p)
    return p


def inside(path: str, root: str) -> bool:
    path, root = os.path.normpath(path), os.path.normpath(root)
    return path == root or path.startswith(root.rstrip("/") + "/")


def unsafe(path: str) -> str | None:
    """Why a path may not be dedicated to one instance, or None."""
    if not os.path.isabs(path):
        return "is not absolute"
    norm = os.path.normpath(path)
    parts = [p for p in norm.split("/") if p]
    if not parts:
        return "is /"
    if norm == "/root" or (parts[0] == "home" and len(parts) <= 2):
        return "is a home directory"
    if len(parts) == 1 and parts[0] in {"etc", "usr", "var", "opt", "bin", "sbin", "lib", "boot", "srv", "tmp", "storage"}:
        return "is a system directory"
    return None


def read_marker(path: str) -> str:
    try:
        with open(path) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def read_manifest(path: str) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return None


def check(cfg: dict, host) -> dict:
    problems: list[str] = []
    instance = cfg["instance"]
    owner = read_marker(cfg["marker"])
    ours = owner == instance

    if owner and not ours:
        problems.append(f"host belongs to instance '{owner}', not '{instance}'")

    manifest = None
    if ours:
        manifest = read_manifest(cfg["manifest"])
        if manifest is None:
            problems.append(f"marker names {instance} but the ownership manifest {cfg['manifest']} is missing or unreadable")
        elif manifest.get("instance") != instance or manifest.get("provision") != cfg.get("provision"):
            problems.append(f"manifest {cfg['manifest']} is for instance {manifest.get('instance')!r} "
                            f"({manifest.get('provision')!r}), not {instance!r} ({cfg.get('provision')!r})")
            manifest = None
    recorded_paths = (manifest or {}).get("paths", {})
    recorded_projects = set((manifest or {}).get("compose_projects", []))

    docker_root = host.docker_root()
    resolved = {}
    for name, path in cfg["paths"].items():
        why = unsafe(path)
        if why:
            problems.append(f"{name} {path} {why}")
            continue
        if os.path.islink(path):
            problems.append(f"{name} {path} is a symlink; use the real path")
            continue
        real = os.path.realpath(path)
        resolved[name] = real
        if docker_root and (inside(real, docker_root) or inside(docker_root, real)):
            problems.append(f"{name} {real} overlaps Docker's data root {docker_root}")
        if os.path.exists(real) and not (ours and recorded_paths.get(name) == real):
            problems.append(f"{name} {real} exists but is not owned by {instance} (no manifest entry): "
                            "another stack lives here; pick another host or path")

    listening = host.listening_ports()
    for port_s, project in cfg.get("ports", {}).items():
        port = int(port_s)
        if port not in listening:
            continue
        publishers = host.projects_publishing(port)
        if not (ours and project in recorded_projects and publishers == {project}):
            who = ", ".join(sorted(p or "<not compose>" for p in publishers)) or "a process outside Docker"
            problems.append(f"port {port} is in use by {who}, not by this instance's {project}")

    running = host.running_projects()
    for project in cfg.get("projects", []):
        if project in running and not (ours and project in recorded_projects):
            problems.append(f"compose project {project} has containers here but is not owned by {instance}")

    checked = {existing_ancestor(p) for p in resolved.values()}
    if docker_root:
        checked.add(existing_ancestor(docker_root))
    for p in sorted(checked):
        free = host.free_gb(p)
        if free < cfg.get("min_free_gb", 0):
            problems.append(f"only {free} GB free on the filesystem of {p}, need {cfg['min_free_gb']}")

    return {"owner": owner, "problems": problems, "resolved": resolved}


def reset_plan(cfg: dict, host) -> dict:
    problems: list[str] = []
    instance, provision = cfg["instance"], cfg.get("provision")
    owner = read_marker(cfg["marker"])
    if not owner:
        problems.append(f"no ownership marker {cfg['marker']}: nothing here is known to belong to {instance}")
    elif owner != instance:
        problems.append(f"host belongs to instance '{owner}', not '{instance}'")
    manifest = read_manifest(cfg["manifest"]) or {}
    if not manifest:
        problems.append(f"ownership manifest {cfg['manifest']} is missing or unreadable")
    elif manifest.get("instance") != instance or manifest.get("provision") != provision:
        problems.append(f"manifest {cfg['manifest']} is for instance {manifest.get('instance')!r} "
                        f"({manifest.get('provision')!r}), not {instance!r} ({provision!r})")
    recorded_paths = manifest.get("paths", {})
    recorded_projects = set(manifest.get("compose_projects", []))

    docker_root = host.docker_root()
    shared = [os.path.realpath(p) for p in cfg.get("shared", []) if p]
    mounts = [os.path.normpath(m) for m in host.mounts()]
    paths: list[str] = []
    for name, path in cfg["paths"].items():
        why = unsafe(path)
        if why:
            problems.append(f"{name} {path} {why}")
            continue
        if os.path.islink(path):
            problems.append(f"{name} {path} is a symlink; nothing behind it is removed")
            continue
        real = os.path.realpath(path)
        if recorded_paths.get(name) != real:
            problems.append(f"{name} {real} is not the path the manifest records ({recorded_paths.get(name)!r})")
            continue
        if docker_root and (inside(real, docker_root) or inside(docker_root, real)):
            problems.append(f"{name} {real} overlaps Docker's data root {docker_root}")
            continue
        clash = [p for p in shared if inside(real, p) or inside(p, real)]
        if clash:
            problems.append(f"{name} {real} overlaps shared data {', '.join(clash)}")
            continue
        held = [m for m in mounts if inside(m, real)]
        if held:
            problems.append(f"{name} {real} is or holds a mount point ({', '.join(held)})")
            continue
        paths.append(real)

    owned = [os.path.realpath(p) for p in cfg["paths"].values() if not unsafe(p)]
    projects: list[dict] = []
    for name, file in sorted(cfg.get("projects", {}).items()):
        if name not in recorded_projects:
            problems.append(f"compose project {name} is not recorded in the manifest")
            continue
        real = os.path.realpath(file)
        if not any(inside(real, o) for o in owned):
            problems.append(f"compose project {name}: file {file} lies outside this instance's paths")
            continue
        built_from = host.project_config_files(name)
        foreign = sorted(f for f in built_from if os.path.realpath(f) != real)
        if foreign:
            problems.append(f"compose project {name} has containers from {', '.join(foreign)}, not {file}")
            continue
        if os.path.isfile(real):
            # Taken down through the path given, a link included: Compose reads the .env beside it
            # (COMPOSE_PROFILES), and the resolved file's directory has none.
            projects.append({"name": name, "file": file})
        elif built_from or name in host.running_projects():
            problems.append(f"compose project {name} has containers but its file {file} is missing")

    if problems:
        paths, projects = [], []
    return {"problems": problems, "paths": paths, "projects": projects}


def main() -> int:
    cfg = json.loads(base64.b64decode(sys.argv[1]))
    result = reset_plan(cfg, Host()) if cfg.get("mode") == "reset" else check(cfg, Host())
    json.dump(result, sys.stdout)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
