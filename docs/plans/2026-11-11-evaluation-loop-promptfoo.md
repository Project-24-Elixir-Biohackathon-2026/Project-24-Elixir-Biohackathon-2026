# Plan: evaluation-loop around promptfoo, with own models (LiteLLM)

Spec: `docs/specs/2026-11-11-evaluation-loop-promptfoo.md` (updated in T10).
Progress and rulings: `docs/plans/2026-11-11-evaluation-loop-promptfoo-progress.md`.

## 1. Context

Today `evaluation-loop/threatlab.py`:
- runs its own loops (`run`, `loop`, `adaptive`);
- uses promptfoo only as a second runner;
- reaches the chat through a logged-in browser (CDP);
- calls every model role through Claude Code (`claude -p`).

The user wants the tool built around promptfoo:

1. The **proposer** drafts a threat model (TM).
2. A **translator** turns it into promptfoo red-team input.
3. **promptfoo** works the chat with its own attack loop.
4. **threatlab** judges the outcome with deterministic checks.
5. The TM **draft** is revised, and the loop repeats.

Lint and the deterministic checks sit at every handoff. Models are configurable per role, including the
team's LiteLLM with an API key from the config. The tool will be deployed in the team's cloud.

## 2. Decisions (with source)

| # | Decision | Source |
|---|---|---|
| D1 | The revise loop changes `drafts/<slug>/` only. `threats/` gains new files through `promote`, never edits | user, 2026-11-11 |
| D2 | Own models = one OpenAI-compatible backend, aimed at LiteLLM (de.NBI gateway `https://denbi-llm-api-internal.bihealth.org/v1`, `platform/ansible/inventory/group_vars/all.yml:189`) | user: "Máme vlastní litellm" |
| D3 | The tool runs in the team's cloud. The new pipeline needs **no browser**: it reaches the chat over HTTP, and LiteLLM is reachable from there. The browser transports (`--via api|ui`) stay for local use of the old commands | user: "nasazený v našem cloudu" |
| D4 | The chat transport is **PR #47's** `agui_provider.py` with `via: chat` (run route without a key, the session read back through `GET /api/sessions/<id>`). Multi-turn uses this path only; `--via ui` stays single-turn | user: "Jen api … PR#47, použij to" |
| D5 | promptfoo's one residual ping when telemetry is disabled (`feature_used: telemetry disabled` to `r.promptfoo.app`, random id, no test content) is accepted and documented | user |
| D6 | A model never sets a verdict. promptfoo's grader only steers and stops its search; threatlab's indicators and thresholds decide | existing rule |
| D7 | Paid calls need the human's OK: any role on a backend marked `paid` (default for openai-compatible), and every agent run, behind an approved hash | AGENTS.md |

## 3. What promptfoo 0.125.1 does offline (read in `platform/promptfoo-evals/node_modules/promptfoo/dist/src`, spot-checked)

- **Environment.** Set `PROMPTFOO_DISABLE_REMOTE_GENERATION=true`, plus `PROMPTFOO_DISABLE_TELEMETRY`, `PROMPTFOO_DISABLE_UPDATE` and
  `PROMPTFOO_DISABLE_SHARING`, and an isolated `PROMPTFOO_CONFIG_DIR`. With remote generation disabled there is no email gate and
  no login check. An `OPENAI_API_KEY` alone does *not* disable remote generation (`remoteGeneration-*.js`).
- **Attacker and grader.** `redteam.provider` takes any provider spec, e.g.
  `{id: openai:chat:<model>, config: {apiBaseUrl, apiKeyEnvar}}`. The grader falls back to the same provider. Our provider is
  loaded unchanged, so `jsonOnly` is not applied for us: set `response_format: {type: json_object}` in its config.
- **Plugins that work offline.**
  - Usable: `intent` (verbatim: one test per intent, no LLM call; a list of lists becomes a scripted multi-turn `sequence`),
    `policy`, `excessive-agency`, `shell-injection`, `prompt-extraction`, `pii:*`, `debug-access`, `rbac`, `sql-injection`,
    `tool-discovery`, and `file://` custom plugins.
  - Remote-only (they yield 0 tests): `hijacking`, `ssrf`, `indirect-prompt-injection`, `system-prompt-override`, `bola`, `bfla`,
    most `harmful:*`.
- **Strategies that work offline.**
  - Static, at generate time: `base64`, `hex`, `rot13`, `leetspeak`, `homoglyph`, `jailbreak-templates`, `math-prompt`, `language`.
  - Dynamic, at eval time: `crescendo`, `jailbreak:tree`, `custom` (our own `strategyText`).
  - **Remote-only, they throw:** `jailbreak`/`jailbreak:meta`, `jailbreak:composite` (both in the *default* strategy list), `goat`,
    `hydra`, `best-of-n`, `mischievous-user`, `citation`, `likert`, `gcg`. So strategies are always listed explicitly.
- **Generate before eval.** `redteam generate -o redteam.yaml` writes every test before the target is called. Each test
  carries `metadata.pluginId` and `strategyId`. A dynamic test carries `provider: promptfoo:redteam:<strategy>`.
- **Multi-turn and the target.**
  - With `stateful: true` (in the strategy's config), crescendo sends only the newest message and passes back the `sessionId`
    our provider returns (`context.vars.sessionId`).
  - Stateful turns off crescendo's backtracking, so it makes at most `maxTurns` target calls.
  - `jailbreak:tree` sends independent single prompts.
  - On `{error}`, crescendo uses up the round and continues; none of the strategies retries.
- **No global cap on target calls exists.** The provider has to enforce it.
- **Our `type: python` assert does not steer the loop.** The plugin grader picks the turn and early stop; our assert sees only the
  final output.
- **Results.** Turns are recorded in `metadata.redteamHistory` or `metadata.messages`. Replay is not taken from there: our
  provider logs every turn itself.
- **Python provider.**
  - The worker is persistent: module state survives between calls.
  - `context` has `vars`, `test.metadata` (pluginId, strategyId), `repeatIndex`, `testIdx` and `evaluationId`.
  - There is no turn index.
  - Successful calls are cached by prompt and vars, so `--no-cache` is mandatory against the live agent.

## 4. Flow and gates

```
Proposer ──► drafts/<slug>/threat.md
  [A] validate.py checks + near-duplicate (existing propose_drafts)
Translator ──► spec.json: purpose, threat indicators, intents ({nonce} seeds), sequences,
               policies, plugins ⊆ allowlist, strategies ⊆ allowlist (+ caps), grader guidance
  [B] every seed/sequence linted as a case (lint_case: safety, hosts, echo test, example_hit);
      allowlists enforced; caps clamped; budget estimate ≤ max_runs
pf_spec.build ──► promptfooconfig.yaml ──► promptfoo redteam generate ──► redteam.yaml
  [C] per generated test: lint_message, provability (§5), reversible-encoding check;
      failures dropped and listed; plan.json frozen (spec + redteam.yaml sha256 + caps + models),
      hash printed with max agent runs and estimated model calls
promptfoo redteam eval --no-cache -j 1 ──► pf_provider.py ──► agui_provider (via chat) ──► chat-ui ──► agent
  [D] in pf_provider, per turn: approval hash, run counter (file lock), lint_message, nonce fill,
      provability mark, turn logged to raw.jsonl (pluginId, strategyId, testIdx, repeatIndex, turn, sessionId)
threatlab evaluate ──► per conversation: indicators over all its turns (checks.py)
  [E] candidates = provable conversations with a hit → confirm plan (exact user turns, unchanged),
      approved hash → replayed N× in new sessions with fresh nonces → L.case_verdict thresholds
      → Validator (may say less, never more)
Reviser ──► drafts/<slug>/threat.v<N>.md (+ diff) ──► next round, or promote
  [F] validate.py checks; a status/Evidence not backed by [E] is downgraded; never writes threats/
```

## 5. Nonce, provability, encodings

**Provable.** A case's indicators are *nonce-dependent* if any parameter contains `{nonce}`, e.g. `answer_contains: SECRET-{nonce}`.
Others are nonce-free: `canary_leak`, `key_leak`, `tls_bypass`, fixed `tool_args_match` and `tool_called`.
- A test or turn with nonce-dependent indicators is **provable** only if its message still carries the anchors. Otherwise it is
  run (it may still help the attack along), marked `unprovable`, and never counts toward a verdict.
- The translator must give each threat at least one nonce-free indicator wherever the TM allows it, so plugin-generated tests
  (which carry no payload) can be decided.

**Nonce per conversation.**
- `nonce = nonce_for(plan, f"{testIdx}#{repeatIndex}", 1)`, reusing `L.nonce_for`, so every turn of one conversation shares it.
- The provider fills `{nonce}` in the outgoing message.
- The confirm replay uses a fresh nonce per trial.

**Reversible encodings** (`base64`, `hex`, `rot13`), in a new `encodings.py`.
- Gate C decodes the message by `strategyId` and checks the anchors are there.
- Gate D decodes, fills the nonce and re-encodes.
- Other static strategies count as provable only if the literal `{nonce}` anchors survive. Otherwise gate C drops the test when
  its indicators are nonce-dependent.

## 6. Multi-turn through the chat (extends PR #47)

chat-ui owns the history (spec §13 of `2026-10-15-agui-frontend-design`):
- it keeps from the client only the new user message;
- it anchors on message ids its journal holds;
- it records everything else as ignored.

So a continued conversation must look like the real client's:

1. Same `threadId`.
2. `messages` = the session's current branch from `GET /api/sessions/<id>` (with the server's ids), then the new user message.

**Change to `platform/promptfoo-evals/agui_provider.py`.** With `via: chat` and `context.vars.sessionId` (or `config.session_id`)
set, the provider:
- reuses that id;
- fetches the branch;
- sends it plus the new message;
- returns `sessionId` at the top level.

Without a session id the behaviour stays exactly as in PR #47. `vars.history` stays the forged-history feature, so the two never
mix: a test with both is an error.

## 7. Budget

| Strategy | Per-test cap we set | Max agent runs per test |
|---|---|---|
| basic, static encodings, `intent` | n/a | 1 |
| `sequence` (multi-turn intent) | its length ≤ 6 | ≤ 6 |
| `crescendo` | `stateful: true`, `maxTurns ≤ 6` | ≤ 6 |
| `custom` | `stateful: true`, `maxTurns ≤ 6` (backtracking checked in T6) | ≤ 6 |
| `jailbreak:tree` | `maxDepth 3`, `branchingFactor 2`, `maxWidth 2`, `maxAttempts ≤ 8` | ≤ 9 (attempts + final) |

- Estimate = Σ over tests of cap × `--repeat`. It must be ≤ `max_runs` (gate C).
- The provider counter is authoritative (gate D). Past the cap it returns `{error: "budget reached"}` without calling the chat.
- Model calls: about 1 attacker + 1 grader per turn for dynamic strategies, plus generate-time calls per plugin. Gate C prints
  the estimate; it is paid on LiteLLM.

## 8. Models and keys (`lab.yaml`)

```yaml
models:
  default: {backend: claude-code, model: haiku}          # local use; no API bill
  denbi:
    backend: openai-compatible
    base_url: https://denbi-llm-api-internal.bihealth.org/v1
    api_key_env: DENBI_LLM_API_KEY      # or api_key_file: /path (0600), or api_key: sk-... (only if lab.yaml is git-ignored)
    model: qwen3.8-27b
    paid: true                          # default for openai-compatible
roles: {proposer: denbi, translator: denbi, tester: denbi, repairer: denbi, rewriter: denbi,
        judge: denbi, validator: denbi, refiner: denbi, reviser: denbi, attacker: denbi, grader: denbi}
```

- An old `generator:` block still works and becomes `models.default`.
- An inline `api_key` is refused unless `lab.yaml` is git-ignored, with a warning unless the file is 0600.
- The key goes only into an HTTP header, or into a subprocess env (`THREATLAB_KEY_<MODEL>`, named in `apiKeyEnvar`). It never
  appears in provenance, logs, `plan.json` or generated configs. A test greps all written files for it.
- The system message is always the first message (Qwen and Mistral reject others).
- `response_format: json_schema` is tried first; on a 400 the backend falls back to `json_object` plus local `jsonschema`
  validation, with one retry that carries the errors. The backend remembers which mode works.
- `--allow-paid-models` is required whenever a paid role would be called. Every command first prints a
  role → model → paid table.

## 9. Tasks

Each task is one or more commits, with tests, in this worktree. The branch is rebased onto `main` once #49 and #47 are merged.
T0 blocks the rest.

**T0. Prerequisites.**
- PR #49 (evaluation-loop) and PR #47 (`via: chat`) merged; this branch rebased on `main`.
- Separately and urgently: rotate the de.NBI key in the tracked `platform/ansible/instances/test-1.yml` and untrack that file
  (its own PR).

**T1. Model backends, config, paid guard.**
- Files: `lab_llm.py` (`ClaudeCodeBackend` = today's `_call`; `OpenAICompatBackend` on stdlib `urllib`; `Generator` resolves a
  backend per role and keeps every role method), `threatlab.py` (`load_config`, a `gen_kwargs(cfg)` helper at the 8 call sites,
  global `--allow-paid-models`, role table), `pyproject.toml` (`jsonschema`).
- Tests: a fake OpenAI server (thread + `http.server`) covering the schema path, the fallback + retry, a refusal, a 401, and the
  key absent from provenance/files; the old config shape; refusal of a paid role without the flag; `FakeGen` injection unchanged.

**T2. Chat session continuation.**
- Files: `platform/promptfoo-evals/agui_provider.py` (§6).
- Tests: extend PR #47's stub chat server with a session store. Cover turn 2 sending branch + new message on the same thread,
  `sessionId` returned, the error when `history` is combined with a session, and PR #47 behaviour unchanged without a session.

**T3. Message-level checks.**
- Files: `lab_checks.py`:
  - `lint_message(text, hosts)` factored out of `lint_case`'s safety block (`lint_case` calls it, so its behaviour is unchanged);
  - `nonce_dependent(indicators)`;
  - `provable(message, anchors, indicators)`.
- Files: `encodings.py` (`decode`/`encode` for base64, hex, rot13).
- Tests: existing lint tests stay green; round-trip of the encodings; provability cases.

**T4. Provider gate D.**
- Files: `pf_provider.py`, rewritten as a wrapper around `agui_provider.call_api`. Per call it:
  - checks the approval hash;
  - takes a counter slot (`fcntl` lock on `plan_dir/counter`);
  - reads the strategy and test from `context.test.metadata`;
  - derives the nonce (§5);
  - decodes, fills and re-encodes;
  - runs `lint_message`, refusing without sending on a failure;
  - calls the chat with the session id;
  - logs the turn to `raw.jsonl` (0600);
  - returns `output`, `sessionId` and metadata.
- A transport switch keeps today's browser path for the old `threatlab promptfoo` command (single-turn only, refused for
  dynamic strategies).
- Tests: blocked message not sent, counter stop, nonce shared within a conversation, re-encoding, logging fields, old-command
  compatibility (`test_promptfoo_provider_and_assertion`).

**T5. Translator and spec builder (gate B).**
- Files: `lab_llm.py` (`TRANSLATOR` prompt and schema), new `pf_spec.py` (spec → `promptfooconfig.yaml`: `purpose`, plugins,
  strategies with caps, `redteam.provider`/grader from roles, `graderGuidance` from the TM, target `file://pf_provider.py`,
  `defaultTest` assert `pf_assert.not_reproduced`).
- Allowlists are the offline sets in §3, as constants in code. `lab.yaml` may narrow them, never widen them.
- Tests: schema rejection, a non-allowlisted plugin or strategy refused, caps clamped, intents linted and repaired, budget
  estimate, the config snapshot.

**T6. `pf-generate` (gate C, freeze).**
- Files: `threatlab.py`. Runs `promptfoo redteam generate` with the offline env, then for each test in `redteam.yaml`: lint,
  provability, the encoding check; drops and reports failures; freezes `plan.json`; prints the hash and both estimates.
- Also: read `custom-*.js` for `custom`'s turn and backtrack options and record them in the progress file.
- Tests: a fixture `redteam.yaml` (no promptfoo run), drop rules, a hash that changes on any edit.

**T7. `pf-run`.**
- Files: `threatlab.py`. Generalises `run_promptfoo` and `promptfoo_env`: `promptfoo redteam eval -c <frozen> --no-cache -j 1`,
  the model key env for the subprocess only, `THREATLAB_APPROVE`.
- Tests: refusal without the hash or over `max_runs`; the subprocess env holds the key and the config files do not.

**T8. Evaluate and confirm (gate E).**
- Files: `threatlab.py`:
  - `evaluate_conversations(rdir)`: group `raw.jsonl` by `(testIdx, repeatIndex)` and judge with `spe_threat.judge` over the
    concatenated turns;
  - `confirm_plan(...)`: exact user turns, N trials;
  - `confirm(...)`: factored out of `run_adaptive` (`threatlab.py:759-790`) and reused by `adaptive`, replaying multi-turn
    turn by turn in one new session through `agui_provider`;
  - verdict by `L.case_verdict`; output that `validate_loop` reads unchanged.
- Tests: unprovable never reproduced, multi-turn grouping, `adaptive` tests green after the refactor.

**T9. Reviser and `pf-loop` (gate F).**
- Files: `lab_llm.py` (`REVISER` prompt and schema), `threatlab.py`:
  - `revise_draft` runs the `check_draft_markdown`/`validate.py` checks, downgrades the status, writes the versioned draft and
    the diff;
  - `pf-loop <slug> | --propose N` runs T5 → T6 → approval → T7 → T8 → Validator → reviser for `--rounds`, stopping on no
    change or an exhausted `--budget`;
  - `pipeline --engine promptfoo-redteam`.
- Tests: an end-to-end loop with `FakeGen`, a fake promptfoo (writes `redteam.yaml` and calls `pf_provider` like the real one)
  and a stub chat; status downgrade; `threats/` untouched.

**T10. Docs.**
- `evaluation-loop/README.md`: new diagram, config, the offline/telemetry note (D5), the paid guard, running in the cloud.
- `lab.example.yaml`, the spec, `platform/promptfoo-evals/README.md` (sessions), AGENTS.md if commands change.

**T11. Cloud readiness.**
- `THREATLAB_CONFIG` env for the config path.
- Every secret from env or file.
- No CDP needed for the `pf-*` commands.
- A `doctor` command: reachability of the chat URL and the LiteLLM `/models`, promptfoo installed, an offline env check.
- The deployment itself (where it runs, how it reaches each instance's chat) is a follow-up, not part of this plan.

## 10. Verification

- **Free, after each task:**
  - `(cd evaluation-loop && uv run --group dev pytest -q)`
  - `(cd platform/promptfoo-evals && uv run --group dev pytest -q)`
  - `uv run --with pyyaml python validate.py`
  - T9's end-to-end test with fakes.
- **Paid, each only after the user's OK, in this order and with these costs:**
  - **V1:** every role's model on LiteLLM returns schema-valid JSON (about 10 calls).
  - **V2:** `pf-generate` on one draft: 2 intents, 1 sequence, 1 policy, `base64` + `crescendo` (about 10–20 attacker calls,
    0 agent runs).
  - **V3:** `pf-run` of V2's plan on the test workspace, capped at `max_runs 10`. Check: the chat-ui session shows the turns of a
    crescendo conversation in one session; `raw.jsonl` holds every turn; a lint-blocked message never reached the chat.
  - **V4:** confirm + reviser on V3's output: `threat.v2.md` and its diff, `promptfoo view` shows the turns.

## 11. Remaining uncertainty, and how it is closed

| Item | Closed by |
|---|---|
| LiteLLM models follow JSON (`json_schema` vs. `json_object`) | V1; the fallback covers both |
| `custom` strategy's turn and backtrack options | T6, reading the code (free) |
| chat-ui accepts a continued session from a non-browser client | T2 against the stub, V3 live |
| A remote-only strategy aborting `generate` | cannot happen: allowlist (T5) |
| The telemetry ping | accepted (D5), documented |

## 12. Out of scope
- Multi-turn through `--via ui`.
- Editing catalog threats.
- promptfoo cloud features (GOAT, hydra, meta and composite jailbreaks).
- Deploying the tool in the cloud.
