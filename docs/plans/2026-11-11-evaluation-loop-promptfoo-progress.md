# evaluation-loop around promptfoo: progress and rulings

Plan: `docs/plans/2026-11-11-evaluation-loop-promptfoo.md`. Spec:
`docs/specs/2026-11-11-evaluation-loop-promptfoo.md`. Branch `evaluation-loop-promptfoo`
(from `evaluation-loop`, PR #49).

## State

| Task | State | Evidence |
|---|---|---|
| 0 Prerequisites, research | done | PR #49 base + PR #47 merged (`61064f8`); promptfoo 0.125.1 and chat-ui read, plan v2 |
| 1 Backends + key | not started | |
| 2 Provider gate | not started | |
| 3 Translator | not started | |
| 4 Generate + freeze | not started | |
| 5 promptfoo loop | not started | |
| 6 Evaluate + confirm | not started | |
| 7 Reviser + pf-loop | not started | |
| 8 Docs | not started | |

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
