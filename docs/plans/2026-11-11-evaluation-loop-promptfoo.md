# Plan: evaluation-loop around promptfoo, with own models (LiteLLM)

## Context

Today `evaluation-loop/threatlab.py` runs its own loops (`run`, `loop`, `adaptive`) and uses promptfoo
only as an alternative runner/UI (`pf_provider.py`, `pf_assert.py`). Every model role goes through
Claude Code (`claude -p`) in `lab_llm.Generator`.

The user wants the tool built around promptfoo:

1. Proposer drafts a TM →
2. the TM is translated into promptfoo input →
3. promptfoo works the chat with its own red-team loop (plugins, strategies, iterative attacks) →
4. the output is judged by threatlab's deterministic checks →
5. the TM draft is revised and the loop repeats.

Lint and the deterministic checks sit at every handoff (A–F below). The user also wants the
models to be configurable, with an API key in the config, through the team's own **LiteLLM**
proxy (OpenAI-compatible), not only Claude Code.

Decided with the user:
- The revise loop changes **drafts only** (`drafts/<slug>/threat.md`). The catalog still only gains
  new files, through `promote`.
- Own models = **LiteLLM** (one OpenAI-compatible backend: `base_url` + `api_key` + `model`).

Unchanged rules:
- The model never decides a verdict. Indicators and thresholds in code do.
- Paid calls need the human's OK (AGENTS.md).
- Everything except `threats/` stays git-ignored, guarded by `ensure_ignored`.

## Target flow and its gates

```
Proposer ─► drafts/<slug>/threat.md
   A: validate.py checks + duplicate detection            (existing: propose_drafts)
Translator ─► promptfoo red-team spec (purpose, intents with {nonce} payload, plugins/strategies
              from an allowlist, our indicators)
   B: lint intents (L.lint_case), echo test, budget estimate ≤ max_runs
promptfoo redteam generate ─► redteam.yaml (static tests)
   C: lint every generated test, drop failures, freeze → SHA-256, user approves
promptfoo eval (its own iterative/multi-turn loop) ◄─► chat
   D: pf_provider at runtime: lint each outgoing message, payload present, run counter, via api|ui
threatlab evaluate: indicators (checks.py) → winners replayed UNCHANGED N× (new approved plan)
                    → thresholds → Judge/Validator
   E: verdict only from thresholds; validator may say less, never more
Reviser ─► drafts/<slug>/threat.vN.md ─► back to Translator (rounds/budget/no-change stop) ─► promote
   F: validate.py, every status/Evidence claim backed by a confirmed run, diff shown
```

## Work (one worktree, branch `evaluation-loop-promptfoo` from `evaluation-loop`)

Docs first, per the repo convention:
- spec: `docs/specs/2026-11-11-evaluation-loop-promptfoo.md`
- plan: `docs/plans/2026-11-11-evaluation-loop-promptfoo.md`
- progress: `docs/plans/2026-11-11-evaluation-loop-promptfoo-progress.md`, recording rulings and their cost if wrong

The worktree shares `.git/info/exclude`. The local-only `lab.yaml`, `scenarios/` and `runs/` are
symlinked from the main checkout.

### 0. Spike: promptfoo 0.125.1 red-team, offline from promptfoo's servers

This is a read/try step; its findings go to the progress file. Check, in the pinned
`platform/promptfoo-evals`:
- `PROMPTFOO_DISABLE_REDTEAM_REMOTE_GENERATION=true` with `redteam.provider` pointed at LiteLLM
  (promptfoo's `openai:chat:<model>` with `apiBaseUrl`, or its `litellm:` provider).
- Which plugins and strategies work locally (`jailbreak`, `jailbreak:composite`, `crescendo`,
  `goat`, encodings).
- That `redteam generate` writes a file before `eval`.
- How a Python `file://` provider receives multi-turn context.

Any LiteLLM call here is paid: ask first.

### 1. Model backends + API key in config (`lab_llm.py`, `threatlab.py:load_config`)

- Split `Generator._call` into backends with one interface, `call(system, user, schema) -> (data, provenance)`:
  - `ClaudeCodeBackend`: today's code, moved unchanged.
  - `OpenAICompatBackend`: LiteLLM `/v1/chat/completions` over stdlib `urllib`, like
    `platform/promptfoo-evals/agui_provider.py`. It sends `response_format: json_schema`. If that
    is unsupported, it parses the JSON and validates locally (`jsonschema`, new dependency), with
    one retry that carries the validation errors. Refusals map to `Refused`.
- Config, new and backward compatible (an old `generator:` block becomes `models.default` with
  backend `claude-code`):
  ```yaml
  models:
    default: {backend: claude-code, model: haiku}
    litellm: {backend: openai-compatible, base_url: https://litellm.<host>/v1,
              api_key: sk-...,            # or api_key_env: LITELLM_KEY / api_key_file: ~/.litellm_key
              model: qwen3.8-27b, paid: true}
  roles:                                  # optional; missing roles use default
    proposer: default
    judge: litellm
    attacker: litellm                     # promptfoo's red-team provider
    grader: litellm                       # promptfoo's loop steering only, never the verdict
  ```
- Key safety:
  - `load_config` refuses an inline `api_key` unless `lab.yaml` is git-ignored (`ensure_ignored`)
    and warns unless the file is 0600.
  - The key never appears in provenance, logs, `plan.json` or the generated promptfoo configs. It
    reaches promptfoo through an env var such as `OPENAI_API_KEY`/`LITELLM_API_KEY`, set only for
    the subprocess.
  - Provenance records backend, model, the `base_url` host and usage.
- Paid guard: a role whose backend has `paid: true` runs only with `--allow-paid-models`. Every
  command prints which roles will call which model before it starts.
- `Generator` keeps its role methods (`propose`, `write_tests`, `judge`, `validate`, `refine`,
  `variants`, `repair`) and resolves the backend per role.

### 2. Runtime gate in the provider (gate D, `pf_provider.py`)

- Add `L.lint_message(text, anchors, hosts)` in `lab_checks.py`, reusing the checks inside
  `L.lint_case`: forbidden commands, hosts, secret-shaped strings without `{nonce}`.
- Before sending, the provider:
  - lints the message; a failing message is not sent, returns `{error: "blocked by lint: …"}` and
    is logged to `raw.jsonl` as `blocked`;
  - requires an anchor or the nonce payload, so a hit can be proven; without one the message is
    sent but marked `unprovable`, and it can never count as `reproduced`;
  - takes a slot from a run counter (a file in the plan dir with a lock) and stops at `max_runs`.
- Honour `via: api|ui` from `lab.yaml`. Today it is always api.
- Multi-turn: pass promptfoo's conversation history through `spe_threat.run_input` (`history`),
  as the spike found it.
- Each `raw.jsonl` row records the promptfoo test id, plugin, strategy and turn.

### 3. Translator: TM → promptfoo red-team spec (gate B)

- New role prompt `TRANSLATOR` in `lab_llm.py`, with a JSON schema. From `threat.md` it writes:
  - `purpose` (the agent's role from the context files),
  - 1–5 intents, each a seed prompt carrying a `{nonce}` payload plus anchors,
  - our indicators (reusing `_case_schema` fields),
  - plugins/strategies chosen only from `promptfoo.allowed_plugins` / `allowed_strategies` in `lab.yaml`.
- Code (`threatlab.py`, new `pf_spec.py`) builds `runs/<id>/promptfoo/redteam-config.yaml`:
  - target `file://pf_provider.py`, `redteam.provider` = the attacker role, grader = the grader role,
  - remote generation disabled through the env.
- Gate B:
  - every intent passes through `L.lint_case` as a case, including the echo test and `example_hit`;
    `repair()` gets up to `--max-repairs` tries;
  - budget estimate: intents × (1 + strategies) × `numTests` × repeat × max turns ≤ `max_runs`,
    otherwise the command refuses and says what to cut.

### 4. Generate → gate C → freeze

`threatlab.py pf-generate drafts/<slug>`:
1. Runs `promptfoo redteam generate` and writes `redteam.yaml`. This calls the attacker model,
   so it is paid if LiteLLM is.
2. Lints every static test, drops the failures and lists them.
3. Freezes the file plus the spec into `plan.json`, reusing `L.plan_hash`, with salt and
   `max_runs`, and prints the hash.

### 5. Run promptfoo's loop

`threatlab.py pf-run runs/<id> --approve <hash>`:
- generalises today's `run_promptfoo` and `promptfoo_env` (`threatlab.py`);
- sets `THREATLAB_APPROVE` and the model env for the subprocess only;
- runs `promptfoo redteam eval`, or `eval` on `redteam.yaml`;
- every turn lands in `raw.jsonl` through the provider.

### 6. Evaluate + confirm (gate E)

- Reuse `evaluate_dir` (indicators via `spe_threat.judge` / `checks.py`). An optional per-trial
  Judge uses the configured role model.
- Winners are rows with a hit. They become a confirmation plan: the exact message, history
  included, replayed unchanged `--confirm N` times through the existing run path (`cmd_run` /
  `lab_browser`). This needs its own approval hash.
- Only confirmed hits meeting `max(2, threshold)` count as `reproduced`. This reuses the threshold
  logic in `lab_checks`.
- Run the Validator (`validate_loop`) on the confirmed results.

### 7. Reviser (gate F, drafts only)

- New role `REVISER`. It gets the threat draft, the validation and the confirmed evidence, and
  writes a revised `threat.md`: refined scenarios, Evidence, a suggested status.
- Code:
  - runs `validate.py` checks;
  - downgrades a status the confirmed runs do not back (the same rule as the validator);
  - writes `drafts/<slug>/threat.v<N>.md` and makes it current, so history is kept;
  - prints the diff;
  - never touches `threats/`.
- `threatlab.py pf-loop <slug|--propose N>` runs 3 → 4 → (approval) → 5 → 6 → 7 for `--rounds`.
  It stops early when the reviser makes no change or `--budget` runs out. Approval of each frozen
  plan stays interactive unless `--budget` is given, as in today's `loop`.
- `pipeline --engine promptfoo-redteam` wires the proposer in front. `promote` is unchanged.

### 8. Docs

- `evaluation-loop/README.md`: new diagram and config (`models`, `roles`, `promptfoo.allowed_*`),
  the paid guard.
- `lab.example.yaml`: a LiteLLM example without a real key.
- `AGENTS.md`: mention own models and the paid guard if needed.

## Reused code
- `lab_checks.py`: `lint_case`, the echo test, `anchors`, `plan_hash`, the thresholds.
- `threatlab.py`: `propose_drafts`, `write_tests_for_draft`, `evaluate_dir`, `validate_loop`,
  `run_promptfoo`, `promptfoo_env`, `ensure_ignored`, `write_private`, `cmd_promote`.
- `pf_provider.py`, `pf_assert.py`, `spe_threat.fill`/`run_input`/`judge`, `lab_browser.Browser`.

Existing commands (`run`, `loop`, `adaptive`, `promptfoo`) keep working.

## Verification
- Unit tests (`cd evaluation-loop && uv run --group dev pytest -q`):
  - backends against a local fake OpenAI-compatible HTTP server: schema path, fallback + retry,
    refusal;
  - config: the key never appears in provenance or generated files; inline key refused when
    `lab.yaml` is not ignored; old `generator:` still works;
  - `lint_message`, the provider gate (blocked, unprovable, counter at `max_runs`);
  - budget estimate, spec builder output, reviser status downgrade.
- No-cost checks: `pf-generate` with a scripted attacker (a fake provider) → lint → frozen hash;
  `pf-run` against `platform/dev/fake_agent.py` or the scripted chat (`spe_threat.py selftest --with-chat`).
- Paid, only after the user's OK: on the test-josef workspace with LiteLLM, one TM draft,
  `--budget 10`. Check:
  - `promptfoo view` shows the iterative turns;
  - `raw.jsonl` holds every turn;
  - lint-blocked messages were not sent;
  - the confirmation replay and the revised `threat.v2.md` with its diff.
- Commit per task. Push the branch and open a PR against `main` (after #49), per AGENTS.md.
