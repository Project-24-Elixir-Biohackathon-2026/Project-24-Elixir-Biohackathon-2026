# 2026-11-03: slice 3/3 blocked: the de.NBI key on the VMs is blocked at the gateway

Nothing changed in the repo since `49a4c70` except this handoff. No model call was made.

## What was tried (task 1, step 1)

- `agent-service-1` is `denbi-agui-01` (`spe_existing_host` in its instance file). Its agent container holds
  the key as `OPENAI_API_KEY` (25 characters); `/v1/models` with it, run inside the container: **HTTP 401**.
- `~/agent-stack/webui.env` (Open WebUI) holds the same key (same sha256). Through `curl` on the VM the gateway
  says: `"Authentication Error, Key is blocked. Update via /key/unblock if you're an admin."` (LiteLLM, 401).
- No other key on the reachable VMs: `spe-ga4gh-api` has no route, `spe-ga4gh-api-2` fails host-key
  verification, `denbi-jumphost-01` has nothing for `bihealth.org` beyond system config. Nothing is set locally.

So the de.NBI quota is unusable for tasks 1, 3 and 4 until the user gives a working key (or unblocks this one).
Gate: comment on PR #21, `next-session.sh --end --blocked 21`.

## Next, once the gate clears

The user's answer comes as a PR #21 comment: either the `max_model_len` value (and how it was read) or a working
key (where to read it from). Then: task 1 (set, render, commit), task 3 (needs `denbi-agui-01` redeployed with
that key: `DENBI_LLM_API_KEY` exported for the run only, never written down), task 4, task 4 step 7. The previous
handoff's notes still hold (`2026-11-03T2000Z-slice3-blocked-denbi-key.md`: deploy flags, dev VM disk, rulings).
If only the value comes and no working key, task 1 can land, but tasks 3 and 4 still need the quota: ask again.
