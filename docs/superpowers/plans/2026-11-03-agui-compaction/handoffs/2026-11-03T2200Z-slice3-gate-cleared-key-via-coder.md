# 2026-11-03: slice 3/3 gate cleared: a working de.NBI key through Coder

The gate in `2026-11-03T2100Z-slice3-denbi-key-blocked.md` is cleared; no model call was made.

- **The key:** the one on agent-service-1 is still blocked (401). The portal's key works: the user installed and
  logged in to the Coder CLI (`~/.local/bin/coder`, authenticated as `theo`), and `theo/theo-workspace`'s Open
  WebUI holds it (sha `52bb9f98`; the blocked one is `281aa6c1`). `/v1/models` with it lists `qwen3.8-27b`.
  How, and the rules for handling it: [`denbi-llm-key.md`](../../../../knowledge/denbi-llm-key.md).
- **Task 1, step 1:** `/v1/models` has no `max_model_len` (LiteLLM). `/v1/model/info` gives `qwen3.8-27b`
  `max_input_tokens: 262144`. Use **262144**, read 2026-11-03 from `/v1/model/info`; the plan's command and the
  `all.yml` comment say `/v1/models` and `max_model_len`, so rewrite them to what was read.

## Next

Task 1 steps 2–3 with 262144, then task 3 (`denbi-agui-01` redeployed with `DENBI_LLM_API_KEY` exported from
`coder ssh theo/theo-workspace 'docker exec spe-frontend-open-webui-1 printenv OPENAI_API_KEY'` for the run
only), task 4 (qwen overflow at N = ceil(W/3) = 87382 digits), task 4 step 7. Reply on PR #21 that the gate is
cleared, and drop its `waiting-on-user` label. The 2000Z handoff's deploy notes still hold.

## Rulings (decision — why — cost if wrong)

- **262144 from LiteLLM's `/v1/model/info`, not vLLM's `max_model_len`**: the gateway exposes no
  `max_model_len`, and vLLM is not reachable directly. — If vLLM is set lower, task 4's overflow run fails
  before it reaches 262144 tokens: the error shows vLLM's real limit; set that and rerun task 1 step 3.
