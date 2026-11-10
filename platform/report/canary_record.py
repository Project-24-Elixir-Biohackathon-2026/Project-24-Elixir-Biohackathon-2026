"""Readers for the canary record and the hosts record of the hand-off directory
(platform/ansible/output/<instance>/), standard library only, so the canary hit viewer's watcher can
read them without importing platform/promptfoo-evals (decision 2).

A missing, malformed or mismatched record raises RecordError. hosts.yml is YAML, written by the
handoff role with to_nice_yaml from a flat mapping of string and boolean values and one list of
strings (`frontends`). read_hosts parses exactly that subset (`key: value` lines, plain, single- or
double-quoted scalars, true/false/null; a key with no value followed by `- scalar` lines at column 0,
or `[]`) and rejects anything nested rather than guessing.

Where platform/promptfoo-evals/handoff.py exists (the canary evaluation ladder), it imports
RecordError (as its own ConfigError), _json, _scalar, load_canaries, read_hosts and vm_argv from
here, so its own callers and `ManifestError(ConfigError)` are unchanged.
"""
from __future__ import annotations

import json
import shlex
from pathlib import Path

LOCAL_TARGETS = frozenset({"localhost", "127.0.0.1"})


class RecordError(Exception):
    """The canary record or the hosts record is missing, malformed, or belongs to another instance."""


def _json(path: Path, error: type[RecordError] = RecordError) -> object:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        raise error(f"missing {path.name} in {path.parent}") from None
    except (OSError, ValueError) as e:  # JSON errors give a position, never the content
        raise error(f"unreadable {path.name}: {e}") from None


def load_canaries(dir: Path | str) -> list[dict]:
    directory = Path(dir)
    if not (directory / "canaries.json").exists() and (directory / "canaries.json.age").exists():
        raise RecordError("canaries.json is age-encrypted: decrypt it to canaries.json (0600) before scoring")
    record = _json(directory / "canaries.json")
    tokens = record.get("tokens") if isinstance(record, dict) else None
    if not isinstance(tokens, list) or not tokens:
        raise RecordError("canaries.json has no tokens: nothing to score against")
    for i, t in enumerate(tokens):
        if not (isinstance(t, dict) and all(isinstance(t.get(k), str) and t[k] for k in ("token", "type", "file"))):
            raise RecordError(f"canaries.json: tokens[{i}] lacks a token, type or file")
    return tokens


def _scalar(raw: str, where: str) -> object:
    if raw in ("", "null", "~"):
        return None
    if raw in ("true", "false"):
        return raw == "true"
    if raw[0] == "'":
        if len(raw) < 2 or raw[-1] != "'":
            raise RecordError(f"{where}: unterminated quoted value")
        return raw[1:-1].replace("''", "'")
    if raw[0] == '"':
        try:
            return json.loads(raw)
        except ValueError:
            raise RecordError(f"{where}: unsupported double-quoted value") from None
    if raw[0] in "[{|>&*!":
        raise RecordError(f"{where}: not a flat scalar")
    return raw


def read_hosts(dir: Path | str) -> dict:
    path = Path(dir) / "hosts.yml"
    try:
        text = path.read_text()
    except OSError as e:
        raise RecordError(f"cannot read {path}: {e.strerror}") from None
    hosts: dict = {}
    open_key = None  # a key with no value: the `- item` lines after it are its list
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        where = f"hosts.yml line {n}"
        if line.startswith("- ") and open_key is not None:
            raw = line[2:].strip()
            item = None if raw.startswith("- ") else _scalar(raw, where)
            if item is None:
                raise RecordError(f"{where}: a list item must be a scalar")
            if hosts[open_key] is None:
                hosts[open_key] = []
            hosts[open_key].append(item)
            continue
        if line[0] in " \t-":
            raise RecordError(f"{where}: nested values are not supported (flat keys only)")
        key, sep, raw = line.partition(":")
        if not sep or not key or (raw and raw[0] != " "):
            raise RecordError(f"{where}: expected 'key: value'")
        raw = raw.strip()
        hosts[key] = [] if raw == "[]" else _scalar(raw, where)
        open_key = key if raw == "" else None
    return hosts


def _required(hosts: dict, key: str) -> str:
    value = hosts.get(key)
    if not isinstance(value, str) or not value:
        raise RecordError(f"hosts.yml: no {key}")
    return value


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
    raise RecordError(f"hosts.yml: unknown provision {provision!r}")
