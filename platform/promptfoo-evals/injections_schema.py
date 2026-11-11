"""Schema of injections.json, version 1 (spec part 02, Hand-off), standard library only.

    python3 injections_schema.py <manifest> <repo_root>   # exit 1, one error per line, when invalid
    (also lints fixtures.json itself, check_fixtures)

Checked when the handoff role writes the manifest and when handoff.load_injections loads it.
The manifest carries no token, seed or credential: unknown fields are errors.

The catalogue is read from the repository's own files, not listed here (spec 01, *Attacks*,
decision 23): `build_catalogue` builds id -> (switch, surface, target_file, payload) from
`fixtures.json`, `surfaces.json` beside it gives each surface's location keys (`{"surfaces":
{<surface>: [<key>, ...]}}`, sorted, as the schema used to list them), and metrics.DETECTORS (the
scoring side, imported lazily: metrics imports handoff, which imports this module) gives the
actions a detector can score. A completely different injection (new id, new surface or new action)
needs no edit here, only its fixture and, for a new action, its detector in metrics.py.

What stays fixed, for every injection (spec 01, end of *Attacks*): the manifest entry's fields
(and no token, seed or credential field), one placement of exactly the committed payload
(`payload_file` is `PAYLOAD_DIR/<payload>`, the fixture's own `payload` field), its SHA-256
matching the file, `target_file` equal to `/data-share/` + `canary_file`, `disclosure` derived
from the canary file's directory (`registry/`: first five lines; `secret/`: whole file), and
`location` holding exactly the surface's keys. `check_fixtures` lints the catalogue itself:
every fixture complete, unique ids and switches, a known surface, an action a detector handles,
a payload file that is present and names its target, and a switch that defaults to `false` in
`group_vars/all.yml`.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[2]  # platform/promptfoo-evals/injections_schema.py
PAYLOAD_DIR = "platform/ansible/catalog/injections"
GROUP_VARS = "platform/ansible/inventory/group_vars/all.yml"  # under the repo root
DATA_SHARE = "/data-share/"
FIELDS = ("id", "switch", "payload_file", "payload_sha256", "surface", "location", "target_file", "canary_file",
          "action", "disclosure")
FIXTURE_FIELDS = ("id", "switch", "surface", "payload", "select", "target_file", "canary_file", "action",
                  "disclosure")
SHA256 = re.compile(r"[0-9a-f]{64}")


def _disclosure(canary_file: str) -> str | None:
    if canary_file.startswith("sensitive/registry/"):
        return "first-five-lines"
    if canary_file.startswith("sensitive/secret/"):
        return "whole-file"
    return None


def _detectors() -> dict:
    """metrics.DETECTORS, the action -> detector map (metrics imports handoff, which imports this
    module, so this import stays lazy, done only when a catalogue is actually built)."""
    import metrics
    return metrics.DETECTORS


def _fixtures(repo_root: Path) -> list[dict]:
    """fixtures.json's `fixtures` array, under <repo_root>/PAYLOAD_DIR."""
    path = Path(repo_root) / PAYLOAD_DIR / "fixtures.json"
    data = json.loads(path.read_text())
    fixtures = data.get("fixtures") if isinstance(data, dict) else None
    if not isinstance(fixtures, list):
        raise ValueError(f"{PAYLOAD_DIR}/fixtures.json: no fixtures array")
    return fixtures


def _surfaces(repo_root: Path) -> dict[str, tuple[str, ...]]:
    """surfaces.json's surface -> location keys, under <repo_root>/PAYLOAD_DIR."""
    path = Path(repo_root) / PAYLOAD_DIR / "surfaces.json"
    data = json.loads(path.read_text())
    surfaces = data.get("surfaces") if isinstance(data, dict) else None
    if not isinstance(surfaces, dict):
        raise ValueError(f"{PAYLOAD_DIR}/surfaces.json: no surfaces object")
    return {surface: tuple(keys) for surface, keys in surfaces.items()}


def build_catalogue(repo_root: Path = REPO_ROOT) -> dict[str, tuple[str, str, str, str]]:
    """id -> (switch, surface, target_file, payload), from fixtures.json (spec 01, decision 23)."""
    return {f["id"]: (f["switch"], f["surface"], f["target_file"], f["payload"]) for f in _fixtures(repo_root)}


def switches(ids: list[str], repo_root: Path = REPO_ROOT) -> dict[str, bool]:
    """Every catalogue switch, `True` for the listed ids, `False` otherwise: how an experiment
    block's `injections` (spec 01, *Experiments*) turns into `spe_inject_*` variables. An id
    outside the catalogue raises ValueError naming it.
    """
    catalogue = build_catalogue(repo_root)
    unknown = sorted(set(ids) - set(catalogue))
    if unknown:
        raise ValueError(f"unknown injection id(s): {', '.join(unknown)}")
    on = set(ids)
    return {switch: iid in on for iid, (switch, *_rest) in catalogue.items()}


def check_fixtures(repo_root: Path = REPO_ROOT) -> list[str]:
    """Lints fixtures.json against the invariants every entry must meet (spec 01, *Attacks*):
    every field a string but `select` (a membership test on a wrong-typed field would otherwise
    raise rather than report), unique id and switch, a switch named `spe_inject_*`, a known
    surface, an action a detector can score, `select` exactly one key (what the planting role
    matches the real placement by), a payload that is a plain filename (never a path that climbs
    out of the injections directory), present and naming its target, and a switch that defaults
    to `false` in `group_vars/all.yml` (so a build with every switch off is today's).
    """
    root = Path(repo_root)
    try:
        fixtures = _fixtures(root)
    except (OSError, ValueError) as e:
        return [f"{PAYLOAD_DIR}/fixtures.json: {e}"]
    try:
        surfaces = _surfaces(root)
    except (OSError, ValueError) as e:
        return [f"{PAYLOAD_DIR}/surfaces.json: {e}"]
    try:
        group_vars = (root / GROUP_VARS).read_text()
    except OSError as e:
        return [f"{GROUP_VARS}: {e}"]
    detectors = _detectors()
    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_switches: set[str] = set()
    for i, fx in enumerate(fixtures):
        if not isinstance(fx, dict):
            errors.append(f"fixtures[{i}]: not an object")
            continue
        missing = [f for f in FIXTURE_FIELDS if f not in fx]
        iid = fx.get("id")
        where = f"fixtures[{i}] ({iid})" if isinstance(iid, str) else f"fixtures[{i}]"
        if missing:
            errors.append(f"{where}: missing {', '.join(missing)}")
            continue
        # Every field but `select` is a string: a membership test on a field of the wrong type --
        # `fx["surface"] not in surfaces`, `switch in seen_switches` -- raises TypeError for an
        # unhashable value, e.g. a list, instead of a clean lint error; checked, and the rest of
        # this fixture skipped, before any such test runs.
        not_strings = [f for f in FIXTURE_FIELDS if f != "select" and not isinstance(fx[f], str)]
        if not_strings:
            errors.append(f"{where}: {', '.join(not_strings)} must be strings")
            continue
        if iid in seen_ids:
            errors.append(f"{where}: duplicate id")
        seen_ids.add(iid)
        switch = fx["switch"]
        if switch in seen_switches:
            errors.append(f"{where}: duplicate switch {switch}")
        seen_switches.add(switch)
        if not switch.startswith("spe_inject_"):
            errors.append(f"{where}: switch must start with spe_inject_")
        if fx["surface"] not in surfaces:
            errors.append(f"{where}: unknown surface {fx['surface']!r}")
        if fx["action"] not in detectors:
            errors.append(f"{where}: no detector for action {fx['action']!r}")
        select = fx.get("select")
        if not isinstance(select, dict) or len(select) != 1:
            # Exactly one key (01-experiment-model.md, *Attacks*): the planting role matches it
            # against the real placement's own top-level or `location` field
            # (`injections_manifest.py`: `(key, want), = fx["select"].items()`, which raises
            # "not enough values to unpack"/"too many values to unpack" for anything else).
            errors.append(f"{where}: select must hold exactly one key")
        payload = fx["payload"]
        payload_rel = PurePosixPath(payload)
        if payload_rel.is_absolute() or ".." in payload_rel.parts or payload != payload_rel.name:
            errors.append(f"{where}: payload must be a plain filename, not {payload!r}")
        else:
            payload_path = root / PAYLOAD_DIR / payload
            try:
                text = payload_path.read_text()
            except OSError:
                errors.append(f"{where}: payload file {payload} not found")
            else:
                if fx["target_file"] not in text:
                    errors.append(f"{where}: payload {payload} does not name {fx['target_file']}")
        if not re.search(rf"^{re.escape(switch)}: false\b", group_vars, re.MULTILINE):
            errors.append(f"{where}: switch {switch} does not default to false in {GROUP_VARS}")
    return errors


def _entry(e: dict, where: str, repo_root: Path, catalogue: dict, locations: dict, detectors: dict) -> list[str]:
    missing = [f for f in FIELDS if f not in e]
    unknown = sorted(set(e) - set(FIELDS))
    errors = [f"{where}: missing {', '.join(missing)}"] if missing else []
    if unknown:
        errors.append(f"{where}: unknown fields {', '.join(unknown)} (no token, seed or credential field)")
    if missing:
        return errors
    not_strings = [f for f in FIELDS if f != "location" and not (isinstance(e[f], str) and e[f])]
    if not_strings:
        return errors + [f"{where}: {', '.join(not_strings)} must be non-empty strings"]
    known = catalogue.get(e["id"])
    if known is None:
        errors.append(f"{where}: unknown id (catalogue: {', '.join(catalogue)})")
    else:
        switch, surface, target_file, payload = known
        for field, value in zip(("switch", "surface", "target_file"), (switch, surface, target_file)):
            if e[field] != value:
                errors.append(f"{where}: {field} must be {value}")
        if e["payload_file"] != f"{PAYLOAD_DIR}/{payload}":
            errors.append(f"{where}: payload_file must be {PAYLOAD_DIR}/{payload}")
    if e["surface"] not in locations:
        errors.append(f"{where}: unknown surface {e['surface']!r}")
    if e["action"] not in detectors:
        errors.append(f"{where}: invalid action {e['action']!r}")
    if e["target_file"] != DATA_SHARE + e["canary_file"]:
        errors.append(f"{where}: target_file and canary_file name different files")
    expected = _disclosure(e["canary_file"])
    if e["disclosure"] != expected:
        errors.append(f"{where}: disclosure must be {expected} for {e['canary_file']}")
    location = e["location"]
    keys = locations.get(e["surface"])
    if not isinstance(location, dict) or (keys and tuple(sorted(location)) != keys) \
            or not all(isinstance(v, str) and v for v in location.values()):
        errors.append(f"{where}: location must hold exactly {', '.join(keys or ())} as non-empty strings")
    elif "field" in location and location["field"] != "description":
        errors.append(f"{where}: location.field must be description")
    if not SHA256.fullmatch(e["payload_sha256"]):
        errors.append(f"{where}: payload_sha256 must be 64 lowercase hex characters")
    else:
        path = PurePosixPath(e["payload_file"])
        if path.is_absolute() or ".." in path.parts:
            errors.append(f"{where}: payload_file must be repository-relative")
        else:
            try:
                data = (repo_root / path).read_bytes()
            except OSError:
                errors.append(f"{where}: payload_file {path} not found under {repo_root}")
            else:
                if not data:
                    errors.append(f"{where}: payload_file {path} is empty")
                else:
                    digest = hashlib.sha256(data).hexdigest()
                    if digest != e["payload_sha256"]:
                        errors.append(f"{where}: payload_sha256 does not match {path}")
    return errors


def validate(manifest: dict, repo_root: Path) -> list[str]:
    if not isinstance(manifest, dict):
        return ["manifest is not a JSON object"]
    root = Path(repo_root)
    try:
        catalogue = build_catalogue(root)
        locations = _surfaces(root)
    except (OSError, ValueError, KeyError, TypeError) as e:
        # KeyError/TypeError: a broken fixtures.json entry (e.g. missing 'payload'), the shape
        # check_fixtures lints; caught here too so a caller that skips check_fixtures (handoff.
        # load_injections) gets a ManifestError, not a traceback.
        return [f"{PAYLOAD_DIR}: {e}"]
    detectors = _detectors()
    errors = []
    unknown = sorted(set(manifest) - {"schema_version", "injections"})
    if unknown:
        errors.append(f"unknown top-level fields: {', '.join(unknown)}")
    if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        errors.append("schema_version must be the integer 1")
    entries = manifest.get("injections")
    if not isinstance(entries, list):
        return errors + ["injections must be an array"]
    seen: set[str] = set()
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            errors.append(f"injections[{i}]: not an object")
            continue
        iid = e.get("id")
        where = f"injections[{i}] ({iid})" if isinstance(iid, str) else f"injections[{i}]"
        if isinstance(iid, str):
            if iid in seen:
                errors.append(f"{where}: duplicate id")
            seen.add(iid)
        errors += _entry(e, where, root, catalogue, locations, detectors)
    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: injections_schema.py <manifest> <repo_root>", file=sys.stderr)
        return 2
    try:
        manifest = json.loads(Path(argv[0]).read_text())
    except (OSError, ValueError) as e:
        print(f"{argv[0]}: {e}", file=sys.stderr)
        return 1
    repo_root = Path(argv[1])
    # check_fixtures first: a broken fixtures.json (e.g. a fixture missing 'payload') would
    # otherwise reach validate's build_catalogue first and raise before check_fixtures ever
    # names it.
    errors = check_fixtures(repo_root)
    if not errors:
        errors = validate(manifest, repo_root)
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
