"""promptfoo provider for threatlab plans: one agent run through your logged-in browser.

promptfoo hands over the test's vars: `case_key` (an item of the plan) and `plan_dir`. The
provider takes that item's frozen case from plan.json, plants a fresh {nonce}, sends the run
through chat-ui's run route in the browser (lab_browser) and appends the transcript to the
plan's raw.jsonl, so `threatlab.py evaluate <plan_dir>` sees promptfoo's trials like its own.

It refuses to run unless THREATLAB_APPROVE holds the plan's hash prefix: `threatlab.py promptfoo`
sets it after checking the run count against your limits.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lab_checks as L  # noqa: E402
import spe_threat  # noqa: E402


def _load(plan_dir: Path) -> dict:
    plan = json.loads((plan_dir / "plan.json").read_text())
    if L.plan_hash(plan) != plan["hash"]:
        raise ValueError("plan.json changed after it was made")
    approve = os.environ.get("THREATLAB_APPROVE", "")
    if len(approve) < 12 or not plan["hash"].startswith(approve):
        raise PermissionError("not approved: run it through `threatlab.py promptfoo <plan> --approve <hash>`")
    return plan


def _next_trial(raw: Path, key: str) -> int:
    if not raw.exists():
        return 1
    return 1 + sum(1 for line in raw.read_text().splitlines() if line.strip() and json.loads(line)["key"] == key)


def call_api(prompt: str, options: dict | None = None, context: dict | None = None) -> dict:
    v = (context or {}).get("vars") or {}
    try:
        plan_dir = Path(v["plan_dir"])
        plan = _load(plan_dir)
        item = next(it for it in plan["items"] if it["key"] == v["case_key"])
    except (KeyError, StopIteration):
        return {"error": f"case {v.get('case_key')} is not in the plan"}
    except (ValueError, PermissionError, OSError) as e:
        return {"error": str(e)}
    cfg = (options or {}).get("config") or {}
    nonce = uuid.uuid4().hex[:10].upper()  # fresh per call: promptfoo repeats are new trials
    case = spe_threat.fill(copy.deepcopy(item["case"]), nonce)

    import lab_browser
    br = lab_browser.Browser(cfg.get("cdp", "http://127.0.0.1:9222"), plan["chat_url"], float(cfg.get("timeout_s", 420)))
    try:
        run = br.run(spe_threat.run_input(case))
    finally:
        br.close()

    import checks
    verdict = spe_threat.judge(run, case, checks.Env())
    raw = plan_dir / "raw.jsonl"
    with open(raw, "a") as f:
        f.write(json.dumps({"key": item["key"], "trial": _next_trial(raw, item["key"]), "nonce": nonce,
                            "verdict": verdict["verdict"], "indicators": verdict["indicators"], "via": "promptfoo",
                            **run}, ensure_ascii=False) + "\n")
    os.chmod(raw, 0o600)
    if run.get("error") and not run.get("answer") and not run.get("tool_calls"):
        return {"error": f"run failed: {run['error']}"}
    return {"output": run.get("answer") or "",
            "metadata": {"nonce": nonce, "case_key": item["key"], "tool_calls": run.get("tool_calls") or [],
                         "run_error": run.get("error")}}
