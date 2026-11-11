"""`spe-eval`'s core library (experiments spec part 03, `docs/specs/2026-11-10-experiments-design/`):
experiments, arms, the suite config, run ids and the lock. Standard library plus PyYAML only (the
VM has `python3-yaml`); the only repository imports are `validate` (repo root) and
`injections_schema` (`platform/promptfoo-evals/`), both read-only siblings of the same clone, not
new dependencies.

Used by the `spe-eval` CLI (`platform/instance/spe-eval`) and, for the lock, by `spe-apply` (in
bash, mirroring `Lock`'s file format):

    - `load_experiment`, `default_experiment_name`, `load_local_vars`, `check_build_matches`:
      decision 7, which experiment a bare `spe-eval` command means and whether it still matches
      this build.
    - `experiment_arms`, `arm_mitigations`, `arm_vars`, `write_json`: decision 9, the `-e` values
      for one arm, as the JSON file `spe-apply ... -e @<path>` passes.
    - `suite_config`: spec part 03's R1, `agent.yaml` unchanged for an experiment with no tests
      of its own, else a generated `suite.yaml` with absolute paths.
    - `run_id`, `iso_now`, `spe_eval_home`, `reports_dir`: decision 7's run id, the `run.json`/
      `windows.jsonl` timestamp format, and the reports layout.
    - `promptfoo_env`: the environment `run.sh`'s promptfoo calls need, from the VM-local
      hand-off (task 5 review item 1).
    - `Lock`, `LockHeld`: decision 11, `~/spe-eval/lock`.
    - `append_jsonl`, `discover_runs`, `run_entry`, `read_progress`: `spe-eval status`/`wait`/
      `runs`'s own reading of `~/spe-eval/reports/`, `windows.jsonl` and the progress file R3
      writes.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

_HERE = Path(__file__).resolve()
OWN_REPO_ROOT = _HERE.parents[2]  # platform/instance/spe_eval.py -> the repository root
_PROMPTFOO_DIR = OWN_REPO_ROOT / "platform" / "promptfoo-evals"
for _p in (str(OWN_REPO_ROOT), str(_PROMPTFOO_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import validate  # noqa: E402  (repo root: EXPERIMENT_PARAMETER_ANSIBLE_NAMES, main.tf's own mapping)
import injections_schema  # noqa: E402  (promptfoo-evals: switches(), built from the fixtures.json catalogue)


class ConfigError(Exception):
    """A usage or configuration problem (CLI exit 2): a missing or malformed file, an unknown
    id, or an experiment whose creation-time settings do not match this build (decision 7)."""


def repo_dir() -> Path:
    """The clone `spe-eval` reads `experiments/`, `mitigations/` and `instances/local.yml`
    from: `SPE_REPO_DIR`, or the repository containing this script (03, *Which experiment*)."""
    value = os.environ.get("SPE_REPO_DIR")
    return Path(value) if value else OWN_REPO_ROOT


# --- which experiment (decision 7) --------------------------------------------------------------

def load_experiment(name: str, repo_root: Path | None = None) -> dict:
    """`experiments/<name>.yml`, parsed (01-experiment-model.md, *Experiments*)."""
    repo_root = repo_root or repo_dir()
    path = repo_root / "experiments" / f"{name}.yml"
    try:
        text = path.read_text()
    except OSError as e:
        raise ConfigError(f"{path}: {e.strerror or e}") from None
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: not a YAML mapping")
    return data


def load_local_vars(repo_root: Path | None = None) -> dict:
    """`platform/ansible/instances/local.yml`, the build's own values (written at creation for
    `spe-apply`; decision 7 compares an experiment's creation-time settings against it)."""
    repo_root = repo_root or repo_dir()
    path = repo_root / "platform" / "ansible" / "instances" / "local.yml"
    try:
        text = path.read_text()
    except OSError as e:
        raise ConfigError(
            f"{path}: {e.strerror or e}: this instance was built before local re-apply existed; "
            "start a new workspace") from None
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: not a YAML mapping")
    return data


def default_experiment_name(local_vars: dict) -> str:
    """The experiment the workspace was built with (`spe_experiment` in `local_vars`), the
    default `spe-eval` command target when none is named (03, *Which experiment*)."""
    name = local_vars.get("spe_experiment")
    if not name:
        raise ConfigError("instances/local.yml has no spe_experiment: this is not a spe-experiments build")
    return name


# decision 7: not creation-time choices of the experiment itself (`seed` is not even a key of
# validate.EXPERIMENT_PARAMETER_ANSIBLE_NAMES, so it needs no entry here).
_SKIP_CREATION_TIME_PARAMETERS = frozenset({"experiment", "mitigations"})

# These three hold the creation form's own list order, which a hand-edited build need not match
# (task 3 review, minor 1): compared as sets, not sequences.
_ORDER_INSENSITIVE_PARAMETERS = frozenset({"samples", "tiers", "workflows"})


def check_creation_time(experiment: dict, local_vars: dict, repo_root: Path | None = None) -> list[str]:
    """The Ansible keys where `experiment`'s `parameters` or `vars` differ from the build's own
    (`local_vars`, from `instances/local.yml`), decision 7. Uses
    `validate.EXPERIMENT_PARAMETER_ANSIBLE_NAMES`, the mapping `experiments-template/main.tf` uses
    to turn a parameter into an Ansible variable, leaving out `experiment` and `mitigations`.
    `canaries` has no single Ansible name: it expands to one `spe_canary_<type>` key per type the
    build actually has (read from `local_vars`'s own keys, so every type the build supports is
    checked). A parameter with no persisted Ansible name at all (`flavor`: VM sizing, done once at
    creation) is skipped, since `local_vars` never holds anything to compare it to. `samples`,
    `tiers` and `workflows` are compared as sets, not sequences, so a build whose form held the
    same list in a different order is not a false mismatch.

    `experiment["experiment"]["injections"]` (not a `parameters` key, so the loop above never
    reaches it) is checked the same way as `canaries`: every catalogue switch this experiment names
    must be `true` in `local_vars` and every other one `false` (task 5 review item 2) -- the build's
    own `spe_inject_*` switches (`roles/repo/tasks/main.yml`'s `spe_local_vars_fixture_switches`,
    persisted for every fixture whether an experiment names it or not), compared against
    `injections_schema.switches` for this experiment's own list. A switch missing from `local_vars`
    (a build from before this comparison existed) is treated as `false`, its Ansible default.
    """
    params = experiment.get("parameters") or {}
    mismatches: list[str] = []
    for key, ansible_name in validate.EXPERIMENT_PARAMETER_ANSIBLE_NAMES.items():
        if key in _SKIP_CREATION_TIME_PARAMETERS or key not in params:
            continue
        if key == "canaries":
            selected = set(params["canaries"] or [])
            for local_key in local_vars:
                if not local_key.startswith("spe_canary_"):
                    continue
                canary_type = local_key[len("spe_canary_"):]
                if bool(local_vars[local_key]) != (canary_type in selected):
                    mismatches.append(local_key)
            continue
        if ansible_name is None or ansible_name not in local_vars:
            continue
        if key in _ORDER_INSENSITIVE_PARAMETERS:
            if sorted(local_vars[ansible_name] or []) != sorted(params[key] or []):
                mismatches.append(ansible_name)
            continue
        if local_vars[ansible_name] != params[key]:
            mismatches.append(ansible_name)
    for key, value in (experiment.get("vars") or {}).items():
        if local_vars.get(key) != value:
            mismatches.append(key)
    injection_ids = (experiment.get("experiment") or {}).get("injections") or []
    expected_switches = injections_schema.switches(injection_ids, repo_root or repo_dir())
    for switch, expected in expected_switches.items():
        if bool(local_vars.get(switch, False)) != expected:
            mismatches.append(switch)
    return sorted(set(mismatches))


def check_build_matches(experiment: dict, local_vars: dict, repo_root: Path | None = None) -> None:
    """Raises `ConfigError` naming every key `check_creation_time` finds differing, saying to
    build fresh from the branch template (decision 7); returns normally when they all match."""
    mismatches = check_creation_time(experiment, local_vars, repo_root)
    if mismatches:
        raise ConfigError(
            "this build does not match the experiment's creation-time settings: "
            + ", ".join(mismatches)
            + " differ; build a fresh workspace from its branch template (05, step 5)")


# --- arms (decision 9) ----------------------------------------------------------------------

def load_mitigations(repo_root: Path | None = None) -> dict[str, dict]:
    """`mitigations/<id>.yml`, by id, skipping `status: planned` ones (no `on`/`off` to apply)."""
    repo_root = repo_root or repo_dir()
    mitigations: dict[str, dict] = {}
    for path in sorted((repo_root / "mitigations").glob("*.yml")):
        meta = yaml.safe_load(path.read_text())
        if not isinstance(meta, dict) or meta.get("status") == "planned":
            continue
        mitigations[meta["id"]] = meta
    return mitigations


def experiment_arms(experiment: dict) -> tuple[str, ...]:
    """This experiment's arms (decision 9): `baseline` alone when there is no mitigation under
    test (`mitigation: null`), else `baseline` and `mitigated`."""
    if experiment["experiment"].get("mitigation") is None:
        return ("baseline",)
    return ("baseline", "mitigated")


def arm_mitigations(experiment: dict, arm: str) -> list[str]:
    """The mitigation ids on in `arm`, in declared order (`base`, then the one under test for
    `mitigated`). Raises `ValueError` for an arm this experiment does not have (e.g. `mitigated`
    on a one-arm experiment such as `ladder-l0`)."""
    arms = experiment_arms(experiment)
    if arm not in arms:
        raise ValueError(f"{arm!r}: not an arm of this experiment (has {', '.join(arms)})")
    base = list(experiment["experiment"].get("base") or [])
    if arm == "baseline":
        return base
    return base + [experiment["experiment"]["mitigation"]]


def arm_vars(experiment: dict, arm: str, repo_root: Path | None = None) -> dict:
    """The `-e` values for one arm (03, step 2; decision 9): every mitigation file's `on` for the
    ids in this arm, `off` for every other mitigation file (so the arm is exactly its set,
    whatever a mitigation selected on the form but outside the experiment was), plus
    `spe_mitigations` (the arm's set), `spe_experiment`, and every injection switch from
    `injections_schema.switches` (the same in both arms, 01, *Attacks*)."""
    repo_root = repo_root or repo_dir()
    on_ids = set(arm_mitigations(experiment, arm))
    values: dict = {}
    for mitigation_id, meta in load_mitigations(repo_root).items():
        values.update(meta["on"] if mitigation_id in on_ids else meta["off"])
    values["spe_mitigations"] = arm_mitigations(experiment, arm)
    values["spe_experiment"] = experiment["parameters"]["experiment"]
    values.update(injections_schema.switches(experiment["experiment"].get("injections") or [], repo_root))
    return values


def write_json(values: dict, path: Path) -> Path:
    """Write `values` as the JSON file `spe-apply ... -e @<path>` passes (03, step 2)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values, indent=2, sort_keys=True) + "\n")
    return path


# --- the suite (R1) ------------------------------------------------------------------------------

_FILE_URI = re.compile(r"^file://([^:]+)(:.*)?$")


def _absolutize_file_uris(obj, base_dir: Path):
    """Every `file://<path>[:<suffix>]` string in `obj` (recursively, through dicts and lists),
    `<path>` made absolute under `base_dir` if it is not already: a `suite.yaml` written outside
    `platform/promptfoo-evals/` still finds `agui_provider.py`, `isolation.py`, `asserts.py` and
    `metrics.py` (R1, "paths in it are absolute, so it runs from any directory")."""
    if isinstance(obj, dict):
        return {k: _absolutize_file_uris(v, base_dir) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_absolutize_file_uris(v, base_dir) for v in obj]
    if isinstance(obj, str):
        m = _FILE_URI.match(obj)
        if m:
            rel, suffix = m.group(1), m.group(2) or ""
            path = Path(rel)
            if not path.is_absolute():
                path = (base_dir / path).resolve()
            return f"file://{path}{suffix}"
    return obj


def _load_tests(promptfoo_dir: Path) -> dict[str, dict]:
    """Every test across `tests/*.yaml` and `tests/experiments/*.yaml`, by its `metadata.id`
    (01, *Tests*). The first file to define an id wins (the ladder's own files are read first), so
    a clash is silently resolved rather than raised: the catalogue's own tests stay canonical."""
    tests: dict[str, dict] = {}
    paths = sorted(promptfoo_dir.glob("tests/*.yaml")) + sorted(promptfoo_dir.glob("tests/experiments/*.yaml"))
    for path in paths:
        cases = yaml.safe_load(path.read_text()) or []
        for case in cases:
            tid = (case.get("metadata") or {}).get("id")
            if tid:
                tests.setdefault(tid, case)
    return tests


def suite_config(experiment: dict, out_dir: Path, repo_root: Path | None = None) -> Path:
    """The agent suite to run for this experiment (spec part 03, R1). With no `tests` named,
    `agent.yaml` unchanged (the ladder's own suite, byte for byte, so its 13 tests stay
    comparable). With tests named: `agent.yaml`'s settings with `tests` replaced by those ids
    (looked up across `tests/*.yaml` and `tests/experiments/*.yaml`; an unknown id raises
    `ConfigError`) plus every test of the `utility` group not already named, written as
    `<out_dir>/suite.yaml` with every `file://` path made absolute. Returns the path to run.
    """
    repo_root = repo_root or repo_dir()
    promptfoo_dir = repo_root / "platform" / "promptfoo-evals"
    agent_yaml = promptfoo_dir / "agent.yaml"
    test_ids = (experiment.get("experiment") or {}).get("tests") or []
    if not test_ids:
        return agent_yaml
    config = yaml.safe_load(agent_yaml.read_text())
    all_tests = _load_tests(promptfoo_dir)
    unknown = [tid for tid in test_ids if tid not in all_tests]
    if unknown:
        raise ConfigError(f"unknown test id(s): {', '.join(unknown)}")
    chosen = [all_tests[tid] for tid in test_ids]
    chosen_ids = set(test_ids)
    for tid, case in all_tests.items():
        if tid not in chosen_ids and (case.get("metadata") or {}).get("group") == "utility":
            chosen.append(case)
    config["tests"] = chosen
    config = _absolutize_file_uris(config, promptfoo_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "suite.yaml"
    out_path.write_text(yaml.safe_dump(config, sort_keys=False))
    return out_path


# --- run id and reports layout (decision 7) -------------------------------------------------

def run_id() -> str:
    """A run's id, fixed when the lock is taken (03, *Every run is kept*): UTC `YYYYMMDDTHHMMSSZ`."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def iso_now() -> str:
    """UTC timestamp in `run.sh`'s own format (`date -u +%Y-%m-%dT%H:%M:%SZ`), for `run.json`'s
    `started`/`ended` and `windows.jsonl`."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def spe_eval_home(home: Path | None = None) -> Path:
    """`~/spe-eval` (03, *The hand-off on the VM*; decision 11, the lock): everything `spe-eval`
    keeps on the VM. `home` overrides `Path.home()`, for tests."""
    return (home or Path.home()) / "spe-eval"


def reports_dir(experiment_name: str, run_id_: str, arm: str, home: Path | None = None) -> Path:
    """`~/spe-eval/reports/<experiment>/<run id>/<arm>/` (03, *Every run is kept*)."""
    return spe_eval_home(home) / "reports" / experiment_name / run_id_ / arm


# --- run.sh's environment (03, *The hand-off on the VM*; task 5 review item 1) ----------------

def promptfoo_env(handoff_dir: Path, config_dir: Path, progress_path: Path, base_env: dict | None = None) -> dict:
    """The environment `run.sh`'s promptfoo calls need, built from the VM-local hand-off
    (`handoff_dir`, never the controller's `SPE_HANDOFF_DIR` tunnel path): `PROMPTFOO_CONFIG_DIR`
    and `SPE_EVAL_PROGRESS` (R3), `SPE_AGENT_URL` (`handoff_dir`'s own `hosts.yml`, its `agent_url`
    key, left unset when that build has no `agui` frontend and hosts.yml has none), and
    `SPE_AGENT_API_KEY_FILE`/`SPE_LLM_API_KEY_FILE` as paths into `handoff_dir` -- this function
    never opens either key file, so no key value is ever read here, let alone printed. First drops
    `SPE_AGENT_API_KEY`, `SPE_LLM_API_KEY`, `SPE_AGENT_URL` and `SPE_HANDOFF_DIR` if `base_env`
    (ordinarily the caller's own inherited environment) carries any of them: `asserts._secret`
    prefers the bare key over its `_FILE` variant, and the controller's own docs tell an operator
    to export `SPE_LLM_API_KEY` by hand, so a shell that still has it set must not override the VM
    hand-off this function is building (task 5 review, Minor 1). Also disables promptfoo's own
    telemetry, sharing and update check, as `platform/promptfoo-evals/README.md`'s run steps set
    them by hand, and puts `/usr/local/bin` (node, npx, uv: the `spe_eval` role's own symlinks) at
    the front of `PATH`, so `run.sh` finds them whatever the caller's own PATH already has (e.g. a
    `systemd --user` unit's own minimal one, R5).
    """
    handoff_dir = Path(handoff_dir)
    env = dict(base_env if base_env is not None else os.environ)
    for stale in ("SPE_AGENT_API_KEY", "SPE_LLM_API_KEY", "SPE_AGENT_URL", "SPE_HANDOFF_DIR"):
        env.pop(stale, None)
    hosts_path = handoff_dir / "hosts.yml"
    if hosts_path.is_file():
        hosts = yaml.safe_load(hosts_path.read_text()) or {}
        agent_url = hosts.get("agent_url")
        if agent_url:
            env["SPE_AGENT_URL"] = agent_url
    env["SPE_AGENT_API_KEY_FILE"] = str(handoff_dir / "agent_api_key")
    env["SPE_LLM_API_KEY_FILE"] = str(handoff_dir / "llm_api_key")
    env["PROMPTFOO_DISABLE_TELEMETRY"] = "1"
    env["PROMPTFOO_DISABLE_SHARING"] = "1"
    env["PROMPTFOO_DISABLE_UPDATE"] = "1"
    env["PROMPTFOO_CONFIG_DIR"] = str(config_dir)
    env["SPE_EVAL_PROGRESS"] = str(progress_path)
    path_parts = env.get("PATH", "").split(os.pathsep) if env.get("PATH") else []
    if "/usr/local/bin" not in path_parts:
        env["PATH"] = os.pathsep.join(["/usr/local/bin", *path_parts]) if path_parts else "/usr/local/bin"
    return env


# --- the lock (decision 11) -----------------------------------------------------------------

class LockHeld(Exception):
    """Another process holds the lock; `token` is its holder's token, read from the lock file
    (`None` when the file could not be read, which should not happen once `flock` itself refused)."""

    def __init__(self, token: str | None):
        self.token = token
        super().__init__(
            f"spe-eval run {token} holds the lock; wait for it (spe-eval wait)" if token
            else "the lock is held; wait for it (spe-eval wait)")


class Lock:
    """`~/spe-eval/lock` (`flock`): one `spe-eval run` or `arm` at a time per VM (decision 11).
    `spe-apply` enforces the same file in bash, refusing unless `SPE_EVAL_LOCK` equals `holder()`."""

    def __init__(self, path: Path):
        self.path = path
        self._fd: int | None = None

    def holder(self) -> str | None:
        """The token in the lock file, reported only when the lock is actually held: a missing
        or empty file is "not held" (03), and so is a non-empty file whose `flock` a non-blocking
        probe can still take -- a token left behind by a process that died before `release()`
        ever ran (e.g. SIGKILLed past its SIGTERM grace period), rather than trusting the file's
        text alone (task 5 review, Important 4a)."""
        try:
            text = self.path.read_text().strip()
        except FileNotFoundError:
            return None
        if not text:
            return None
        try:
            fd = os.open(self.path, os.O_RDWR)
        except FileNotFoundError:
            return None
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return text  # genuinely held by another process
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
            return None  # a stale token in a file nothing holds: "free"
        finally:
            os.close(fd)

    def acquire(self, token: str) -> None:
        """Take the lock and write `token` (a run id) into it. Raises `LockHeld`, naming the
        current holder's token, if another process already holds it."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        # A few short retries: `holder()`'s own probe (`status`, `wait`'s polling) takes the free lock
        # for an instant, and must not make a real acquire fail (re-review N3).
        for attempt in range(5):
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if attempt == 4:
                    os.close(fd)
                    raise LockHeld(self.holder()) from None
                time.sleep(0.1)
        os.ftruncate(fd, 0)
        os.write(fd, token.encode())
        os.fsync(fd)
        self._fd = fd

    def release(self) -> None:
        """Release the lock (03, step 5) and clear the file, so a stale token is never read as
        held by a later `holder()` call. A no-op if this `Lock` never acquired it."""
        if self._fd is None:
            return
        os.ftruncate(self._fd, 0)
        fcntl.flock(self._fd, fcntl.LOCK_UN)
        os.close(self._fd)
        self._fd = None


# --- runs: kept reports, status and the progress file (07, `status`/`wait`/`runs`) -----------

def append_jsonl(path: Path, record: dict) -> None:
    """Append one JSON line to `path` (03, `windows.jsonl`): `{run, experiment, start, end}`, two per run:
    an opening line (`end` null) when it starts and a closing one at its end; per run, the closed line wins."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def discover_runs(home: Path | None = None) -> list[dict]:
    """Every run under `~/spe-eval/reports/<experiment>/<run id>/<arm>/run.json`, newest first
    (07, `spe-eval runs`): `{"run": <id>, "experiment": <name>, "arms": {<arm>: <run.json>}}`. A
    run with no readable `run.json` in any of its arms is left out (nothing to report)."""
    reports_root = spe_eval_home(home) / "reports"
    runs: dict[str, dict] = {}
    if reports_root.is_dir():
        for experiment_dir in sorted(p for p in reports_root.iterdir() if p.is_dir()):
            for run_dir in sorted(p for p in experiment_dir.iterdir() if p.is_dir()):
                arms: dict[str, dict] = {}
                for arm_dir in sorted(p for p in run_dir.iterdir() if p.is_dir()):
                    run_json = arm_dir / "run.json"
                    if not run_json.is_file():
                        continue
                    try:
                        arms[arm_dir.name] = json.loads(run_json.read_text())
                    except ValueError:
                        continue
                if arms:
                    runs[run_dir.name] = {"run": run_dir.name, "experiment": experiment_dir.name, "arms": arms}
    return sorted(runs.values(), key=lambda entry: entry["run"], reverse=True)


def run_entry(home: Path | None, run_id_: str) -> dict | None:
    """The one entry of `discover_runs` whose run id is `run_id_`, or `None`."""
    for entry in discover_runs(home):
        if entry["run"] == run_id_:
            return entry
    return None


def read_progress(path: Path, repeat: int = 1) -> dict:
    """The progress file's numbers (R3, `isolation.py`'s hook): `total` (the suite's test count
    times `repeat`, `None` before the first line), `done` (0 before the first `afterEach`) and
    `last_error` (the most recent test's error, kept rather than cleared by a later passing test,
    so `spe-eval status` still shows why an earlier test failed)."""
    total = None
    done = 0
    last_error = None
    if path.is_file():
        for raw in path.read_text().splitlines():
            try:
                record = json.loads(raw)
            except ValueError:
                continue
            if "total" in record:
                total = record["total"]
            elif "done" in record:
                done = record["done"]
                if record.get("error"):
                    last_error = record["error"]
    return {"total": (total * repeat) if total is not None else None, "done": done, "last_error": last_error}
