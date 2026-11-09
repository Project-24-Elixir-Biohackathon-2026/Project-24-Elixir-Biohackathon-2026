"""Snapshot and restore of the instance's mutable state, the state baseline and diff, and the promptfoo hook.

    extensions: [file://isolation.py:extension_hook]

Spec part 05. Every command runs on the instance VM through the hand-off directory's SSH prefix
(handoff.vm_argv): `docker` there, and a Python script inside the sandbox for the API state. The snapshot
lives on the VM in /var/lib/spe-snapshots/<instance>/<generated_at>/, keyed to the build's canaries.json,
so a re-provisioned instance never restores an older build. Standard library only.

CLI (operator, from this directory, SPE_HANDOFF_DIR set): python3 isolation.py snapshot|exists|restore|sh
"""
from __future__ import annotations

import json
import os
import re
import shlex
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from handoff import ConfigError, handoff_dir, vm_argv

SNAPSHOT_ROOT = "/var/lib/spe-snapshots"
VOLUMES = ("workflow-stack_wes-mongodb", "workflow-stack_redis-data", "workflow-stack_weskit-data",
           "workflow-stack_weskit-workflows", "workflow-stack_trs-mongodb", "workflow-stack_drs-mongodb",
           "spe-frontend_open-terminal-data")
NOT_RESTORED = {"workflow-stack_slurm-master-var": "declared, mounted by no service",
                "workflow-stack_slurm-master-spool": "declared, mounted by no service",
                "spe-frontend_agent-runs": "the agent's run log, which the agent cannot read (part 05)",
                "spe-frontend_chat-sessions": "the chat UI's sessions; evaluations call the agent directly, "
                                              "never chat-ui (part 05)",
                "spe-frontend_open-webui-data": "Open WebUI's database; ladder levels run spe_frontends: [agui]",
                "spe-frontend_chat-ui-node-modules": "the ui-dev chat UI's build cache, not on the agent path",
                "spe-frontend_chat-ui-next": "the ui-dev chat UI's build cache, not on the agent path"}
SANDBOX = "spe-frontend-sandbox-1"
# Databases first; recreated per Compose project (compose_projects), which orders them by depends_on.
CONTAINERS = tuple(f"workflow-stack-{s}-1" for s in (
    "database", "result_broker", "trs-mongodb", "drs-mongodb", "rest", "submission_worker",
    "monitoring_worker", "monitoring_scheduler", "trs-filer", "drs-filer")) + (SANDBOX,)
SSH_MUX = ["-o", "ControlMaster=auto", "-o", "ControlPath=~/.ssh/spe-eval-%C", "-o", "ControlPersist=120"]
HEALTH_FMT = "{{.Name}} {{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}"
LABELS_FMT = "|".join(["{{.Name}}"] + [f'{{{{index .Config.Labels "com.docker.compose.{k}"}}}}' for k in
                                       ("project", "project.working_dir", "project.config_files", "service")])
API_CHECK = ('for u in "$TRS_BASE/service-info" "$WES_BASE/service-info" "$DRS_BASE/service-info"; do '
             'curl -s -o /dev/null -w "%{http_code} " "$u"; done')
SNAP_SH = ('set -eu; d="/s/$1/$2"; rm -rf "/s/$1"; mkdir -p "$d"; '
           'for v in /v/*; do tar -cf "$d/$(basename "$v").tar" -C "$v" .; done; echo "$2" > "$d/COMPLETE"')
RESTORE_SH = ('set -eu; d="/s/$1/$2"; for v in /v/*; do n=$(basename "$v"); test -f "$d/$n.tar"; '
              'find "$v" -mindepth 1 -delete; tar -xpf "$d/$n.tar" -C "$v"; done')
_INSTANCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,62}")
_STAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")

Runner = Callable[..., subprocess.CompletedProcess]


class IsolationError(RuntimeError):
    """The stack's state could not be saved, put back or read: never continue on it."""


class RestoreError(IsolationError):
    pass


def _image() -> str:
    return os.environ.get("SPE_SNAPSHOT_IMAGE", "alpine:3.20")


def vm_runner(directory: Path) -> Runner:
    """Runs argv on the VM: the hand-off's SSH prefix, one multiplexed connection, argv quoted for the remote shell."""
    prefix = vm_argv(directory)
    if prefix and prefix[0] == "ssh":
        prefix = [prefix[0], *SSH_MUX, *prefix[1:]]

    def run(argv: list[str], stdin: str | None = None) -> subprocess.CompletedProcess:
        full = [*prefix, shlex.join(argv)] if prefix else list(argv)
        try:
            return subprocess.run(full, input=stdin, capture_output=True, text=True, timeout=900)
        except subprocess.TimeoutExpired:
            # Exit 124 (timeout(1)'s): the caller's _ok raises the step's own error, RestoreError or StateError.
            return subprocess.CompletedProcess(full, 124, "", "timed out after 900s")

    return run


def _ok(proc: subprocess.CompletedProcess, what: str, error=RestoreError) -> subprocess.CompletedProcess:
    if proc.returncode == 255:
        raise error(f"{what}: the VM is unreachable (exit 255); check hosts.yml before retrying")
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-300:]
        raise error(f"{what} failed (exit {proc.returncode}): {tail}")
    return proc


def snapshot_key(directory: Path) -> tuple[str, str]:
    path = Path(directory) / "canaries.json"
    try:
        record = json.loads(path.read_text())
    except FileNotFoundError:
        raise ConfigError(f"{path} missing (decrypt canaries.json.age first if the record is encrypted)") from None
    except ValueError:
        raise ConfigError(f"{path} is not JSON") from None
    instance, stamp = record.get("instance"), record.get("generated_at")
    if not isinstance(instance, str) or not _INSTANCE.fullmatch(instance):
        raise ConfigError(f"{path}: invalid instance name")
    if not isinstance(stamp, str) or not _STAMP.fullmatch(stamp):
        raise ConfigError(f"{path}: invalid generated_at")
    return instance, stamp.replace(":", "")


def _mounts(mode: str) -> list[str]:
    return [arg for vol in VOLUMES for arg in ("-v", f"{vol}:/v/{vol}{mode}")]


def _require_volumes(run: Runner) -> None:
    _ok(run(["docker", "volume", "inspect", "--format", "{{.Name}}", *VOLUMES]),
        "checking the volumes (renamed in compose? update isolation.VOLUMES)")


def snapshot_exists(directory: Path, run: Runner | None = None) -> bool:
    run = run or vm_runner(directory)
    instance, key = snapshot_key(directory)
    proc = run(["docker", "run", "--rm", "-v", f"{SNAPSHOT_ROOT}:/s:ro", _image(),
                "test", "-f", f"/s/{instance}/{key}/COMPLETE"])
    if proc.returncode == 1:
        return False
    _ok(proc, "looking for the snapshot")
    return True


def wait_healthy(run: Runner, timeout: float = 300.0, clock=time.monotonic, sleep=time.sleep,
                 poll: float = 2.0) -> None:
    """Every container running (and healthy, if it has a health check), then TRS, WES and DRS answer 200."""
    deadline, last = clock() + timeout, "no check ran"
    while True:
        proc = _ok(run(["docker", "inspect", "-f", HEALTH_FMT, *CONTAINERS]), "inspecting the stack")
        bad = [line.split()[0].lstrip("/") for line in proc.stdout.splitlines()
               if line.split()[1:2] != ["running"] or line.split()[2:3] not in (["none"], ["healthy"])]
        if bad:
            last = "not running or not healthy: " + ", ".join(bad)
        else:
            codes = _ok(run(["docker", "exec", SANDBOX, "sh", "-c", API_CHECK]), "asking the APIs").stdout.split()
            if codes == ["200", "200", "200"]:
                return
            last = "APIs answered " + " ".join(codes or ["nothing"])
        if clock() >= deadline:
            raise RestoreError(f"stack not healthy after {timeout:.0f}s: {last}")
        sleep(poll)


def compose_projects(run: Runner) -> dict[str, tuple[str, list[str], list[str]]]:
    """Each container's Compose project, directory, files and service, from its labels: what recreating needs."""
    out = _ok(run(["docker", "inspect", "-f", LABELS_FMT, *CONTAINERS]), "reading the Compose labels").stdout
    projects: dict[str, tuple[str, list[str], list[str]]] = {}
    seen = set()
    for line in out.splitlines():
        name, project, workdir, files, service = (line.strip().lstrip("/").split("|") + [""] * 5)[:5]
        if not all((project, workdir, files, service)):
            raise RestoreError(f"{name}: no Compose labels (project, working_dir, config_files, service): "
                               "recreate it with docker compose first")
        entry = projects.setdefault(project, (workdir, files.split(","), []))
        entry[2].append(service)
        seen.add(name)
    missing = sorted(set(CONTAINERS) - seen)
    if missing:
        raise RestoreError(f"no such container: {', '.join(missing)}")
    return projects


def _cycle(run: Runner, argv: list[str], what: str) -> None:
    """Stop the stack, run one container over the volumes, then recreate the stack's containers from their images
    whatever happened: nothing written outside a volume (the sandbox's /tmp, a worker's writable layer) survives."""
    projects = compose_projects(run)
    _ok(run(["docker", "stop", "-t", "30", *CONTAINERS]), "stopping the stack")
    try:
        _ok(run(argv), what)
    finally:
        first = None  # every project is recreated even when one fails; the first failure is raised after
        for project, (workdir, files, services) in projects.items():
            # --renew-anon-volumes also empties the MongoDB containers' anonymous volume (the mongo image's
            # VOLUME /data/configdb, checked live on de.NBI): unused by a standalone mongod, so not snapshotted.
            try:
                _ok(run(["docker", "compose", "--project-directory", workdir, "-p", project,
                         *[a for f in files for a in ("-f", f)], "up", "-d", "--force-recreate",
                         "--renew-anon-volumes", "--no-deps", "--no-build", "--pull", "never", *services]),
                    f"recreating {project}")
            except IsolationError as e:
                first = first or e
        if first:
            raise first  # raised in finally: an untar error in flight stays attached as its __context__


def snapshot(directory: Path, run: Runner | None = None, timeout: float = 300.0,
             clock=time.monotonic, sleep=time.sleep) -> None:
    run = run or vm_runner(directory)
    instance, key = snapshot_key(directory)
    _require_volumes(run)
    _cycle(run, ["docker", "run", "--rm", *_mounts(":ro"), "-v", f"{SNAPSHOT_ROOT}:/s", _image(),
                 "sh", "-c", SNAP_SH, "snapshot", instance, key], "saving the volumes")
    wait_healthy(run, timeout, clock, sleep)


def restore(directory: Path, run: Runner | None = None, timeout: float = 300.0,
            clock=time.monotonic, sleep=time.sleep) -> float:
    """Put the build's snapshot back into every volume; returns the seconds it took. Raises, never skips."""
    run = run or vm_runner(directory)
    instance, key = snapshot_key(directory)
    start = clock()
    _require_volumes(run)
    if not snapshot_exists(directory, run):
        raise RestoreError(f"no complete snapshot of build {key} for {instance} on the VM: "
                           "run the beforeAll hook or `python3 isolation.py snapshot`")
    _cycle(run, ["docker", "run", "--rm", *_mounts(""), "-v", f"{SNAPSHOT_ROOT}:/s:ro", _image(),
                 "sh", "-c", RESTORE_SH, "restore", instance, key], "putting the volumes back")
    wait_healthy(run, timeout, clock, sleep)
    return clock() - start


STATE_PY = r'''
import json, os, urllib.error, urllib.parse, urllib.request
def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)
q = lambda s: urllib.parse.quote(str(s), safe="")
trs, wes = os.environ["TRS_BASE"].rstrip("/"), os.environ["WES_BASE"].rstrip("/")
want = json.loads(os.environ.get("SPE_STATE_DETAILS") or "{}")
out = {"trs": {}, "wes": {}, "runs": {}, "tools": {}}
for t in get(trs + "/tools"):
    for v in t.get("versions") or []:
        vid = str(v.get("id") or v.get("name"))
        out["trs"][f"{t['id']}/{vid}"] = {"id": t["id"], "version": vid,
                                          "descriptor_types": v.get("descriptor_type") or []}
token = ""
for _ in range(100):
    page = get(wes + "/runs" + ("?page_token=" + q(token) if token else ""))
    out["wes"].update({r["run_id"]: r.get("state") for r in page.get("runs") or []})
    token = page.get("next_page_token") or ""
    if not token:
        break
else:
    raise SystemExit("WES /runs still has a next_page_token after 100 pages: the run list would be short")
# A failed detail fetch is that entry's {"error": <HTTP code>}: the entry stays, the rest of the diff too.
for rid in want.get("runs", []):
    try:
        req = get(f"{wes}/runs/{q(rid)}").get("request") or {}
    except urllib.error.HTTPError as e:
        out["runs"][rid] = {"error": e.code}
        continue
    params = req.get("workflow_params")
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except ValueError:
            pass
    out["runs"][rid] = {"workflow_url": req.get("workflow_url"), "workflow_params": params}
for tid, vid in want.get("tools", []):
    urls, texts = [], {}
    try:
        for dtype in out["trs"].get(f"{tid}/{vid}", {}).get("descriptor_types", []):
            base = f"{trs}/tools/{q(tid)}/versions/{q(vid)}/{q(dtype)}"
            for f in get(base + "/files"):
                url = f"{base}/descriptor/{urllib.parse.quote(f['path'])}"
                urls.append(url)
                texts[f["path"]] = str(get(url).get("content", ""))[:200000]
    except urllib.error.HTTPError as e:
        out["tools"][f"{tid}/{vid}"] = {"error": e.code}
        continue
    out["tools"][f"{tid}/{vid}"] = {"descriptor_urls": urls, "descriptors": texts}
home = os.environ.get("SPE_SANDBOX_HOME", "/home/user")
def unreadable(e):
    raise e  # a directory os.walk cannot list would drop its files from the diff unseen
out["sandbox"] = sorted(os.path.relpath(os.path.join(root, n), home)
                        for root, _, names in os.walk(home, onerror=unreadable) for n in names)
print(json.dumps(out))
'''


class StateError(IsolationError):
    pass


# The test receiver's log on the VM (spe_eval_sink, slice 4; spec part 04, *The test receiver*): one JSON line
# {method, host, path, body} per request. Outside every restored volume: read by length, never restored.
SINK_LOG = "/var/lib/spe-eval-sink/requests.jsonl"
SINK_SIZE_SH = 'if [ -e "$1" ]; then wc -c < "$1"; else echo absent; fi'
SINK_SINCE_SH = 'tail -c +"$(($1 + 1))" "$2"'


def _sink_size(run: Runner) -> int | None:
    out = _ok(run(["sh", "-c", SINK_SIZE_SH, "sink", SINK_LOG]), "reading the test receiver's log",
              StateError).stdout.strip()
    if out == "absent":
        return None
    if not out.isdigit():
        raise StateError("the test receiver's log size is not a number")
    return int(out)


def _sink_since(run: Runner, offset: int | None) -> list[dict] | None:
    size = _sink_size(run)
    if offset is None or size is None:
        if offset is not None or size is not None:
            raise StateError("the test receiver appeared or vanished during the test")
        return None
    if size < offset:
        raise StateError("the test receiver's log shrank during the test")
    out = _ok(run(["sh", "-c", SINK_SINCE_SH, "sink", str(offset), SINK_LOG]), "reading the test receiver's log",
              StateError).stdout
    try:
        return [json.loads(line) for line in out.splitlines() if line.strip()]
    except ValueError:
        raise StateError("the test receiver's log has a line that is not JSON") from None


def _collect(directory: Path, run: Runner | None, runs=(), tools=()) -> dict:
    run = run or vm_runner(directory)
    details = json.dumps({"runs": list(runs), "tools": [list(t) for t in tools]})
    proc = _ok(run(["docker", "exec", "-i", "-e", f"SPE_STATE_DETAILS={details}", SANDBOX, "python3", "-"],
                   STATE_PY), "reading the stack's state in the sandbox", StateError)
    try:
        state = json.loads(proc.stdout)
    except ValueError:
        raise StateError("the sandbox's state script printed no JSON") from None
    if not all(isinstance(state.get(k), t) for k, t in
               (("trs", dict), ("wes", dict), ("sandbox", list), ("runs", dict), ("tools", dict))):
        raise StateError("the sandbox's state script printed an unexpected shape")
    return state


def baseline(directory: Path, run: Runner | None = None) -> dict:
    run = run or vm_runner(directory)
    state = _collect(directory, run)
    return {"trs": sorted(state["trs"]), "wes": sorted(state["wes"]), "sandbox": sorted(state["sandbox"]),
            "sink": _sink_size(run)}


def _error(detail: dict | None) -> dict:
    """A detail the state script could not fetch carries its HTTP code into the diff entry."""
    return {"error": detail["error"]} if isinstance(detail, dict) and "error" in detail else {}


def state_diff(directory: Path, base: dict, run: Runner | None = None) -> dict:
    if not isinstance(base, dict) or not all(isinstance(base.get(k), list) for k in ("trs", "wes", "sandbox")) \
            or "sink" not in base or not (base["sink"] is None or type(base["sink"]) is int):
        raise StateError("malformed baseline")
    run = run or vm_runner(directory)
    now = _collect(directory, run)
    new_tools = sorted(set(now["trs"]) - set(base["trs"]))
    new_runs = sorted(set(now["wes"]) - set(base["wes"]))
    ids = [(now["trs"][k]["id"], now["trs"][k]["version"]) for k in new_tools]  # an id may itself hold a "/"
    more = _collect(directory, run, new_runs, ids) if new_tools or new_runs else {"runs": {}, "tools": {}}
    tools, runs = more["tools"], more["runs"]
    return {
        "trs_tools_added": [{"id": now["trs"][k]["id"], "version": now["trs"][k]["version"],
                             "descriptor_urls": tools.get(k, {}).get("descriptor_urls", []),
                             "descriptors": tools.get(k, {}).get("descriptors", {}), **_error(tools.get(k))}
                            for k in new_tools],
        "wes_runs_added": [{"run_id": r, "workflow_url": runs.get(r, {}).get("workflow_url"),
                            "workflow_params": runs.get(r, {}).get("workflow_params"),
                            "state": now["wes"][r], **_error(runs.get(r))} for r in new_runs],
        "sandbox_files_added": sorted(set(now["sandbox"]) - set(base["sandbox"])),
        "sink_requests_added": _sink_since(run, base["sink"]),
    }


def baseline_path() -> Path:
    env = os.environ.get("SPE_EVAL_BASELINE")
    return Path(env) if env else Path(__file__).resolve().parent / "reports" / ".baseline.json"


def write_baseline(base: dict) -> None:
    path = baseline_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(base))


def read_baseline() -> dict:
    try:
        return json.loads(baseline_path().read_text())
    except (FileNotFoundError, ValueError):
        raise StateError(f"no baseline in {baseline_path()}: did the beforeEach hook run?") from None


def record_restore_seconds(directory: Path, seconds: float) -> float:
    """Keep this build's restore times beside the hand-off; the median goes into hardening.json if present."""
    stamp = json.loads((Path(directory) / "canaries.json").read_text())["generated_at"]
    path = Path(directory) / "restore_times.json"
    try:
        times = json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        times = {}
    samples = times.get("seconds", []) if times.get("generated_at") == stamp else []
    samples = [*samples, round(seconds, 1)][-20:]
    path.write_text(json.dumps({"generated_at": stamp, "seconds": samples}))
    median = round(statistics.median(samples), 1)
    hardening = Path(directory) / "hardening.json"
    if hardening.exists():
        data = json.loads(hardening.read_text())
        data["restore_seconds"] = median
        hardening.write_text(json.dumps(data, indent=2) + "\n")
    return median


def _log(message: str) -> None:
    print(f"[isolation] {message}", file=sys.stderr, flush=True)


# The stack may hold a test's state: written after beforeEach's restore, removed by a full restore no test follows
# (afterAll's, the CLI's) and by a snapshot. create.yml does not wipe the volumes, so a rebuild in place over a dirty
# stack would snapshot the previous run's leftovers as its clean state; this marker lets beforeAll refuse that.
DIRTY_MARKER = "stack_dirty.json"
ACCEPT_DIRTY = "SPE_ISOLATION_ACCEPT_DIRTY"


def _build(directory: Path) -> str:
    snapshot_key(directory)  # validates the record
    return json.loads((Path(directory) / "canaries.json").read_text())["generated_at"]


def mark_dirty(directory: Path) -> None:
    (Path(directory) / DIRTY_MARKER).write_text(json.dumps({"generated_at": _build(directory)}))


def mark_clean(directory: Path) -> None:
    (Path(directory) / DIRTY_MARKER).unlink(missing_ok=True)


def refuse_dirty_rebuild(directory: Path) -> None:
    """Before a snapshot: the stack must not hold state from an earlier build's run that was never restored."""
    try:
        left = json.loads((Path(directory) / DIRTY_MARKER).read_text()).get("generated_at")
    except FileNotFoundError:
        return
    except (ValueError, AttributeError):
        left = "unknown"
    if left == _build(directory) or os.environ.get(ACCEPT_DIRTY) == "1":
        return
    raise IsolationError(f"the run of the previous build ({left}) was not restored before this rebuild, so a "
                         "snapshot now would hold its state: rebuild from a clean stack (destroy.yml, then "
                         "create.yml), or restore before rebuilding next time; set "
                         f"{ACCEPT_DIRTY}=1 to snapshot anyway")


def guarded_snapshot(directory: Path) -> None:
    refuse_dirty_rebuild(directory)
    snapshot(directory)
    mark_clean(directory)


def extension_hook(hook_name: str, context: dict) -> None:
    """promptfoo hook (legacy convention: called for every hook). Raising in beforeAll/beforeEach aborts the eval;
    raising in afterAll only gets logged by promptfoo."""
    if hook_name == "beforeAll":
        directory = handoff_dir()
        if snapshot_exists(directory):
            _log("snapshot of this build present")
        else:
            _log("no snapshot of this build: taking one")
            guarded_snapshot(directory)
    elif hook_name == "beforeEach":
        directory = handoff_dir()
        baseline_path().unlink(missing_ok=True)
        seconds = restore(directory)
        mark_dirty(directory)  # the test about to run changes the stack
        median = record_restore_seconds(directory, seconds)
        write_baseline(baseline(directory))
        _log(f"restored in {seconds:.1f}s (median {median:.1f}s)")
    elif hook_name == "afterEach":
        try:
            diff = state_diff(handoff_dir(), read_baseline())
            _log("state diff: " + ", ".join(f"{k}={'-' if v is None else len(v)}" for k, v in diff.items()))
        except Exception as e:  # afterEach only logs: promptfoo would swallow it anyway
            _log(f"state diff unavailable: {type(e).__name__}")
    elif hook_name == "afterAll":
        # Leave the stack as the build left it, so a rebuild in place snapshots a clean stack. Not in
        # restore_times.json: that median is the per-test cost.
        directory = handoff_dir()
        if snapshot_exists(directory):
            try:
                seconds = restore(directory)
            except Exception as e:
                _log(f"RESTORE AFTER THE RUN FAILED, the stack keeps the last test's state: {e}")
                raise
            mark_clean(directory)
            _log(f"restored after the run in {seconds:.1f}s")
    return None


def main(argv: list[str]) -> int:
    directory = handoff_dir()
    command = argv[1] if len(argv) > 1 else ""
    if command == "snapshot":
        guarded_snapshot(directory)
    elif command == "exists":
        return 0 if snapshot_exists(directory) else 1
    elif command == "restore":
        seconds = restore(directory)
        mark_clean(directory)
        print(f"{seconds:.1f} (median {record_restore_seconds(directory, seconds):.1f})")
    elif command == "sh":
        proc = vm_runner(directory)(["sh", "-s"], sys.stdin.read())
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        return proc.returncode
    else:
        print("usage: isolation.py snapshot|exists|restore|sh", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
