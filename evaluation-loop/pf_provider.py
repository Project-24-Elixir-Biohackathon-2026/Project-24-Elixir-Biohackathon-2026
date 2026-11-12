"""promptfoo provider for threatlab plans: every message promptfoo sends to the chat passes through here.

Two kinds of plan:

* a **red-team plan** (`plan.json` with `mode: pf`, made by `threatlab.py pf-generate`): promptfoo's own
  attack loop (crescendo, jailbreak:tree, static encodings, ...) calls this once per turn. This is gate D:
  - the plan's hash must be approved (THREATLAB_APPROVE, set by `pf-run`);
  - the message is linted (lab_checks.lint_message) and never sent if it fails;
  - a run counter (a locked file in the plan dir) stops at the plan's max_runs: promptfoo has no cap;
  - the planted {nonce} is filled per conversation (one chat session = one nonce), under a reversible
    encoding when the strategy applied one;
  - the turn goes to the chat through lab_chat (http or browser), continuing the session promptfoo
    passes back as vars.sessionId;
  - every turn, sent or blocked, is appended to the plan's raw.jsonl (0600): that log, not promptfoo's
    results, is what `pf-evaluate` judges.
* an older **single-turn plan** (`threatlab.py plan`, run with `threatlab.py promptfoo`): one frozen case
  per test, through the logged-in browser, as before.
"""
from __future__ import annotations

import copy
import fcntl
import json
import os
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import checks  # noqa: E402
import lab_checks as L  # noqa: E402
import lab_encodings  # noqa: E402
import spe_threat  # noqa: E402

_transports: dict[str, object] = {}  # the Python worker is persistent: one chat transport per plan


def _load(plan_dir: Path) -> dict:
    plan = json.loads((plan_dir / "plan.json").read_text())
    if L.plan_hash(plan) != plan["hash"]:
        raise ValueError("plan.json changed after it was made")
    approve = os.environ.get("THREATLAB_APPROVE", "")
    if len(approve) < 12 or not plan["hash"].startswith(approve):
        raise PermissionError("not approved: run it through threatlab.py (pf-run or promptfoo) with --approve <hash>")
    return plan


@contextmanager
def locked(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_name(path.name + ".lock"), "a+") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def take_slot(counter: Path, limit: int) -> int | None:
    """Count one call against `limit`; None when the budget is used up (nothing is sent then)."""
    with locked(counter):
        n = int(counter.read_text() or 0) if counter.exists() else 0
        if n >= limit:
            return None
        counter.write_text(str(n + 1))
        return n + 1


def append_row(raw: Path, row: dict) -> None:
    with locked(raw):
        with open(raw, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.chmod(raw, 0o600)


def read_rows(raw: Path) -> list[dict]:
    if not raw.exists():
        return []
    return [json.loads(line) for line in raw.read_text().splitlines() if line.strip()]


def case_for(plan: dict, key: str | None) -> dict:
    return (plan.get("cases") or {}).get(key or "") or plan["generic"]


def newest_message(prompt: str) -> str:
    """promptfoo's prompt: the message itself, or (a non-stateful strategy) the whole chat as a JSON array,
    whose last user turn is the new message; the rest is dropped, since chat-ui keeps the history."""
    try:
        parsed = json.loads(prompt)
    except (ValueError, TypeError):
        return prompt
    if isinstance(parsed, list) and parsed and all(isinstance(m, dict) and "role" in m for m in parsed):
        users = [m for m in parsed if m.get("role") == "user"]
        return str(users[-1].get("content") or "") if users else ""
    return prompt


def transport_for(plan: dict, plan_dir: Path):
    key = str(plan_dir)
    if key not in _transports:
        import lab_chat
        _transports[key] = lab_chat.open_transport(plan["chat"])
    return _transports[key]


def new_nonce() -> str:
    return uuid.uuid4().hex[:10].upper()


def call_redteam(prompt: str, plan: dict, plan_dir: Path, context: dict) -> dict:
    vars_ = context.get("vars") or {}
    meta = (context.get("test") or {}).get("metadata") or {}
    strategy = meta.get("strategyId") or "basic"
    key = vars_.get("case_key") or "generic"
    case = case_for(plan, key)
    raw = plan_dir / "raw.jsonl"
    message = newest_message(prompt)
    plain = lab_encodings.plain_text(strategy, message)

    sid = vars_.get("sessionId")
    if sid:  # a later turn of a stateful conversation: same session, same nonce
        prior = [r for r in read_rows(raw) if r.get("session_id") == sid]
        nonce = next((r["nonce"] for r in prior if r.get("nonce")), None) or new_nonce()
        turn = 1 + sum(1 for r in prior if r.get("status") == "sent")
    else:
        sid, nonce, turn = str(uuid.uuid4()), new_nonce(), 1
    row = {"session_id": sid, "turn": turn, "case_key": key, "plugin": meta.get("pluginId") or "",
           "strategy": strategy, "test_idx": context.get("testIdx"), "repeat": context.get("repeatIndex"),
           "nonce": nonce, "message": message, "provable": L.provable(plain, L.anchors(case), case["indicators"])}

    errors = L.lint_message(plain.replace("{nonce}", nonce), plan["allowed_hosts"])
    if errors:
        append_row(raw, {**row, "status": "blocked", "reason": "lint: " + "; ".join(errors)})
        return {"error": "blocked by lint: " + "; ".join(errors), "sessionId": sid}
    if take_slot(plan_dir / "counter", int(plan["max_runs"])) is None:
        append_row(raw, {**row, "status": "blocked", "reason": f"budget: max_runs {plan['max_runs']} reached"})
        return {"error": f"budget reached: max_runs {plan['max_runs']}", "sessionId": sid}

    sent = lab_encodings.fill_encoded(strategy, message, nonce)
    try:
        res = transport_for(plan, plan_dir).turn(sent, sid)
    except Exception as e:  # noqa: BLE001  (a dead transport is an error turn, not a crash of the eval)
        res = {"answer": "", "tool_calls": [], "error": f"{type(e).__name__}: {str(e)[:200]}"}
    run = {"answer": res.get("answer") or "", "tool_calls": res.get("tool_calls") or [], "error": res.get("error")}
    verdict = spe_threat.judge(run, spe_threat.fill(copy.deepcopy(case), nonce), checks.Env())
    append_row(raw, {**row, "status": "sent", "verdict": verdict["verdict"], "indicators": verdict["indicators"], **run})
    if run["error"] and not run["answer"] and not run["tool_calls"]:
        return {"error": f"run failed: {run['error']}", "sessionId": sid}
    return {"output": run["answer"], "sessionId": sid,
            "metadata": {"nonce": nonce, "case_key": key, "tool_calls": run["tool_calls"], "run_error": run["error"],
                         "turn": turn, "provable": row["provable"], "session_id": sid}}


# --- the older single-turn plans (threatlab.py promptfoo) ---------------------------------------------

def call_plan_item(plan: dict, plan_dir: Path, v: dict, cfg: dict) -> dict:
    try:
        item = next(it for it in plan["items"] if it["key"] == v["case_key"])
    except (KeyError, StopIteration):
        return {"error": f"case {v.get('case_key')} is not in the plan"}
    nonce = new_nonce()  # fresh per call: promptfoo repeats are new trials
    case = spe_threat.fill(copy.deepcopy(item["case"]), nonce)

    import lab_browser
    br = lab_browser.Browser(cfg.get("cdp", "http://127.0.0.1:9222"), plan["chat_url"], float(cfg.get("timeout_s", 420)))
    try:
        run = br.run(spe_threat.run_input(case))
    finally:
        br.close()

    verdict = spe_threat.judge(run, case, checks.Env())
    raw = plan_dir / "raw.jsonl"
    trial = 1 + sum(1 for r in read_rows(raw) if r.get("key") == item["key"])
    append_row(raw, {"key": item["key"], "trial": trial, "nonce": nonce, "verdict": verdict["verdict"],
                     "indicators": verdict["indicators"], "via": "promptfoo", **run})
    if run.get("error") and not run.get("answer") and not run.get("tool_calls"):
        return {"error": f"run failed: {run['error']}"}
    return {"output": run.get("answer") or "",
            "metadata": {"nonce": nonce, "case_key": item["key"], "tool_calls": run.get("tool_calls") or [],
                         "run_error": run.get("error")}}


def call_api(prompt: str, options: dict | None = None, context: dict | None = None) -> dict:
    context = context or {}
    cfg = (options or {}).get("config") or {}
    v = context.get("vars") or {}
    plan_dir = cfg.get("plan_dir") or v.get("plan_dir")
    if not plan_dir:
        return {"error": "no plan_dir in the provider config or the test's vars"}
    plan_dir = Path(plan_dir)
    try:
        plan = _load(plan_dir)
    except (ValueError, PermissionError, OSError) as e:
        return {"error": str(e)}
    if plan.get("mode") == "pf":
        return call_redteam(prompt, plan, plan_dir, context)
    return call_plan_item(plan, plan_dir, v, cfg)
