# evaluation-loop around promptfoo: progress and rulings

Plan: `docs/plans/2026-11-11-evaluation-loop-promptfoo.md`. Spec:
`docs/specs/2026-11-11-evaluation-loop-promptfoo.md`. Branch `evaluation-loop-promptfoo`
(from `evaluation-loop`, PR #49).

## State

| Task | State | Evidence |
|---|---|---|
| 0 Prerequisites, research | done | PR #49 base + PR #47 merged (`61064f8`); promptfoo 0.125.1 and chat-ui read, plan v2 |
| 1 Backends + key + paid guard | done | `lab_models.py`; `tests/test_models.py` (14) against a fake OpenAI server: json_schema, fallback, retry, refusal, 401 without the key, env/file keys, system first, role routing, paid refusal, old `generator:` |
| 2 Chat sessions, both transports | done | `agui_provider.chat_body/get_session`, `lab_browser.turn`, `lab_chat.py`; promptfoo-evals tests 35 pass (5 new), `tests/test_chat.py` |
| 3 Message checks, encodings | done | `lint_message`, `nonce_dependent`, `provable`, `lab_encodings.py`; `tests/test_messages.py` |
| 4 Provider gate D, 4b pf_model | done | `pf_provider.py` (red-team and old plans), `pf_model.py`; `tests/test_pf.py` |
| 5–9 Translator, generate + gate C, run, evaluate + confirm, validate, reviser, pf-loop | done | `pf_lab.py`, `pf-*` commands; `tests/test_pf.py` (14) end to end with fakes. **Real promptfoo 0.125.1 smoke run** (no model, stub chat): offline generate of intent + basic/base64/rot13, gate C kept 3, eval through `pf_provider` over `transport: http`, nonce filled and re-encoded under base64/rot13, verdicts as the stub behaves |
| 10 Docs | done | `evaluation-loop/README.md` (user guide), `lab.example.yaml`, promptfoo-evals README, this file |
| 11 Run modes, doctor | done | `THREATLAB_CONFIG`, `doctor`; tested against fakes and run on the dev laptop (Claude Code found; browser check needs `--group browser`) |
| V1–V4, L1–L2 live checks | not run | need the user's OK: model calls and agent runs |

## Rulings

1. **The revise loop changes drafts only** (user, 2026-11-11). Catalog threats are not
   revised in place; a revision of an existing TM would need a new draft. Cost if wrong:
   a later "revise TM-005" feature needs a PR flow.
2. **Own models through one OpenAI-compatible backend** (user: "Máme vlastní litellm").
   Anthropic's API directly is not a separate backend; LiteLLM can route to it. Cost if wrong:
   one more backend class.
3. **Baseline:** on `evaluation-loop`, `test_threat_ids_exist_in_catalog` fails in this worktree
   because local scenarios TM-018/019 wait for PR #46. Not caused by this work.
4. **Built on PRs #49 and #47; they become part of this branch** (user, 2026-11-11). Cost if
   wrong: one large PR to review instead of three.
5. **Open: the de.NBI key tracked in `platform/ansible/instances/test-1.yml`.** The user asked to go
   on without rotating it; the repository is public, which they were told on 2026-11-11. Their decision
   is pending. Not part of this plan either way.
6. **Multi-turn `sequence` intents are not used** (2026-11-11). promptfoo's `sequence` provider's
   session handling with a Python target is unverified; crescendo and custom cover multi-turn, and a
   confirmed hit is replayed turn by turn by threatlab itself. Cost if wrong: scripted multi-turn seeds
   would need their own path.
7. **One indicator set per seed case, plus one generic set per threat** (2026-11-11). Generic indicators
   must be nonce-free, or policies and plugins are dropped (their tests carry no payload). Cost if wrong:
   threats only showable with a payload get no plugin tests.
8. **Conversations are keyed by chat session, not by promptfoo test** (2026-11-11). jailbreak:tree's
   attempts are separate single-turn conversations; crescendo's turns share one session and one nonce.
   A conversation's hit counts if any of its sent turns carried the payload. Cost if wrong: none found.
9. **`adaptive`'s confirm step was not refactored**; `pf_lab.confirm` is a separate, multi-turn
   replay using the same `case_verdict`. Cost if wrong: two confirm implementations to keep in step.
10. **promptfoo calls the attacker during generate even for intents only** (entity extraction, seen in
    the smoke run as "Error in extraction" with a zero budget). Harmless; documented.
11. **pf-evaluate judges with indicators only**, not the Claude judge, following the user's rule that
    code decides. Cost if wrong: indicator gaps are not caught by a second opinion.
12. **`lab.example.yaml` now defaults `judge: indicators`** for the original commands (the code default
    stays `claude`). Cost if wrong: a user copying the example gets the stricter judge.
