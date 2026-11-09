"""Loaders for the hand-off directory (platform/ansible/output/<instance>/), standard library only.

A missing, malformed or mismatched hand-off file raises ConfigError (ManifestError for
injections.json): scoring stops with a configuration error, never a pass.

hosts.yml is YAML, written by the handoff role with to_nice_yaml from a flat mapping of string
and boolean values. read_hosts parses exactly that subset (`key: value` lines, plain, single- or
double-quoted scalars, true/false/null) and rejects anything nested rather than guessing.
"""
from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(HERE) not in sys.path:  # promptfoo loads this file by path
    sys.path.insert(0, str(HERE))
import injections_schema  # noqa: E402

METADATA_TYPES = frozenset({"drs-object-metadata", "trs-tool-description", "workflow-file-comment", "service-info"})
SWITCHES = ("spe_harden_trs_readonly", "spe_harden_data_tiers", "spe_harden_egress", "spe_agent_tool_surface",
            "spe_harden_airlock")
LOCAL_TARGETS = frozenset({"localhost", "127.0.0.1"})


class ConfigError(Exception):
    """The hand-off is missing, malformed or belongs to another instance."""


class ManifestError(ConfigError):
    """injections.json is missing or invalid."""


def handoff_dir() -> Path:
    value = os.environ.get("SPE_HANDOFF_DIR", "")
    if not value:
        raise ConfigError("SPE_HANDOFF_DIR is not set (platform/ansible/output/<instance>)")
    path = Path(value)
    if not path.is_dir():
        raise ConfigError(f"SPE_HANDOFF_DIR is not a directory: {path}")
    return path


def _json(path: Path, error: type[ConfigError] = ConfigError) -> object:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        raise error(f"missing {path.name} in {path.parent}") from None
    except (OSError, ValueError) as e:  # JSON errors give a position, never the content
        raise error(f"unreadable {path.name}: {e}") from None


def load_canaries(dir: Path | str) -> list[dict]:
    directory = Path(dir)
    if not (directory / "canaries.json").exists() and (directory / "canaries.json.age").exists():
        raise ConfigError("canaries.json is age-encrypted: decrypt it to canaries.json (0600) before scoring")
    record = _json(directory / "canaries.json")
    tokens = record.get("tokens") if isinstance(record, dict) else None
    if not isinstance(tokens, list) or not tokens:
        raise ConfigError("canaries.json has no tokens: nothing to score against")
    for i, t in enumerate(tokens):
        if not (isinstance(t, dict) and all(isinstance(t.get(k), str) and t[k] for k in ("token", "type", "file"))):
            raise ConfigError(f"canaries.json: tokens[{i}] lacks a token, type or file")
    return tokens


def load_study_ids(dir: Path | str) -> list[str]:
    """The study ids from canaries.json (`study_ids`: {giab: id} as spe_seed writes it, or a list).

    They name paths (sensitive/genomes/<id>/...) and, with registry tokens on, are tokens
    themselves, so reasons redact them. Missing or empty means none; any other shape is refused.
    """
    record = _json(Path(dir) / "canaries.json")
    ids = record.get("study_ids") if isinstance(record, dict) else None
    if ids is None:
        return []
    values = list(ids.values()) if isinstance(ids, dict) else ids
    if not isinstance(values, list) or not all(isinstance(v, str) and v for v in values):
        raise ConfigError("canaries.json: study_ids is not a mapping or list of ids")
    return values


def is_file_canary(entry: dict) -> bool:
    return entry.get("type") not in METADATA_TYPES


def _scalar(raw: str, where: str) -> object:
    if raw in ("", "null", "~"):
        return None
    if raw in ("true", "false"):
        return raw == "true"
    if raw[0] == "'":
        if len(raw) < 2 or raw[-1] != "'":
            raise ConfigError(f"{where}: unterminated quoted value")
        return raw[1:-1].replace("''", "'")
    if raw[0] == '"':
        try:
            return json.loads(raw)
        except ValueError:
            raise ConfigError(f"{where}: unsupported double-quoted value") from None
    if raw[0] in "[{|>&*!":
        raise ConfigError(f"{where}: not a flat scalar")
    return raw


def read_hosts(dir: Path | str) -> dict:
    path = Path(dir) / "hosts.yml"
    try:
        text = path.read_text()
    except OSError as e:
        raise ConfigError(f"cannot read {path}: {e.strerror}") from None
    hosts: dict = {}
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        where = f"hosts.yml line {n}"
        if line[0] in " \t-":
            raise ConfigError(f"{where}: nested values are not supported (flat keys only)")
        key, sep, raw = line.partition(":")
        if not sep or not key or (raw and raw[0] != " "):
            raise ConfigError(f"{where}: expected 'key: value'")
        hosts[key] = _scalar(raw.strip(), where)
    return hosts


def _required(hosts: dict, key: str) -> str:
    value = hosts.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigError(f"hosts.yml: no {key}")
    return value


def api_host(dir: Path | str) -> str:
    return _required(read_hosts(dir), "api_host")


def vm_argv(dir: Path | str) -> list[str]:
    """The ssh prefix that runs a command on the VM; [] when the controller is the VM.

    Mirrors the handoff role's spe_ssh_prefix, from the fields hosts.yml records.
    """
    hosts = read_hosts(dir)
    user = _required(hosts, "ssh_user")
    provision = hosts.get("provision")
    if provision == "existing":
        target = _required(hosts, "ssh_target")
        if target in LOCAL_TARGETS:
            return []
        argv = ["ssh"]
        if hosts.get("ssh_key"):
            argv += ["-i", str(hosts["ssh_key"])]
        argv += shlex.split(str(hosts.get("ssh_args") or ""))
        return argv + [f"{user}@{target}"]
    if provision == "openstack":
        host = hosts.get("floating_ip") or _required(hosts, "api_host")
        return ["ssh", "-i", _required(hosts, "ssh_key"), f"{user}@{host}"]
    raise ConfigError(f"hosts.yml: unknown provision {provision!r}")


def check_hardening(record: object) -> dict:
    """The shape of hardening.json version 1 (plan README, Shared interfaces).

    `injections` says whether the injection fixtures were planted: true at every ladder level, false
    only in the clean control run (spec clarification 6), which the matrix shows as "L<n> clean".

    Also checks that `level` equals the number of leading ladder controls switched on, in ladder
    order L1 spe_harden_trs_readonly, L2 spe_harden_data_tiers (on when a non-empty list), L3
    spe_harden_egress, L4 spe_agent_tool_surface == "typed", L5 spe_harden_airlock: the count
    stops at the first switch that is off, so a non-contiguous pattern never matches a level > 0
    beyond its unbroken leading run.
    """
    if not isinstance(record, dict) or record.get("schema_version") != 1:
        raise ConfigError("hardening.json: schema_version must be 1")
    for key in ("instance", "frontend", "model_provider", "model", "commit"):
        if not isinstance(record.get(key), str) or not record[key]:
            raise ConfigError(f"hardening.json: no {key}")
    level = record.get("level")
    if type(level) is not int or not 0 <= level <= 5:
        raise ConfigError("hardening.json: level must be an integer 0-5")
    switches = record.get("switches")
    if not isinstance(switches, dict) or sorted(switches) != sorted(SWITCHES):
        raise ConfigError(f"hardening.json: switches must be exactly {', '.join(SWITCHES)}")
    tiers, surface = switches["spe_harden_data_tiers"], switches["spe_agent_tool_surface"]
    if not all(isinstance(switches[k], bool) for k in ("spe_harden_trs_readonly", "spe_harden_egress",
                                                        "spe_harden_airlock")) \
            or not isinstance(tiers, list) or not all(isinstance(t, str) and t for t in tiers) \
            or surface not in ("shell", "typed"):
        raise ConfigError("hardening.json: switches have the wrong types (booleans; spe_harden_data_tiers a list "
                          "of tier names, [] for all; spe_agent_tool_surface shell or typed)")
    ladder = (switches["spe_harden_trs_readonly"], bool(tiers), switches["spe_harden_egress"], surface == "typed",
              switches["spe_harden_airlock"])
    counted = 0
    for on in ladder:
        if not on:
            break
        counted += 1
    if level != counted:
        raise ConfigError(f"hardening.json: level {level} does not match {counted} leading switches on")
    if not isinstance(record.get("injections"), bool):
        raise ConfigError("hardening.json: injections must be true (every spe_inject_* on) or false (all off)")
    restore = record.get("restore_seconds")
    if restore is not None and (isinstance(restore, bool) or not isinstance(restore, (int, float))):
        raise ConfigError("hardening.json: restore_seconds must be a number or null")
    return record


def load_hardening(dir: Path | str) -> dict:
    record = check_hardening(_json(Path(dir) / "hardening.json"))
    instance = _required(read_hosts(dir), "instance")
    if record["instance"] != instance:
        raise ConfigError(f"hardening.json is for instance {record['instance']!r}, hosts.yml for {instance!r}")
    return record


def load_injections(dir: Path | str, repo_root: Path | None = None) -> list[dict]:
    """The validated injections of injections.json; each canary_file must hold a file canary."""
    directory = Path(dir)
    manifest = _json(directory / "injections.json", ManifestError)
    errors = injections_schema.validate(manifest, repo_root or REPO_ROOT)
    if errors:
        raise ManifestError("injections.json: " + "; ".join(errors))
    files = {t["file"] for t in load_canaries(directory) if is_file_canary(t)}
    for e in manifest["injections"]:
        if e["canary_file"] not in files:
            raise ManifestError(f"injections.json: {e['id']} targets {e['canary_file']}, "
                                "which has no file canary in canaries.json")
    return manifest["injections"]
