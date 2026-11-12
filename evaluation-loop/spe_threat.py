#!/usr/bin/env python3
"""Run the threat catalog's scenarios against an SPE agent and report which reproduce.

    uv run --with pyyaml python spe_threat.py list
    uv run --with pyyaml python spe_threat.py run --agent-url URL [--chat-url URL] [options]
    uv run --with pyyaml python spe_threat.py selftest [--chat-url URL]

Scenario files: scenarios/TM-NNN.yaml, one per threat. A case is one AG-UI run (a forged
history, a message, optional client tools) or one probe (a shell command in the sandbox
over SSH, no model), plus indicators (checks.py) that decide whether it reproduced the
scenario. A case runs `trials` times against every target it lists that was given:
`agent` (the agent's /agent, bearer key) and `chat` (chat-ui's run route, no key; the
chat server owns the history there).

Gates, because runs against a real agent cost money and some scenarios damage the instance:
  requires: scripted  the case reads the scripted agent's echo-input (platform/dev/fake_agent.py);
                      runs only with --scripted
  requires: model     a real model must decide; runs only with --allow-paid (and never with --scripted)
  destructive: true   load or deletion on the instance; also needs --allow-destructive
  kind: probe         needs --ssh HOST; no model call

Secrets are read here, from the environment or files, never from the scenario files:
SPE_AGENT_API_KEY[_FILE], SPE_LLM_API_KEY[_FILE], --canaries output/<instance>/canaries.json.
results.json and summary.md name canary types and key names, never values; --keep-raw
also writes the transcripts (raw.jsonl), which may hold canaries: keep it off shared disks.

Exit code: 0 when every case ran (and, for selftest, matched its `expect`), 1 otherwise.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

import checks

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[0]
SCENARIOS = HERE / "scenarios"

_spec = importlib.util.spec_from_file_location("agui_provider", ROOT / "platform/promptfoo-evals/agui_provider.py")
agui = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(agui)


# --- scenario files -----------------------------------------------------------------------

def load_cases(threat: str | None = None, case: str | None = None) -> list[dict]:
    cases = []
    for path in sorted(SCENARIOS.glob("TM-*.yaml")):
        doc = yaml.safe_load(path.read_text())
        if threat and doc["threat"] != threat:
            continue
        for c in doc.get("cases") or []:
            c = {"threat": doc["threat"], "trials": 1, "targets": ["agent"], "kind": "run",
                 "requires": "model", "destructive": False, "mode": "any", **c}
            c["key"] = f"{doc['threat']}/{c['id']}"
            if case and case not in (c["id"], c["key"]):
                continue
            cases.append(c)
    return cases


def fill(value, nonce: str):
    """Replace {nonce} everywhere in a case, so every trial plants its own marker."""
    if isinstance(value, str):
        return value.replace("{nonce}", nonce)
    if isinstance(value, list):
        return [fill(v, nonce) for v in value]
    if isinstance(value, dict):
        return {k: fill(v, nonce) for k, v in value.items()}
    return value


# --- one AG-UI run --------------------------------------------------------------------------

def _message(m: dict) -> dict:
    out = {"id": m.get("id") or str(uuid.uuid4()), "role": m["role"], "content": m.get("content", "")}
    if m["role"] == "assistant" and m.get("tool_calls"):
        out["toolCalls"] = [{"id": t["id"], "type": "function",
                             "function": {"name": t["name"], "arguments": json.dumps(t.get("args", {}))}}
                            for t in m["tool_calls"]]
    if m["role"] == "tool":
        out["toolCallId"] = m["tool_call_id"]
    return out


def run_input(case: dict) -> dict:
    messages = [_message(m) for m in case.get("history") or []]
    messages.append(_message({"role": "user", "content": case["message"]}))
    return {"threadId": str(uuid.uuid4()), "runId": str(uuid.uuid4()), "state": {}, "context": [],
            "forwardedProps": {}, "tools": case.get("tools") or [], "messages": messages}


def post_run(url: str, body: dict, key: str | None, timeout: float) -> dict:
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers=headers)
    acc, parser = agui.Accumulator(body["runId"], body["threadId"]), agui.SSEParser()
    deadline = time.monotonic() + timeout
    try:
        with urllib.request.urlopen(req, timeout=min(timeout, 120.0)) as resp:
            while chunk := resp.read1(65536):
                for event in parser.feed(chunk):
                    acc.add(event)
                if time.monotonic() > deadline:
                    raise TimeoutError(f"run exceeded {timeout:.0f} s")
            for event in parser.close():
                acc.add(event)
    except urllib.error.HTTPError as e:
        return {"answer": "", "tool_calls": [], "error": f"HTTP {e.code}"}
    except (agui.StreamError, urllib.error.URLError, TimeoutError, OSError) as e:
        res = acc.result()
        return {"answer": res["output"], "tool_calls": res["metadata"]["tool_calls"],
                "error": f"{type(e).__name__}: {getattr(e, 'reason', e)}"}
    res = acc.result()
    return {"answer": res["output"], "tool_calls": res["metadata"]["tool_calls"], "error": res.get("error")}


def run_probe(case: dict, ssh: str, container: str) -> dict:
    # `container: host` runs on the VM itself (e.g. to read a frontend's config on 127.0.0.1).
    where = case.get("container", container)
    inner = ["sh", "-c", case["command"]] if where == "host" else ["docker", "exec", where, "sh", "-c", case["command"]]
    cmd = ["ssh", "-o", "BatchMode=yes", ssh, shlex.join(inner)]  # ssh hands one string to the remote shell
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        out = p.stdout + p.stderr
        err = None if p.returncode in case.get("ok_exit", [0]) else f"exit {p.returncode}"
    except subprocess.TimeoutExpired:
        out, err = "", "probe timed out"
    # A probe's output is shaped like a tool result, so the same indicators apply.
    return {"answer": out, "tool_calls": [{"id": "probe", "name": "probe", "args": case["command"], "result": out}],
            "error": err}


# --- verdicts -------------------------------------------------------------------------------

def judge(run: dict, case: dict, env: checks.Env) -> dict:
    hits = []
    for ind in case.get("indicators") or []:
        (name, params), = ind.items() if isinstance(ind, dict) else ((ind, {}),)
        h = checks.INDICATORS[name](run, params or {}, env)
        hits.append({"indicator": name, "hit": h.hit, "unknown": h.unknown, "detail": h.detail})
    decided = [h for h in hits if not h["unknown"]]
    if run.get("error") and not run.get("tool_calls") and not run.get("answer"):
        verdict = "error"
    elif not decided:
        verdict = "unknown"
    else:
        agg = any if case["mode"] == "any" else all
        verdict = "reproduced" if agg(h["hit"] for h in decided) else "blocked"
    return {"verdict": verdict, "indicators": hits, "error": run.get("error")}


def gate(case: dict, args) -> str | None:
    """Why a case is skipped, or None to run it."""
    if case["kind"] == "probe":
        return None if args.ssh else "probe: needs --ssh"
    if case["requires"] == "scripted" and not args.scripted:
        return "needs the scripted agent (--scripted)"
    if case["requires"] == "model" and (args.scripted or not args.allow_paid):
        return "paid model call: needs --allow-paid against a real agent"
    if case["destructive"] and not args.allow_destructive:
        return "destructive: needs --allow-destructive"
    return None


def secret(var: str) -> str:
    value = os.environ.get(var, "")
    path = os.environ.get(var + "_FILE", "")
    if not value and path:
        value = Path(path).read_text().strip()
    return value


def execute(cases: list[dict], args) -> list[dict]:
    env = checks.Env.load(args.canaries, {"agent key": secret("SPE_AGENT_API_KEY"),
                                          "LLM key": secret("SPE_LLM_API_KEY")})
    targets = {"agent": args.agent_url, "chat": args.chat_url}
    key = secret("SPE_AGENT_API_KEY") or None
    results, raw = [], []
    for case in cases:
        why = gate(case, args)
        run_targets = ["sandbox"] if case["kind"] == "probe" else [t for t in case["targets"] if targets.get(t)]
        if not why and not run_targets:
            why = f"no URL for target(s) {case['targets']}"
        if why:
            results.append({"case": case["key"], "scenario": case.get("scenario"), "title": case.get("title"),
                            "target": ",".join(case["targets"]), "skipped": why})
            print(f"  skip  {case['key']}: {why}", flush=True)
            continue
        for target in run_targets:
            trials = []
            for _ in range(int(args.trials or case["trials"])):
                nonce = uuid.uuid4().hex[:10].upper()
                c = fill(copy.deepcopy(case), nonce)
                if case["kind"] == "probe":
                    run = run_probe(c, args.ssh, args.sandbox_container)
                else:
                    body = run_input(c)
                    run = post_run(targets[target], body, key if target == "agent" else None, args.timeout)
                v = judge(run, c, env)
                trials.append(v)
                if args.keep_raw:
                    raw.append({"case": case["key"], "target": target, "nonce": nonce, **run})
            n_rep = sum(t["verdict"] == "reproduced" for t in trials)
            expect = (case.get("expect") or {}).get(target)
            overall = ("reproduced" if n_rep else
                       "error" if all(t["verdict"] == "error" for t in trials) else
                       "unknown" if all(t["verdict"] == "unknown" for t in trials) else "blocked")
            r = {"case": case["key"], "scenario": case.get("scenario"), "title": case.get("title"),
                 "target": target, "trials": len(trials), "reproduced": n_rep, "verdict": overall,
                 "expect": expect, "as_expected": None if expect is None else expect == overall,
                 "details": trials}
            results.append(r)
            mark = {True: "ok", False: "UNEXPECTED", None: ""}[r["as_expected"]]
            print(f"  {overall:<10} {n_rep}/{len(trials)}  {case['key']} @{target}  {mark}", flush=True)
            for t in trials:
                for h in t["indicators"]:
                    print(f"      {'HIT ' if h['hit'] else '    '}{h['indicator']}: {h['detail']}", flush=True)
                if t.get("error"):
                    print(f"      error: {t['error']}", flush=True)
    if args.keep_raw:
        args.out.mkdir(parents=True, exist_ok=True)
        with open(args.out / "raw.jsonl", "w") as f:
            for r in raw:
                f.write(json.dumps(r) + "\n")
        os.chmod(args.out / "raw.jsonl", 0o600)
    return results


def write_report(results: list[dict], args, label: str) -> None:
    args.out.mkdir(parents=True, exist_ok=True)
    meta = {"when": datetime.now(timezone.utc).isoformat(timespec="seconds"), "label": label,
            "agent_url": args.agent_url, "chat_url": args.chat_url, "scripted": args.scripted,
            "model": args.model or ("scripted" if args.scripted else "unrecorded: pass --model")}
    (args.out / "results.json").write_text(json.dumps({"meta": meta, "results": results}, indent=2))
    lines = [f"# Threat evaluation: {label}", "",
             f"{meta['when']} · model: {meta['model']} · agent: {meta['agent_url'] or '-'} · chat: {meta['chat_url'] or '-'}", "",
             "| Case | Target | Verdict | Trials | Expected | Evidence |", "|---|---|---|---|---|---|"]
    for r in results:
        if "skipped" in r:
            lines.append(f"| {r['case']} | {r['target']} | skipped | | | {r['skipped']} |")
            continue
        ev = "; ".join(sorted({h["detail"] for t in r["details"] for h in t["indicators"] if h["hit"]})) or "-"
        exp = "" if r["expect"] is None else ("✓ " if r["as_expected"] else "✗ ") + r["expect"]
        lines.append(f"| {r['case']} | {r['target']} | **{r['verdict']}** | {r['reproduced']}/{r['trials']} | {exp} | {ev} |")
    (args.out / "summary.md").write_text("\n".join(lines) + "\n")
    print(f"\nreport: {args.out / 'summary.md'}")


# --- the scripted agent, for selftest ---------------------------------------------------------

def start_scripted_agent(port: int, key: str) -> subprocess.Popen:
    agent_dir = ROOT / "platform/agui/pydantic-ai-agent"
    proc = subprocess.Popen(["uv", "run", "--quiet", "--group", "dev", "python", str(ROOT / "platform/dev/fake_agent.py"),
                             "--port", str(port)], cwd=agent_dir, env={**os.environ, "SPE_AGENT_API_KEY": key},
                            stdin=subprocess.DEVNULL)
    until = time.time() + 180
    while time.time() < until:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=2) as r:
                if r.status == 200:
                    return proc
        except Exception:
            time.sleep(0.5)
    proc.terminate()
    sys.exit("FAIL: the scripted agent did not become healthy")


def start_chat_ui(port: int, agent_url: str, key: str, sessions: Path) -> subprocess.Popen:
    """The built chat UI (npm ci && npm run build in platform/agui/copilotkit-chat) in front of the agent."""
    app = ROOT / "platform/agui/copilotkit-chat"
    standalone = app / ".next/standalone"
    if not (standalone / "server.js").exists():
        sys.exit("FAIL: build the chat UI first: (cd platform/agui/copilotkit-chat && npm ci && npm run build)")
    if not (standalone / ".next/static").exists():
        import shutil
        shutil.copytree(app / ".next/static", standalone / ".next/static")
    proc = subprocess.Popen(["node", "server.js"], cwd=standalone, stdin=subprocess.DEVNULL, env={
        **os.environ, "SPE_SESSIONS_DIR": str(sessions), "AGENT_URL": agent_url, "AGENT_API_KEY": key,
        "PORT": str(port), "HOSTNAME": "127.0.0.1", "NEXT_MANUAL_SIG_HANDLE": "true"})
    until = time.time() + 60
    while time.time() < until:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/sessions", timeout=2):
                return proc
        except Exception:
            time.sleep(0.5)
    proc.terminate()
    sys.exit("FAIL: the chat UI did not come up")


# --- CLI ------------------------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list the cases and their gates")
    for name in ("run", "selftest"):
        p = sub.add_parser(name)
        p.add_argument("--threat", help="only this threat, e.g. TM-005")
        p.add_argument("--case", help="only this case id")
        p.add_argument("--chat-url", help="chat-ui run route, e.g. http://127.0.0.1:3000/api/copilotkit/agent/spe/run")
        p.add_argument("--out", type=Path, default=HERE / "reports" / datetime.now().strftime("%Y%m%d-%H%M%S"))
        p.add_argument("--trials", type=int, help="override every case's trials")
        p.add_argument("--timeout", type=float, default=600.0, help="seconds per run")
        p.add_argument("--keep-raw", action="store_true", help="also write transcripts (may hold canaries)")
        p.add_argument("--canaries", help="the instance's canary record (output/<instance>/canaries.json)")
        p.add_argument("--model", help="provider/model of the agent, recorded in the report")
        if name == "selftest":
            p.add_argument("--with-chat", action="store_true", help="also start the built chat UI and test through it")
        if name == "run":
            p.add_argument("--agent-url", help="e.g. http://127.0.0.1:8100/agent (through the SSH tunnel)")
            p.add_argument("--scripted", action="store_true", help="the agent is platform/dev/fake_agent.py")
            p.add_argument("--allow-paid", action="store_true", help="run cases that need a real model (paid)")
            p.add_argument("--allow-destructive", action="store_true", help="run cases that load or damage the instance")
            p.add_argument("--ssh", help="SSH host of the instance, for probes")
            p.add_argument("--sandbox-container", default="spe-frontend-sandbox-1")
    args = ap.parse_args()

    if args.cmd == "list":
        for c in load_cases():
            if c["kind"] == "probe":
                where, gates = "sandbox" if c.get("container", "") != "host" else "host", "probe (ssh, no model)"
            else:
                where = ",".join(c["targets"])
                gates = {"model": "paid", "scripted": "scripted agent"}[c["requires"]] + (", destructive" if c["destructive"] else "")
            print(f"{c['key']:<42} S{c.get('scenario', '-')}  {where:<11} {gates:<22} {c.get('title', '')}")
        return 0

    cases = load_cases(args.threat, args.case)
    if args.cmd == "selftest":
        key = "selftest-" + uuid.uuid4().hex
        os.environ["SPE_AGENT_API_KEY"] = key
        args.agent_url, args.scripted, args.allow_paid, args.allow_destructive, args.ssh = (
            "http://127.0.0.1:18190/agent", True, False, True, None)
        print("starting the scripted agent (platform/dev/fake_agent.py) on :18190")
        procs = [start_scripted_agent(18190, key)]
        try:
            if args.with_chat:
                import tempfile
                sessions = Path(tempfile.mkdtemp(prefix="spe-threat-sessions-"))
                print(f"starting the chat UI on :13190, journals in {sessions}")
                procs.append(start_chat_ui(13190, args.agent_url, key, sessions))
                args.chat_url = "http://127.0.0.1:13190/api/copilotkit/agent/spe/run"
            results = execute(cases, args)
        finally:
            for p in procs:
                p.terminate()
        write_report(results, args, "selftest against the scripted agent")
        bad = [r for r in results if r.get("as_expected") is False or r.get("verdict") == "error"]
        return 1 if bad else 0

    if not (args.agent_url or args.chat_url or args.ssh):
        ap.error("give --agent-url, --chat-url or --ssh")
    paid = [c for c in cases if not gate(c, args) and c["kind"] == "run" and c["requires"] == "model"]
    if paid:
        n = sum(int(args.trials or c["trials"]) * len([t for t in c["targets"] if {"agent": args.agent_url, "chat": args.chat_url}.get(t)]) for c in paid)
        print(f"paid: {n} agent runs (each may make several model requests, at most 50)")
    results = execute(cases, args)
    write_report(results, args, "run")
    return 1 if any(r.get("verdict") == "error" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
