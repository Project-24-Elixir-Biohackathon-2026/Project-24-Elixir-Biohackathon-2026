"""The Node version the `spe_eval` role installs (`spe_eval_node_version`,
`platform/ansible/inventory/group_vars/all.yml`) must be at or above the floor promptfoo's own
`package-lock.json` entry pins (`engines.node`, e.g. `">=22.22.0"` for promptfoo 0.125.1): `npm ci`
only warns on a mismatch, but promptfoo's own CLI checks the Node version at start-up and refuses
below it (fix round 1, critical finding: `spe_eval_node_version` was `22.11.0`, below promptfoo
0.125.1's own `>=22.22.0`). This reads both files directly, so a promptfoo version bump that raises
the floor fails this test rather than failing silently on the VM.
"""
import json
import re
from pathlib import Path

import yaml

ANSIBLE = Path(__file__).resolve().parents[2] / "ansible"
PROMPTFOO_EVALS = Path(__file__).resolve().parents[2] / "promptfoo-evals"

ENGINES_RE = re.compile(r"^>=\s*(\d+)\.(\d+)\.(\d+)$")


def node_version_floor() -> tuple[int, int, int]:
    """The `>=X.Y.Z` floor from `package-lock.json`'s own `node_modules/promptfoo` entry's
    `engines.node` (the installed promptfoo package, not the top-level `package.json`, which
    promptfoo's own CLI does not read for this check)."""
    lock = json.loads((PROMPTFOO_EVALS / "package-lock.json").read_text())
    entry = lock["packages"]["node_modules/promptfoo"]
    engines_node = entry["engines"]["node"]
    m = ENGINES_RE.match(engines_node.strip())
    assert m, f"unexpected engines.node format: {engines_node!r} (update ENGINES_RE)"
    return tuple(int(g) for g in m.groups())


def spe_eval_node_version() -> tuple[int, int, int]:
    group_vars = yaml.safe_load((ANSIBLE / "inventory" / "group_vars" / "all.yml").read_text())
    pinned = group_vars["spe_eval_node_version"]
    parts = tuple(int(p) for p in pinned.split("."))
    assert len(parts) == 3, f"spe_eval_node_version must be X.Y.Z, got {pinned!r}"
    return parts


def test_package_lock_engines_node_parses():
    floor = node_version_floor()
    assert floor == (22, 22, 0), floor  # pins promptfoo 0.125.1's own current floor


def test_spe_eval_node_version_satisfies_promptfoos_engines_node():
    pinned = spe_eval_node_version()
    floor = node_version_floor()
    assert pinned >= floor, (
        f"spe_eval_node_version {pinned} is below promptfoo's own engines.node floor {floor} "
        "(platform/promptfoo-evals/package-lock.json): npm ci only warns, but promptfoo's CLI "
        "refuses to start below it")
