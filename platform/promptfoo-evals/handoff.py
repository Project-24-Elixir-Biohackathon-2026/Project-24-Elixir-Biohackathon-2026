"""Loaders for the hand-off directory (platform/ansible/output/<instance>/), standard library only.

A missing, malformed or mismatched hand-off file raises ConfigError (ManifestError for
injections.json): scoring stops with a configuration error, never a pass.

The canary record (canaries.json) and hosts.yml readers, and the `_scalar`/`_required` parsing they
share, live in platform/report/canary_record.py (canary hit viewer slice 1, decision 2), so the
canary hit viewer's watcher can read them without importing promptfoo-evals; imported below as
ConfigError (aliasing canary_record.RecordError), _json, _required, _scalar, load_canaries and
read_hosts, so this module's own callers and `ManifestError(ConfigError)` are unchanged.
is_file_canary and METADATA_TYPES live in platform/report/canarymatch.py, for the same reason.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(HERE) not in sys.path:  # promptfoo loads this file by path
    sys.path.insert(0, str(HERE))
import injections_schema  # noqa: E402

REPORT = str(REPO_ROOT / "platform" / "report")
if REPORT not in sys.path:
    sys.path.insert(0, REPORT)
from canarymatch import METADATA_TYPES, is_file_canary  # noqa: E402
from canary_record import (  # noqa: E402
    RecordError as ConfigError,
    _json,
    _required,
    _scalar,
    load_canaries,
    read_hosts,
    vm_argv,
)

SWITCHES = ("spe_harden_trs_readonly", "spe_harden_data_tiers", "spe_harden_egress", "spe_agent_tool_surface",
            "spe_harden_airlock")
FIXTURES = Path("platform/ansible/catalog/injections/fixtures.json")  # under the repo root


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


def api_host(dir: Path | str) -> str:
    return _required(read_hosts(dir), "api_host")


def check_hardening(record: object) -> dict:
    """The shape of hardening.json version 1 (plan README, Shared interfaces).

    `injections` says whether the injection fixtures were planted: true (all three spe_inject_* on) is
    the injected condition, false (all off) the clean one (spec part 06, *Clean and injected runs*),
    which the matrix shows as "L<n> clean"; the role writes "mixed" for anything else, refused here.

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


def canaries_digest(dir: Path | str) -> str:
    """SHA-256 over the canary record's tokens (type, file, token) and study ids, in a fixed order.

    Equal for the clean and the injected build of one level (spec part 02, *Matched builds*); it
    ignores generated_at. A digest, never a token, so the counts can carry it.
    """
    directory = Path(dir)
    tokens = sorted([t["type"], t["file"], t["token"]] for t in load_canaries(directory))
    body = json.dumps({"study_ids": sorted(load_study_ids(directory)), "tokens": tokens}, sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()


def condition(dir: Path | str, repo_root: Path | None = None) -> str:
    """The run's condition, "injected" or "clean", once the hand-off is consistent with it.

    injected: injections.json is valid (load_injections) and lists at least one placement. clean:
    injections.json is absent or empty, and every fixture's canary_file in the catalogue
    (FIXTURES under repo_root) still holds a file canary, so removing the injections removed no
    target (spec part 02, *Matched builds*). "mixed" is refused by load_hardening.
    """
    directory = Path(dir)
    root = repo_root or REPO_ROOT
    if load_hardening(directory)["injections"]:
        if not load_injections(directory, root):
            raise ManifestError("injections.json lists no injection, but hardening.json says injections: true")
        return "injected"
    if (directory / "injections.json").exists():
        manifest = _json(directory / "injections.json", ManifestError)
        if not isinstance(manifest, dict) or manifest.get("injections") != []:
            raise ManifestError("injections.json lists injections, but hardening.json says injections: false")
    catalogue = _json(root / FIXTURES)
    fixtures = catalogue.get("fixtures") if isinstance(catalogue, dict) else None
    if not isinstance(fixtures, list) or not fixtures:
        raise ConfigError(f"{FIXTURES}: no fixtures")
    files = {t["file"] for t in load_canaries(directory) if is_file_canary(t)}
    missing = sorted({str(f.get("canary_file")) for f in fixtures if f.get("canary_file") not in files})
    if missing:
        raise ConfigError("clean build lacks the file canary of an injection target: " + ", ".join(missing))
    return "clean"
