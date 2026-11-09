"""promptfoo provider for the controls suite: one probe per test, no model call.

    providers: [{id: "file://controls_provider.py", label: spe-controls}]

Runs probes/<vars.probe>.sh on the instance VM, inside the sandbox (or, for tool-surface and airlock, the agent
container): `<vm_argv> docker exec -i <container> sh -s`, the script on stdin, preceded by `export` lines from
config.env and vars.env. A probe prints `HTTP <code> <label>` per request and, as its last line,
`PROBE <open|closed> <evidence>`, then exits 0; anything else (VM unreachable, timeout, a failed script, no
marker) is state `error`, which no level expects. e2e-exploit prints only sha256 hashes of flag-shaped strings
from the run's stdout; they are compared here with the flag-file canary, so the token never goes to the VM and the
result carries only found / not found. Standard library only.
"""
from __future__ import annotations

import hashlib
import re
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from handoff import ConfigError, handoff_dir, load_canaries, vm_argv  # noqa: E402

PROBES = Path(__file__).resolve().parent / "probes"
CONTAINERS = {"sandbox": "spe-frontend-sandbox-1", "agent": "spe-frontend-agent-1"}
AGENT_PROBES = frozenset({"tool-surface", "airlock"})
PROBE_ID = re.compile(r"[a-z][a-z0-9-]*")
ENV_NAME = re.compile(r"[A-Z_][A-Z0-9_]*")
MARKER = re.compile(r"PROBE (open|closed)(?: (.*))?")
HTTP_LINE = re.compile(r"HTTP (\d{3}) (\S+)")
HASH_LINE = re.compile(r"HASH ([0-9a-f]{64})")
DEFAULT_TIMEOUT = 900.0


def run_subprocess(argv: list[str], stdin: str, timeout: float) -> tuple[int, str, str]:
    try:
        p = subprocess.run(argv, input=stdin, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout:.0f} s"
    except OSError as e:
        return 127, "", f"cannot run {argv[0]}: {e.strerror}"
    return p.returncode, p.stdout, p.stderr


executor = run_subprocess  # the tests replace it


def command(directory: Path, probe: str, env: dict) -> tuple[list[str], str]:
    bad = [k for k in env if not ENV_NAME.fullmatch(str(k))]
    if bad:
        raise ValueError(f"invalid env names {bad}")
    container = CONTAINERS["agent" if probe in AGENT_PROBES else "sandbox"]
    argv = vm_argv(directory) + ["docker", "exec", "-i", container, "sh", "-s"]
    exports = "".join(f"export {k}={shlex.quote(str(v))}\n" for k, v in sorted(env.items()))
    return argv, exports + (PROBES / f"{probe}.sh").read_text()


def parse(code: int, stdout: str, stderr: str) -> dict:
    lines = [line.strip() for line in stdout.splitlines()]
    http = {m[2]: int(m[1]) for line in lines if (m := HTTP_LINE.fullmatch(line))}
    hashes = {m[1] for line in lines if (m := HASH_LINE.fullmatch(line))}
    kept = [line for line in lines if not HASH_LINE.fullmatch(line)]
    last = next((line for line in reversed(lines) if line), "")
    marker = MARKER.fullmatch(last)
    if code != 0 or marker is None:
        stderr_last = (stderr.strip().splitlines() or [None])[-1]
        if stderr_last is not None:
            evidence = f"exit {code}: {stderr_last[:200]}"
        elif marker is not None:
            # the PROBE line is present and last, but the script still exited non-zero.
            evidence = f"exit {code}"
        else:
            evidence = f"exit {code}: no PROBE line as the last line"
        return {"state": "error", "evidence": evidence, "http": http, "hashes": hashes, "kept": kept}
    return {"state": marker[1], "evidence": marker[2] or "", "http": http, "hashes": hashes, "kept": kept}


def flag_found(directory: Path, hashes: set[str]) -> bool:
    flags = [t["token"] for t in load_canaries(directory) if t.get("type") == "flag-file"]
    if not flags:
        raise ConfigError("canaries.json has no flag-file canary")
    return any(hashlib.sha256(f.encode()).hexdigest() in hashes for f in flags)


def call_api(prompt: str, options: dict | None = None, context: dict | None = None) -> dict:
    config = (options or {}).get("config") or {}
    vars_ = (context or {}).get("vars") or {}
    probe = str(vars_.get("probe") or "")
    meta = {"probe": probe, "exit_code": None, "http_codes": {}, "state": "error", "evidence": ""}
    if not PROBE_ID.fullmatch(probe) or not (PROBES / f"{probe}.sh").is_file():
        meta["evidence"] = f"unknown probe {probe!r}"
        return {"output": "", "metadata": meta}
    try:
        directory = handoff_dir()
        argv, script = command(directory, probe, {**(config.get("env") or {}), **(vars_.get("env") or {})})
        timeout = float(config.get("probe_timeout_s", DEFAULT_TIMEOUT))
    except (ConfigError, OSError, ValueError, KeyError) as e:
        meta["evidence"] = f"configuration: {e}"
        return {"output": "", "metadata": meta}
    code, out, err = executor(argv, script, timeout)
    res = parse(code, out, err)
    meta.update(exit_code=code, http_codes=res["http"], state=res["state"], evidence=res["evidence"])
    if probe == "e2e-exploit" and res["state"] == "open":
        try:
            found = flag_found(directory, res["hashes"])
        except (ConfigError, OSError, ValueError, KeyError) as e:
            meta.update(state="error", evidence=f"configuration: {e}")
        else:
            meta.update(state="open" if found else "closed",
                        evidence="flag token found in the run's stdout" if found
                        else "run stdout read, flag token not found")
    return {"output": "\n".join(res["kept"]), "metadata": meta}
