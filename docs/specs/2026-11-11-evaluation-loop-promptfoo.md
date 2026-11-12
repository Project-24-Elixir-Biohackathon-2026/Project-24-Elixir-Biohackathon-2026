# evaluation-loop around promptfoo, with own models

Plan: `docs/plans/2026-11-11-evaluation-loop-promptfoo.md`. Progress and rulings:
`docs/plans/2026-11-11-evaluation-loop-promptfoo-progress.md`. Branch `evaluation-loop-promptfoo`.

## 1. Goal

The tool red-teams the agent of an SPE instance around promptfoo's own attack loop:

1. A proposer drafts a threat model (TM).
2. A translator turns it into promptfoo red-team input.
3. promptfoo works the chat with its plugins and strategies, including iterative and multi-turn
   attacks.
4. threatlab judges the output with its deterministic checks and confirms every hit by replaying
   it unchanged.
5. A reviser updates the TM **draft**, and the loop repeats.

Every model role can run on Claude Code (`claude -p`, no API bill) or on an OpenAI-compatible
endpoint (the team's LiteLLM proxy), chosen per role in `lab.yaml`, which holds the API key.

## 2. Invariants (unchanged from the existing tool)

- A model writes text and steers the search. Verdicts come from code: indicators in `checks.py` and
  fixed thresholds in `lab_checks.py`. promptfoo's grader steers its iterative loop but never sets
  a verdict.
- Nothing reaches the agent without an approved plan hash. The agent-run budget (`max_runs`) is
  enforced in the provider, per call.
- Only `threats/` reaches git, and only as new files written by `promote`. The revise loop changes
  `drafts/<slug>/` only.
- Paid model calls need the human's OK: a role on a backend marked `paid` runs only with
  `--allow-paid-models`.

## 3. Gates

| Gate | Where | What code checks |
|---|---|---|
| A | after the proposer | `validate.py`'s checks, near-duplicate detection |
| B | after the translator | every intent linted as a case (safety, hosts, `{nonce}` payload, echo test, `example_hit`); budget estimate ≤ `max_runs` |
| C | after `promptfoo redteam generate` | every generated test linted, failures dropped; file + spec frozen into `plan.json` with a SHA-256 the user approves |
| D | in `pf_provider.py`, per outgoing message | message lint; payload present (else `unprovable`); run counter; plan hash |
| E | evaluation | indicators on every turn; hits replayed unchanged N times under a new approved plan; `reproduced` only at max(2, threshold) confirmed hits |
| F | after the reviser | `validate.py`'s checks; a status not backed by gate E is downgraded; versioned draft and a diff; never writes `threats/` |

## 4. Models and keys

```yaml
models:
  default: {backend: claude-code, model: haiku}
  litellm:
    backend: openai-compatible
    base_url: https://litellm.example.org/v1
    api_key: sk-...          # or api_key_env: NAME, or api_key_file: path
    model: qwen3.8-27b
    paid: true
roles: {judge: litellm, attacker: litellm, grader: litellm}   # missing roles use default
```

- An old `generator:` block still works and becomes `models.default`.
- An inline key is refused unless `lab.yaml` is git-ignored.
- The key goes only into the request header or a subprocess environment. It never appears in
  provenance, logs, `plan.json` or generated configs.

## 5. As built (2026-11-11)

- **Run modes.** `transport: http` (chat-ui's run route over HTTP, no browser; cloud or `agui_tunnel`) or
  `transport: browser` (the same route on the logged-in browser's cookies; local). Both continue a session
  as the chat page does: the server's branch plus the new message (`agui_provider.chat_body`). Any backend
  works wherever it is reachable, so the tool runs locally with Claude Code as well as in the cloud with
  LiteLLM.
- **promptfoo's attacker and grader are `pf_model.py`.** It calls the role's backend and counts calls
  against `promptfoo.max_model_calls`. It refuses paid backends unless `--allow-paid-models` is given.
  promptfoo never sees an API key.
- **Commands:** `pf-generate`, `pf-run`, `pf-evaluate`, `pf-confirm`, `pf-validate`, `pf-revise`, `pf-loop`,
  `pf-view`, `doctor`. The user guide is `evaluation-loop/README.md`.
