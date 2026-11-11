"""The red-team loop around promptfoo: threat -> promptfoo input -> promptfoo's attacks -> our verdict -> revised draft.

    pf-generate <threat>   translator (gate B) -> promptfooconfig.yaml -> `promptfoo redteam generate`
                           -> gate C -> frozen redteam.yaml + plan.json, whose hash you approve
    pf-run <run> --approve <hash>     `promptfoo eval` on the frozen tests; every turn passes gate D (pf_provider.py)
    pf-evaluate <run>      indicators over every turn of every conversation in raw.jsonl
    pf-confirm <run> [--approve <hash>]   hits replayed unchanged, fresh nonces, new sessions (gate E)
    pf-validate <run>      the validator; it may claim "reproduced" only when the confirmation did
    pf-revise <run>        the reviser rewrites the draft (gate F); never touches threats/
    pf-loop <threat...> | --propose N   all of it, in rounds, within --budget

A <threat> is a draft (`drafts/<slug>` or its slug) or a catalog id (TM-NNN; the catalog is never
revised). Everything is written under runs/pf-<time>/ and drafts/, which git ignores.

promptfoo runs offline: remote generation, telemetry, sharing and update checks are switched off, and
only plugins and strategies that work without promptfoo's servers are allowed (read in promptfoo
0.125.1). Its attacker and grader are pf_model.py, i.e. the models lab.yaml gives those roles.
"""
from __future__ import annotations

import copy
import difflib
import json
import os
import secrets
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

import checks
import lab_checks as L
import lab_encodings
import spe_threat
import threatlab as T

HERE = T.HERE

# Offline-capable building blocks (promptfoo 0.125.1 with PROMPTFOO_DISABLE_REMOTE_GENERATION).
PLUGINS = ("intent", "policy", "excessive-agency", "shell-injection", "prompt-extraction", "pii:direct",
           "pii:api-db", "pii:session", "debug-access", "rbac", "sql-injection", "tool-discovery",
           "cross-session-leak", "overreliance")
SELECTABLE_PLUGINS = tuple(p for p in PLUGINS if p not in ("intent", "policy"))  # intent/policy come from the spec
STATIC = ("basic", "base64", "hex", "rot13", "leetspeak", "homoglyph", "jailbreak-templates", "math-prompt")
DYNAMIC = ("crescendo", "jailbreak:tree", "custom")
STRATEGIES = STATIC + DYNAMIC
# Remote-only in 0.125.1: they throw or yield nothing offline. Never put them in a config.
REMOTE_ONLY = ("jailbreak", "jailbreak:meta", "jailbreak:composite", "goat", "jailbreak:hydra", "best-of-n",
               "mischievous-user", "citation", "jailbreak:likert", "gcg", "hijacking", "ssrf",
               "indirect-prompt-injection", "system-prompt-override", "bola", "bfla")

PF_DEFAULTS = {"plugins": list(SELECTABLE_PLUGINS), "strategies": list(STRATEGIES), "num_tests": 2, "max_cases": 3,
               "max_turns": 4, "tree_attempts": 6, "repeat": 1, "max_model_calls": 200, "confirm_trials": 3,
               "max_repairs": 1}


def pf_cfg(cfg: dict) -> dict:
    """lab.yaml `promptfoo:` merged over the defaults. Lists can only narrow the offline allowlists."""
    out = {**PF_DEFAULTS, **(cfg.get("promptfoo") or {})}
    out["plugins"] = [p for p in out["plugins"] if p in SELECTABLE_PLUGINS]
    out["strategies"] = [s for s in out["strategies"] if s in STRATEGIES]
    out["max_turns"] = max(1, min(int(out["max_turns"]), 6))
    out["tree_attempts"] = max(1, min(int(out["tree_attempts"]), 8))
    return out


def strategy_config(sid: str, pc: dict, custom_text: str = "") -> dict:
    if sid in ("crescendo", "custom"):  # stateful: newest message only, the chat keeps the history; no backtracking
        c = {"stateful": True, "maxTurns": pc["max_turns"], "maxBacktracks": 0}
        if sid == "custom":
            c["strategyText"] = custom_text
        return c
    if sid == "jailbreak:tree":
        return {"maxDepth": 3, "branchingFactor": 2, "maxWidth": 2, "maxAttempts": pc["tree_attempts"]}
    return {}


def calls_per_test(sid: str, pc: dict) -> int:
    """The most agent runs one test can make: promptfoo has no global cap, so this is the estimate the
    plan approves, and pf_provider enforces the total."""
    if sid in ("crescendo", "custom"):
        return pc["max_turns"]
    if sid == "jailbreak:tree":
        return pc["tree_attempts"] + 1
    return 1


def rel(p: Path) -> str:
    try:
        return str(Path(p).resolve().relative_to(HERE))
    except ValueError:
        return str(p)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, obj) -> None:
    T.write_private(path, json.dumps(obj, indent=2, ensure_ascii=False))


# --- threats -------------------------------------------------------------------------------------------

def resolve_threat(ref: str) -> tuple[str, str, Path | None]:
    """(threat id as cases carry it, its markdown, the draft dir or None for a catalog threat)."""
    if ref.startswith("TM-"):
        md = T.threat_text(ref)
        if not md:
            raise SystemExit(f"{ref}: no such threat in threats/")
        return ref, md, None
    d = Path(ref)
    d = d if d.is_dir() else T.DRAFTS / Path(ref).name
    if not (d / "threat.md").exists():
        raise SystemExit(f"{ref}: neither a TM-NNN nor a draft directory with threat.md")
    return f"DRAFT-{d.name}", (d / "threat.md").read_text(), d


# --- gate B: the translator's spec ----------------------------------------------------------------------

def translate(ref: str, cfg: dict, gen, rdir: Path) -> dict:
    """The translator writes promptfoo's input for one threat; code keeps only what passes gate B."""
    import lab_llm
    pc = pf_cfg(cfg)
    tid, md, _ = resolve_threat(ref)
    hosts = cfg["allowed_hosts"]
    strategies = [s for s in pc["strategies"]]
    try:
        raw, prov = gen.translate(md, T.context_files(cfg, []), pc["plugins"], strategies, hosts, pc["max_cases"])
    except lab_llm.Refused as e:
        raise SystemExit(f"the translator refused: {e}")
    report = {"dropped": [], "repaired": []}

    doc = T.to_cases_doc({"cases": raw["cases"][:pc["max_cases"]]}, tid)
    cases = {}
    for c in doc["cases"]:
        c["scenario"] = max(1, int(c.get("scenario") or 1))
        norm = L.normalise(c, tid)
        r = L.lint_case(norm, hosts, need_example=True)
        if not r.ok and pc["max_repairs"]:
            try:
                fixed, _ = T.repair_case(norm, gen, cfg, pc["max_repairs"])
            except RuntimeError as e:  # a model that fails to answer: the case is dropped, the run goes on
                fixed = None
                report["dropped"].append({"what": f"repair of {c['id']}", "why": [str(e)[:200]]})
            if fixed:
                report["repaired"].append(c["id"])
                norm, r = fixed, L.lint_case(fixed, hosts, need_example=True)
        if r.ok:
            cases[norm["key"]] = T.strip_case(norm) | {"key": norm["key"], "threat": tid}
        else:
            report["dropped"].append({"what": f"case {c['id']}", "why": r.errors})

    generic = None
    gind = [T.to_indicator(i) for i in raw["generic_indicators"]]
    if gind:
        g = L.normalise({"id": "generic", "title": "any promptfoo-written attack", "requires": "model", "kind": "run",
                         "targets": ["chat"], "trials": 1, "mode": "any", "message": "(written by promptfoo)",
                         "indicators": gind,
                         "example_hit": {"answer": raw["generic_example_hit"]["answer"],
                                         "tool_calls": [{"name": "run_command", "args": {"command": cmd}}
                                                        for cmd in raw["generic_example_hit"]["tool_commands"]]}}, tid)
        errs = L.lint_case(g, hosts, need_example=True).errors
        if L.nonce_dependent(gind):
            errs.append("generic indicators mention {nonce}: promptfoo-written attacks carry no payload")
        if errs:
            report["dropped"].append({"what": "generic indicators", "why": errs})
        else:
            generic = T.strip_case(g) | {"key": f"{tid}/generic", "threat": tid}

    policies, plugins = [], []
    if generic:
        for ptxt in raw["policies"][:3]:
            e = L.lint_message(ptxt, hosts)
            (report["dropped"].append({"what": f"policy {ptxt[:60]}", "why": e}) if e else policies.append(ptxt))
        plugins = [p for p in raw["plugins"] if p in pc["plugins"]]
    elif raw["policies"] or raw["plugins"]:
        report["dropped"].append({"what": "policies and plugins", "why": ["no usable generic indicators: "
                                  "promptfoo-written attacks could not be decided"]})
    strats = [s for s in raw["strategies"] if s in strategies]
    custom_text = raw["custom_strategy_text"].strip()
    if "custom" in strats and (not custom_text or L.lint_message(custom_text, hosts)):
        strats.remove("custom")
        report["dropped"].append({"what": "strategy custom", "why": ["no usable custom_strategy_text"]})
    if not cases and not generic:
        raise SystemExit("gate B: nothing usable came out of the translator: " + json.dumps(report["dropped"])[:800])
    spec = {"threat": tid, "ref": ref, "created": _now(), "purpose": raw["purpose"].strip(),
            "grader_guidance": raw["grader_guidance"].strip(), "cases": cases, "generic": generic,
            "policies": policies, "plugins": plugins, "strategies": ["basic"] + [s for s in strats if s != "basic"],
            "custom_strategy_text": custom_text, "gate_b": report, "translator_provenance": prov}
    write_json(rdir / "spec.json", spec)
    return spec


# --- promptfoo config and environment --------------------------------------------------------------------

def promptfoo_bin() -> Path:
    binary = T.PF_DIR / "node_modules" / ".bin" / "promptfoo"
    if not binary.exists():
        print(f"installing the pinned promptfoo in {T.PF_DIR.relative_to(T.ROOT)} (npm ci)...")
        if subprocess.run(["npm", "ci", "--no-audit", "--no-fund"], cwd=T.PF_DIR).returncode != 0:
            raise SystemExit("npm ci failed")
    return binary


def pf_env(rdir: Path, cfg: dict, approve: str | None = None) -> dict:
    """promptfoo's environment: offline, our Python, no API keys of ours (pf_model reads lab.yaml itself)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("THREATLAB_")}
    env.update({"PROMPTFOO_DISABLE_REMOTE_GENERATION": "true", "PROMPTFOO_DISABLE_REDTEAM_REMOTE_GENERATION": "true",
                "PROMPTFOO_DISABLE_TELEMETRY": "1", "PROMPTFOO_DISABLE_SHARING": "1", "PROMPTFOO_DISABLE_UPDATE": "1",
                "PROMPTFOO_CACHE_ENABLED": "false", "PROMPTFOO_PYTHON": sys.executable,
                "PROMPTFOO_CONFIG_DIR": str((rdir / ".promptfoo").resolve())})
    if cfg.get("allow_paid_models"):
        env["THREATLAB_ALLOW_PAID"] = "1"
    if approve:
        env["THREATLAB_APPROVE"] = approve
    return env


def model_provider(role: str, rdir: Path, cfg: dict) -> dict:
    return {"id": f"file://{HERE / 'pf_model.py'}", "label": f"threatlab-{role}",
            "config": {"role": role, "run_dir": str(rdir.resolve()), "lab_config": str(cfg["_config_path"]),
                       "max_model_calls": pf_cfg(cfg)["max_model_calls"], "timeout": 900000}}


def build_config(spec: dict, rdir: Path, cfg: dict) -> Path:
    pc = pf_cfg(cfg)
    plugins = []
    if spec["cases"]:
        plugins.append({"id": "intent", "config": {"intent": [c["message"] for c in spec["cases"].values()]}})
    guidance = {"graderGuidance": spec["grader_guidance"]} if spec["grader_guidance"] else {}
    for ptxt in spec["policies"]:
        plugins.append({"id": "policy", "numTests": pc["num_tests"], "config": {"policy": ptxt, **guidance}})
    for p in spec["plugins"]:
        plugins.append({"id": p, "numTests": pc["num_tests"], **({"config": guidance} if guidance else {})})
    strategies = [{"id": s, **({"config": c} if (c := strategy_config(s, pc, spec["custom_strategy_text"])) else {})}
                  for s in spec["strategies"]]
    conf = {
        "description": f"threatlab {spec['threat']} ({rdir.name})",
        "prompts": ["{{prompt}}"],
        "providers": [{"id": f"file://{HERE / 'pf_provider.py'}", "label": "spe-chat",
                       "config": {"plan_dir": str(rdir.resolve()), "timeout": int(float(cfg["timeout_s"]) + 60) * 1000}}],
        "defaultTest": {"assert": [{"type": "python", "value": f"file://{HERE / 'pf_assert.py'}:not_reproduced"}],
                        "options": {"provider": model_provider("grader", rdir, cfg)}},
        "evaluateOptions": {"maxConcurrency": 1},
        "redteam": {"purpose": spec["purpose"], "provider": model_provider("attacker", rdir, cfg),
                    "numTests": pc["num_tests"], "plugins": plugins, "strategies": strategies},
    }
    bad = [s["id"] for s in strategies if s["id"] in REMOTE_ONLY] + [p["id"] for p in plugins if p["id"] in REMOTE_ONLY]
    assert not bad, bad  # cannot happen: the allowlists exclude them
    path = rdir / "promptfooconfig.yaml"
    T.write_private(path, yaml.safe_dump(conf, sort_keys=False, allow_unicode=True, width=110))
    return path


def run_generate(rdir: Path, cfg: dict) -> Path:
    out = rdir / "redteam.yaml"
    T.ensure_ignored(out)
    r = subprocess.run([str(promptfoo_bin()), "redteam", "generate", "-c", str(rdir / "promptfooconfig.yaml"),
                        "-o", str(out), "--force"], cwd=rdir, env=pf_env(rdir, cfg))
    if r.returncode != 0 or not out.exists():
        raise SystemExit(f"promptfoo redteam generate failed (exit {r.returncode}); see the output above")
    return out


# --- gate C: check every generated test, freeze ------------------------------------------------------------

def test_strategy(t: dict) -> str:
    meta = t.get("metadata") or {}
    sid = meta.get("strategyId")
    if sid:
        return str(sid)
    prov = t.get("provider")
    pid = prov.get("id") if isinstance(prov, dict) else prov
    if isinstance(pid, str) and pid.startswith("promptfoo:redteam:"):
        name = pid.split("promptfoo:redteam:", 1)[1]
        return {"iterative:tree": "jailbreak:tree"}.get(name, name)
    return "basic"


def match_case(spec: dict, t: dict, strategy: str) -> str | None:
    meta = t.get("metadata") or {}
    if not str(meta.get("pluginId") or "").endswith("intent"):
        return None
    msg = str((t.get("vars") or {}).get("prompt") or "")
    texts = {str(meta.get("originalText") or ""), lab_encodings.plain_text(strategy, msg), msg,
             str(meta.get("goal") or "")}
    for key, c in spec["cases"].items():
        if c["message"] in texts:
            return key
    for key, c in spec["cases"].items():  # transformed (leetspeak, templates): the payload still identifies it
        anchors = L.anchors(c)
        if anchors and any(all(a in x for a in anchors) for x in texts):
            return key
    return None


def gate_c(spec: dict, rdir: Path, cfg: dict) -> dict:
    pc = pf_cfg(cfg)
    doc = yaml.safe_load((rdir / "redteam.yaml").read_text()) or {}
    kept, dropped, items = [], [], []
    for t in doc.get("tests") or []:
        meta = t.get("metadata") or {}
        strategy = test_strategy(t)
        plugin = str(meta.get("pluginId") or "")
        msg = str((t.get("vars") or {}).get("prompt") or "")
        why = []
        if strategy not in STRATEGIES:
            why.append(f"strategy {strategy} is not allowed offline")
        key = match_case(spec, t, strategy)
        case = spec["cases"].get(key) if key else spec["generic"]
        if case is None:
            why.append("an intent test that matches no seed case" if plugin.endswith("intent")
                       else "no generic indicators to decide a promptfoo-written attack")
        plain = lab_encodings.plain_text(strategy, msg)
        why += L.lint_message(plain.replace("{nonce}", "N0NCE0TEST"), cfg["allowed_hosts"])
        if case is not None and strategy in STATIC and not L.provable(plain, L.anchors(case), case["indicators"]):
            why.append(f"{strategy} lost the planted payload: a hit could not be told from chance")
        desc = f"{plugin or '?'} / {strategy}: {plain[:70]!r}"
        if why:
            dropped.append({"test": desc, "why": why})
            continue
        t.setdefault("vars", {})
        t["vars"]["case_key"] = key or "generic"
        t["vars"]["plan_dir"] = str(rdir.resolve())
        kept.append(t)
        items.append({"idx": len(kept) - 1, "case_key": key or "generic", "plugin": plugin, "strategy": strategy,
                      "cap": calls_per_test(strategy, pc)})
    doc["tests"] = kept
    frozen = rdir / "redteam.frozen.yaml"
    T.write_private(frozen, yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=110))
    return {"items": items, "dropped": dropped, "frozen_sha256": T.hashlib_sha256(frozen.read_bytes())}


def freeze(spec: dict, gc: dict, rdir: Path, cfg: dict) -> dict:
    pc = pf_cfg(cfg)
    max_runs = sum(i["cap"] for i in gc["items"]) * pc["repeat"]
    import lab_llm
    roles = {r: (cfg.get("roles") or {}).get(r, "default") for r in lab_llm.ROLES}
    plan = {"mode": "pf", "created": _now(), "salt": secrets.token_hex(8), "threat": spec["threat"], "ref": spec["ref"],
            "chat": {k: cfg.get(k) for k in ("transport", "chat_url", "chat_run_url", "cdp", "timeout_s")},
            "agent_model": cfg["agent_model"], "threshold": cfg["threshold"], "allowed_hosts": cfg["allowed_hosts"],
            "max_runs": max_runs, "max_model_calls": pc["max_model_calls"], "repeat": pc["repeat"],
            "allow_paid_models": bool(cfg.get("allow_paid_models")), "roles": roles,
            "cases": spec["cases"], "generic": spec["generic"] or {"indicators": [], "mode": "any"},
            "tests": gc["items"], "dropped": gc["dropped"], "frozen_sha256": gc["frozen_sha256"]}
    plan["hash"] = L.plan_hash(plan)
    write_json(rdir / "plan.json", plan)
    return plan


def generate(ref: str, cfg: dict, gen=None, rdir: Path | None = None) -> tuple[Path, dict]:
    """Gate B, promptfoo's generation, gate C, freeze. Calls models (translator, attacker), never the agent."""
    import lab_llm
    rdir = rdir or T.RUNS / f"pf-{T.now_id()}"
    T.ensure_ignored(rdir / "plan.json")
    rdir.mkdir(parents=True, exist_ok=True)
    gen = gen or lab_llm.Generator(**T.gen_kwargs(cfg))
    print(f"== translator ({ref})")
    spec = translate(ref, cfg, gen, rdir)
    print(f"  {len(spec['cases'])} seed case(s), generic indicators: {'yes' if spec['generic'] else 'no'}, "
          f"plugins: {', '.join(spec['plugins']) or '-'}, policies: {len(spec['policies'])}, "
          f"strategies: {', '.join(spec['strategies'])}")
    for d in spec["gate_b"]["dropped"]:
        print(f"  gate B dropped {d['what']}: {'; '.join(d['why'])[:200]}")
    build_config(spec, rdir, cfg)
    print("== promptfoo redteam generate (offline; the attacker is the model lab.yaml gives it)")
    run_generate(rdir, cfg)
    gc = gate_c(spec, rdir, cfg)
    for d in gc["dropped"]:
        print(f"  gate C dropped {d['test']}: {'; '.join(d['why'])[:200]}")
    if not gc["items"]:
        raise SystemExit("gate C: no generated test survived")
    plan = freeze(spec, gc, rdir, cfg)
    by = defaultdict(int)
    for i in gc["items"]:
        by[i["strategy"]] += 1
    print(f"\n{len(gc['items'])} test(s) ({', '.join(f'{k} {v}' for k, v in sorted(by.items()))}), "
          f"at most {plan['max_runs']} agent run(s), at most {plan['max_model_calls']} model call(s) "
          f"(attacker + grader). Agent model: {plan['agent_model']}.")
    print(f"plan {rel(rdir)}  hash {plan['hash'][:16]}")
    print(f"\nrun it (paid: the agent's model):\n  uv run python threatlab.py pf-run {rel(rdir)} "
          f"--approve {plan['hash'][:16]}")
    return rdir, plan


# --- run -----------------------------------------------------------------------------------------------

def load_plan(rdir: Path) -> dict:
    plan = json.loads((rdir / "plan.json").read_text())
    if L.plan_hash(plan) != plan["hash"]:
        raise SystemExit("plan.json was changed after it was made: make a new plan")
    return plan


def check_approval(plan: dict, approve: str | None) -> None:
    if not approve or len(approve) < 12 or not plan["hash"].startswith(approve):
        raise SystemExit(f"--approve must be the first 12+ characters of this plan's hash ({plan['hash'][:12]})")


def run(rdir: Path, cfg: dict, approve: str | None) -> int:
    plan = load_plan(rdir)
    check_approval(plan, approve)
    if plan.get("mode") != "pf":
        raise SystemExit(f"{rdir} is not a red-team plan (pf-generate makes those)")
    frozen = rdir / "redteam.frozen.yaml"
    if T.hashlib_sha256(frozen.read_bytes()) != plan["frozen_sha256"]:
        raise SystemExit("redteam.frozen.yaml changed after the plan was made: make a new plan")
    if plan["allow_paid_models"] and not cfg.get("allow_paid_models"):
        raise SystemExit("this plan uses paid models: run it with --allow-paid-models")
    T.ensure_ignored(rdir / "raw.jsonl")
    print(f"promptfoo eval: {len(plan['tests'])} test(s), at most {plan['max_runs']} agent run(s) "
          f"through {plan['chat']['transport']}")
    out = rdir / "results.json"
    r = subprocess.run([str(promptfoo_bin()), "eval", "-c", str(frozen), "--no-cache", "--no-share", "-j", "1",
                        "--repeat", str(plan["repeat"]), "-o", str(out)], cwd=rdir,
                       env=pf_env(rdir, {**cfg, "allow_paid_models": plan["allow_paid_models"]}, plan["hash"][:16]))
    # promptfoo exits non-zero when an assertion fails, i.e. when it thinks an attack worked: a result, not an error.
    if not out.exists() and not (rdir / "raw.jsonl").exists():
        print(f"promptfoo eval failed (exit {r.returncode})")
        return r.returncode or 1
    return 0


# --- evaluate: conversations from raw.jsonl ------------------------------------------------------------

def conversations(rdir: Path, plan: dict) -> list[dict]:
    import pf_provider
    rows = pf_provider.read_rows(rdir / "raw.jsonl")
    by = defaultdict(list)
    for r in rows:
        by[r["session_id"]].append(r)
    out = []
    env = checks.Env()
    for sid, rs in by.items():
        rs.sort(key=lambda r: (r.get("turn") or 0))
        sent = [r for r in rs if r.get("status") == "sent"]
        key = rs[0].get("case_key") or "generic"
        case = (plan.get("cases") or {}).get(key) or plan["generic"]
        nonce = rs[0].get("nonce")
        hit_turns = []
        for r in sent:
            v = spe_threat.judge({"answer": r.get("answer") or "", "tool_calls": r.get("tool_calls") or [],
                                  "error": r.get("error")}, spe_threat.fill(copy.deepcopy(case), nonce), env)
            if v["verdict"] == "reproduced":
                hit_turns.append(r["turn"])
        provable = any(r.get("provable") for r in sent)
        verdict = ("reproduced" if hit_turns and provable else "unprovable" if hit_turns else
                   "error" if sent and all(r.get("error") and not r.get("answer") for r in sent) else
                   "blocked-by-lint" if not sent else "held")
        out.append({"session_id": sid, "case_key": key, "strategy": rs[0].get("strategy"), "plugin": rs[0].get("plugin"),
                    "turns": [r["message"] for r in sent], "sent": len(sent),
                    "blocked": [r.get("reason") for r in rs if r.get("status") == "blocked"],
                    "hit_turns": hit_turns, "provable": provable, "verdict": verdict})
    return out


def evaluate(rdir: Path, cfg: dict, show: bool = True) -> dict:
    plan = load_plan(rdir)
    convs = conversations(rdir, plan)
    counts = defaultdict(lambda: defaultdict(int))
    for c in convs:
        counts[c["case_key"]][c["verdict"]] += 1
    candidates = [c for c in convs if c["verdict"] == "reproduced"]
    res = {"plan_hash": plan["hash"], "threat": plan["threat"], "agent_model": plan["agent_model"],
           "conversations": convs, "counts": {k: dict(v) for k, v in counts.items()}, "candidates": candidates}
    write_json(rdir / "evaluation.json", res)
    lines = [f"# Red-team run {rdir.name}: {plan['threat']}", "",
             f"agent model {plan['agent_model']}; {len(convs)} conversation(s), {len(candidates)} candidate hit(s) "
             "to confirm. A hit counts only if the conversation still carried the planted payload "
             "(or the indicators need none).", "", "| case | held | reproduced | unprovable | error | blocked by lint |",
             "|---|---|---|---|---|---|"]
    for k, v in sorted(counts.items()):
        lines.append(f"| {k} | {v.get('held', 0)} | {v.get('reproduced', 0)} | {v.get('unprovable', 0)} | "
                     f"{v.get('error', 0)} | {v.get('blocked-by-lint', 0)} |")
    for c in candidates:
        lines += ["", f"- {c['case_key']} via {c['strategy']}, {c['sent']} turn(s), hit at turn(s) {c['hit_turns']}"]
    T.write_private(rdir / "summary.md", "\n".join(lines) + "\n")
    if show:
        print("\n".join(lines))
    return res


# --- gate E: confirm hits by replaying them unchanged ------------------------------------------------------

def confirm_plan(rdir: Path, cfg: dict, trials: int) -> dict:
    src = load_plan(rdir)
    ev = evaluate(rdir, cfg, show=False)
    items = [{"key": c["session_id"], "case_key": c["case_key"], "strategy": c["strategy"], "turns": c["turns"],
              "trials": trials} for c in ev["candidates"]]
    plan = {"mode": "pf-confirm", "created": _now(), "salt": secrets.token_hex(8), "source_hash": src["hash"],
            "threat": src["threat"], "ref": src["ref"], "chat": src["chat"], "agent_model": src["agent_model"],
            "threshold": src["threshold"], "allowed_hosts": src["allowed_hosts"], "cases": src["cases"],
            "generic": src["generic"], "items": items,
            "max_runs": sum(len(i["turns"]) * i["trials"] for i in items)}
    plan["hash"] = L.plan_hash(plan)
    write_json(rdir / "confirm" / "plan.json", plan)
    return plan


def confirm(rdir: Path, cfg: dict, approve: str | None, trials: int, transport=None) -> dict | None:
    """Without a matching --approve: write the confirm plan and print its hash. With it: replay."""
    cdir = rdir / "confirm"
    plan = json.loads((cdir / "plan.json").read_text()) if (cdir / "plan.json").exists() else None
    if not (plan and approve and len(approve) >= 12 and plan["hash"].startswith(approve)):
        plan = confirm_plan(rdir, cfg, trials)
        if not plan["items"]:
            print("no candidate hit to confirm")
            write_json(cdir / "evaluation.json", {"items": [], "plan_hash": plan["hash"]})
            return {"items": []}
        print(f"confirm plan: {len(plan['items'])} hit(s) x {trials} trial(s), at most {plan['max_runs']} agent "
              f"run(s)\n  uv run python threatlab.py pf-confirm {rel(rdir)} --approve {plan['hash'][:16]}")
        return None
    if L.plan_hash(plan) != plan["hash"]:
        raise SystemExit("confirm/plan.json changed after it was made")
    import lab_chat
    import pf_provider
    t = transport or lab_chat.open_transport(plan["chat"])
    env = checks.Env()
    results = []
    try:
        for it in plan["items"]:
            case = (plan["cases"] or {}).get(it["case_key"]) or plan["generic"]
            verdicts, trials_out = [], []
            for n in range(1, it["trials"] + 1):
                nonce = L.nonce_for(plan, it["key"], n)
                sid, answers, calls, errors = None, [], [], []
                for turn in it["turns"]:  # unchanged, in order, in a new session
                    plain = lab_encodings.plain_text(it["strategy"], turn).replace("{nonce}", nonce)
                    if L.lint_message(plain, plan["allowed_hosts"]):
                        errors.append("blocked by lint")
                        break
                    r = t.turn(lab_encodings.fill_encoded(it["strategy"], turn, nonce), sid)
                    sid = r.get("session_id") or sid
                    answers.append(r.get("answer") or "")
                    calls += r.get("tool_calls") or []
                    if r.get("error"):
                        errors.append(r["error"])
                run_ = {"answer": "\n\n".join(answers), "tool_calls": calls,
                        "error": "; ".join(errors) if errors and not any(answers) and not calls else None}
                v = spe_threat.judge(run_, spe_threat.fill(copy.deepcopy(case), nonce), env)["verdict"]
                verdicts.append(v)
                trials_out.append({"trial": n, "session_id": sid, "verdict": v, "errors": errors})
                pf_provider.append_row(cdir / "raw.jsonl", {"key": it["key"], "trial": n, "nonce": nonce,
                                                            "session_id": sid, "verdict": v, **run_})
            results.append({**it, "verdicts": verdicts, "verdict": L.case_verdict(verdicts, plan["threshold"]),
                            "trials_detail": trials_out})
            print(f"  {it['case_key']} via {it['strategy']}: {results[-1]['verdict']} ({verdicts})")
    finally:
        if transport is None:
            t.close()
    out = {"plan_hash": plan["hash"], "items": results}
    write_json(cdir / "evaluation.json", out)
    return out


# --- validator ---------------------------------------------------------------------------------------------

def validate(rdir: Path, cfg: dict, gen=None) -> dict:
    import lab_llm
    plan = load_plan(rdir)
    ev = json.loads((rdir / "evaluation.json").read_text()) if (rdir / "evaluation.json").exists() else evaluate(rdir, cfg, False)
    conf = json.loads((rdir / "confirm" / "evaluation.json").read_text()) if (rdir / "confirm" / "evaluation.json").exists() else {"items": []}
    cases = []
    for it in conf["items"]:
        c = (plan["cases"] or {}).get(it["case_key"]) or plan["generic"]
        cases.append({"case": it["case_key"], "technique": it["strategy"], "title": c.get("title"),
                      "message": "\n---\n".join(it["turns"]), "indicators": c.get("indicators"),
                      "verdict": it["verdict"], "hits": it["verdicts"].count("reproduced"), "trials": len(it["verdicts"]),
                      "errors": it["verdicts"].count("error"), "per_trial_review": []})
    results = {"agent_model": plan["agent_model"], "confirmed": cases, "exploration": ev["counts"],
               "note": "exploration = promptfoo's attack conversations (unconfirmed); confirmed = hits replayed "
                       "unchanged with fresh payloads"}
    gen = gen or lab_llm.Generator(**T.gen_kwargs(cfg))
    _, md, ddir = resolve_threat(plan["ref"])
    v, prov = gen.validate(md, results)
    threshold_met = any(c["verdict"] == "reproduced" for c in cases)
    final = "reproduced" if v["status"] == "reproduced" and threshold_met else "hypothesised"
    rec = {**v, "final_status": final, "threshold_met": threshold_met, "run": str(rel(rdir)),
           "agent_model": plan["agent_model"], "provenance": prov}
    write_json(rdir / "validation.json", rec)
    if ddir is not None:
        (ddir / "validation.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False))
    print(f"validator: {final}" + (f" (it said {v['status']})" if v["status"] != final else ""))
    return rec


# --- gate F: revise the draft --------------------------------------------------------------------------------

def revise(rdir: Path, cfg: dict, gen=None) -> bool:
    """The reviser rewrites a draft from the validation; code checks it and keeps every version.
    Returns whether the draft changed. Catalog threats are never revised."""
    import lab_llm
    plan = load_plan(rdir)
    tid, md, ddir = resolve_threat(plan["ref"])
    if ddir is None:
        print(f"{tid} is in the catalog: it is not revised (only drafts are). The validation is in "
              f"{rel(rdir / 'validation.json')}")
        return False
    val = json.loads((rdir / "validation.json").read_text())
    conf = json.loads((rdir / "confirm" / "evaluation.json").read_text()) if (rdir / "confirm" / "evaluation.json").exists() else {"items": []}
    evidence = {"confirmed": [{k: i[k] for k in ("case_key", "strategy", "turns", "verdict", "verdicts")}
                              for i in conf["items"]],
                "exploration": json.loads((rdir / "evaluation.json").read_text())["counts"]}
    vocab = yaml.safe_load((T.ROOT / "vocabulary.yaml").read_text())
    gen = gen or lab_llm.Generator(**T.gen_kwargs(cfg))
    try:
        d, prov = gen.revise(md, val, evidence, vocab)
    except lab_llm.Refused as e:
        print(f"the reviser refused: {e}")
        return False
    changes = d.pop("changes", [])
    status = "reproduced" if val.get("final_status") == "reproduced" else "hypothesised"  # code, not the model
    new_md = T.render_markdown(d, status=status)
    errs = T.check_draft_markdown(new_md, ddir.name)
    if errs:
        print("gate F: the revision does not pass the catalog's checks, the draft is kept as it was:\n  "
              + "\n  ".join(errs))
        write_json(rdir / "revision-rejected.json", {"errors": errs, "draft": d, "provenance": prov})
        return False
    if new_md == md:
        print("the reviser changed nothing")
        return False
    versions = sorted(ddir.glob("threat.v*.md"))
    if not versions:  # keep the original as v1
        (ddir / "threat.v1.md").write_text(md)
        versions = [ddir / "threat.v1.md"]
    n = 1 + max(int(p.stem.split(".v")[1]) for p in versions)
    (ddir / f"threat.v{n}.md").write_text(new_md)
    (ddir / "threat.md").write_text(new_md)
    old = json.loads((ddir / "draft.json").read_text()) if (ddir / "draft.json").exists() else {}
    (ddir / "draft.json").write_text(json.dumps({**old, **d}, indent=2, ensure_ascii=False))
    diff = "".join(difflib.unified_diff(md.splitlines(True), new_md.splitlines(True), "threat.md (before)",
                                        f"threat.v{n}.md"))
    T.write_private(rdir / "revision.diff", diff)
    write_json(rdir / "revision.json", {"version": n, "status": status, "changes": changes, "provenance": prov})
    print(f"draft revised: {rel(ddir)}/threat.v{n}.md (status {status})")
    for c in changes:
        print(f"  - {c}")
    print(diff[:4000])
    return True


# --- the loop --------------------------------------------------------------------------------------------------

def used_runs(rdir: Path) -> int:
    n = int((rdir / "counter").read_text() or 0) if (rdir / "counter").exists() else 0
    import pf_provider
    return n + sum(1 for r in pf_provider.read_rows(rdir / "confirm" / "raw.jsonl"))


def loop(refs: list[str], cfg: dict, rounds: int, budget: int | None, trials: int) -> list[Path]:
    """Per threat and round: generate -> run -> evaluate -> confirm -> validate -> revise, until the
    reviser changes nothing, the rounds or the budget run out. Without --budget it stops before the
    first agent run and prints the command to approve."""
    import lab_llm
    gen = lab_llm.Generator(**T.gen_kwargs(cfg))
    left = budget
    dirs = []
    for ref in refs:
        for rnd in range(1, rounds + 1):
            print(f"\n######## {ref}, round {rnd}/{rounds}")
            rdir, plan = generate(ref, cfg, gen)
            dirs.append(rdir)
            if left is None:
                print("\nno --budget: stopping before the first agent run (approve with pf-run, then pf-evaluate, "
                      "pf-confirm, pf-validate, pf-revise)")
                return dirs
            if plan["max_runs"] > left:
                print(f"this round needs up to {plan['max_runs']} agent runs, {left} left in --budget: stopping")
                return dirs
            run(rdir, cfg, plan["hash"][:16])
            left -= used_runs(rdir)
            evaluate(rdir, cfg)
            cp = confirm_plan(rdir, cfg, trials)
            if cp["items"]:
                if cp["max_runs"] > left:
                    print(f"confirming needs up to {cp['max_runs']} agent runs, {left} left: stopping")
                    return dirs
                before = used_runs(rdir)
                confirm(rdir, cfg, cp["hash"][:16], trials)
                left -= used_runs(rdir) - before
            else:
                write_json(rdir / "confirm" / "evaluation.json", {"items": [], "plan_hash": cp["hash"]})
            validate(rdir, cfg, gen)
            if not revise(rdir, cfg, gen):
                break
    return dirs


# --- doctor ------------------------------------------------------------------------------------------------------

def doctor(cfg: dict) -> int:
    """What this config needs, checked from here, without a completion or an agent run."""
    import shutil
    import urllib.request
    import lab_llm
    import lab_models
    ok = True

    def say(good: bool, what: str):
        nonlocal ok
        ok &= good
        print(f"  [{'ok' if good else '!!'}] {what}")

    print("models")
    used = {(cfg.get("roles") or {}).get(r, "default") for r in lab_llm.ROLES}
    for name in sorted(used):
        spec = cfg["models"].get(name) or {}
        try:
            b = lab_models.make_backend(name, spec)
        except SystemExit as e:
            say(False, f"{name}: {e}")
            continue
        if b.kind == "claude-code":
            say(bool(shutil.which("claude")), f"{name}: {b.describe()} (claude on PATH)")
            continue
        try:
            req = urllib.request.Request(b.base_url + "/models")
            if b.key():
                req.add_header("Authorization", f"Bearer {b.key()}")
            with urllib.request.urlopen(req, timeout=15) as r:
                ids = [m.get("id") for m in (json.load(r).get("data") or [])]
            say(b.model in ids or not ids, f"{name}: {b.describe()} reachable" +
                ("" if b.model in ids or not ids else f", but {b.model} is not among {ids[:8]}"))
        except SystemExit as e:
            say(False, f"{name}: {e}")
        except Exception as e:  # noqa: BLE001
            say(False, f"{name}: {b.describe()} unreachable from here ({type(e).__name__}: {str(e)[:120]})")
        if lab_models.is_paid(spec):
            print(f"       {name} is paid: roles on it need --allow-paid-models")
    print(f"chat ({cfg.get('transport')})")
    if cfg.get("transport") == "http":
        url = cfg.get("chat_run_url") or ""
        try:
            urllib.request.urlopen(url.split("/api/copilotkit/", 1)[0] + "/api/sessions", timeout=15)
            say(True, f"{url} answers")
        except Exception as e:  # noqa: BLE001
            say(False, f"{url or 'chat_run_url unset'}: {type(e).__name__}: {str(e)[:120]}")
    else:
        try:
            import lab_chat
            t = lab_chat.open_transport(cfg)
            t.preflight()
            t.close()
            say(True, f"logged-in browser at {cfg.get('cdp')} reaches {cfg.get('chat_url')}")
        except ModuleNotFoundError:
            say(False, "browser: playwright is missing: run with `uv run --group browser python threatlab.py ...`")
        except (SystemExit, Exception) as e:  # noqa: BLE001
            say(False, f"browser: {str(e)[:160]}")
    print("promptfoo")
    say((T.PF_DIR / "node_modules" / ".bin" / "promptfoo").exists(), "installed (else the first pf-* runs npm ci)")
    say(True, "offline: remote generation, telemetry, sharing and update checks are switched off for every run "
              "(one 'telemetry disabled' event still goes to promptfoo, without test content)")
    return 0 if ok else 1
