"""promptfoo provider for promptfoo's own model roles: the attacker and the grader.

`redteam.provider` and `defaultTest.options.provider` in the generated promptfoo config point here
(`file://pf_model.py`, `config: {role: attacker|grader, run_dir, lab_config, max_model_calls}`), so
promptfoo never talks to a model directly:

* the role's model comes from lab.yaml (`roles:` -> `models:`), whatever backend it is, Claude Code
  included; promptfoo never sees an API key;
* every call is counted against `max_model_calls` (a locked file in the run dir) and refused past it;
* a paid backend is refused unless threatlab started promptfoo with --allow-paid-models
  (THREATLAB_ALLOW_PAID=1 in promptfoo's environment);
* each call's provenance (backend, model, prompt hash, usage; not the prompt) goes to model_calls.jsonl.

The grader only steers promptfoo's search and its early stop. It never sets a verdict: that is
`threatlab.py pf-evaluate`, from indicators.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

_generators: dict[str, object] = {}


def _generator(lab_config: str):
    if lab_config not in _generators:
        import lab_llm
        import threatlab
        cfg = threatlab.load_config(Path(lab_config))
        cfg["allow_paid_models"] = os.environ.get("THREATLAB_ALLOW_PAID") == "1"
        _generators[lab_config] = lab_llm.Generator(**threatlab.gen_kwargs(cfg))
    return _generators[lab_config]


def messages_of(prompt: str) -> list[dict]:
    """promptfoo hands a role either plain text or a chat as a JSON array of {role, content}."""
    try:
        parsed = json.loads(prompt)
    except (ValueError, TypeError):
        parsed = None
    if isinstance(parsed, list) and parsed and all(isinstance(m, dict) and "role" in m for m in parsed):
        return [{"role": str(m["role"]), "content": m.get("content") if isinstance(m.get("content"), str)
                 else json.dumps(m.get("content"))} for m in parsed]
    return [{"role": "user", "content": str(prompt)}]


def wants_json(messages: list[dict]) -> bool:
    text = " ".join(str(m.get("content") or "") for m in messages if m.get("role") == "system")[:20000].lower()
    return "json" in text or "json" in str(messages[-1].get("content") or "")[-2000:].lower()


def call_api(prompt: str, options: dict | None = None, context: dict | None = None) -> dict:
    import lab_models
    import pf_provider
    cfg = (options or {}).get("config") or {}
    role = cfg.get("role")
    if role not in ("attacker", "grader"):
        return {"error": f"pf_model: config.role must be attacker or grader, not {role!r}"}
    run_dir = Path(cfg.get("run_dir") or ".")
    limit = int(cfg.get("max_model_calls") or 0)
    msgs = messages_of(prompt)
    try:
        gen = _generator(cfg.get("lab_config") or str(HERE / "lab.yaml"))
        gen._check_paid(role)  # before counting: a refused call uses no budget
        if not limit or pf_provider.take_slot(run_dir / "model_calls.count", limit) is None:
            return {"error": f"model budget reached: max_model_calls {limit}"}
        text, prov = gen.complete(role, msgs, json_mode=wants_json(msgs))
    except lab_models.PaidNotAllowed as e:
        return {"error": str(e)}
    except lab_models.Refused:
        return {"output": "I can't help with that.", "metadata": {"refused": True}}
    except (RuntimeError, SystemExit, OSError) as e:
        return {"error": f"pf_model ({role}): {str(e)[:300]}"}
    pf_provider.append_row(run_dir / "model_calls.jsonl", {k: prov.get(k) for k in (
        "role", "backend", "model", "endpoint_host", "when", "prompt_sha256", "stop_reason", "usage")})
    usage = prov.get("usage") or {}
    prompt_t = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
    compl_t = usage.get("completion_tokens") or usage.get("output_tokens") or 0
    return {"output": text, "tokenUsage": {"prompt": prompt_t, "completion": compl_t, "total": prompt_t + compl_t,
                                           "numRequests": 1}}
