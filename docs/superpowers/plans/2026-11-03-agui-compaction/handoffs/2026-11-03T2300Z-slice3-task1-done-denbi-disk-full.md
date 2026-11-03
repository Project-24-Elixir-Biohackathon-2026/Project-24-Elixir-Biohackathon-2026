# 2026-11-03: slice 3/3 task 1 done; task 3 blocked, `agent-service-1`'s disk is full

Done on `impl/agui-compaction-3-denbi-docs` (pushed):

- **Task 1** (`56178dc`): `spe_webui_model_context_tokens: 262144` beside `spe_webui_model_id`, and
  `spe_agent_context_window_tokens` derived from it while `spe_agent_model == spe_webui_model_id`. Step 3's
  renderings: `262144`, then `null` (Haiku), then `20000` (Haiku with the override); the syntax check of
  `create.yml` and `verify.yml` passes.
- **Docs and plan** (`32da961`): the de.NBI window is the gateway's (LiteLLM) `max_input_tokens` from
  `/v1/model/info`, not vLLM's `max_model_len`. The Ansible README, getting-started's row and the plan's task 1
  (its command, the comment, the commit message) and task 2 texts say so.
- **Task 4, step 0:** plan PR #16 has no objection to clarification 5. Go ahead when task 3 is done.
- PR #21: the gate-cleared reply and the label removal were already done in the previous session.

## The gate: `agent-service-1` has 710 MB free

Task 3's redeploy (`create.yml -e @instances/denbi-agui-01.yml -e spe_min_free_gb=5 -e spe_agui_source_dir=…`,
key `52bb9f98` from Coder) was refused by the preflight: "only 0 GB free on the filesystem of
/home/ubuntu/spe-frontend, … /var/lib/docker, need 5". Nothing changed; the running stacks are untouched.
`/` is 48 GB, 99 % used (710 MB free). The VM is shared with `agent-stack` and `workflow-stack`, so pruning
there waits on the user. Reclaimable:

- Docker build cache: **12.95 GB**, none active (`docker buildx du`). It includes the previous `spe-agent` and
  `spe-chat-ui` builds, and perhaps other stacks' builds.
- Our unused image tags: `spe-agent:89d75ef7f596`, `:ac7fe88374e0`, `:330300004551` (315 MB each, layers
  shared), `spe-chat-ui:4444517685b9` (the same image ID as the running `:18a71fcf1c1e`).
- Others' images that no container uses (not ours to judge): `spe-goose` ×2, `ghcr.io/open-webui/open-terminal`,
  `hello-world`, and the base images.

Asked on PR #21: may we run `docker builder prune -f` and remove our three unused `spe-agent` tags there, or
should we use another VM? One redeploy needs about 5 GB (two image builds).

## Next, once the gate clears

1. The instance file `MAIN/platform/ansible/instances/denbi-agui-01.yml` already has task 3's
   `spe_agent_context_window_tokens: 20000` (with a comment saying to remove it afterwards).
2. Free space as the user allows, then redeploy. Read the key into the environment for that run only:
   `export DENBI_LLM_API_KEY="$(~/.local/bin/coder ssh theo/theo-workspace 'docker exec spe-frontend-open-webui-1
   printenv OPENAI_API_KEY' | tr -d '\r\n')"`. Check its sha prefix is `52bb9f98`, then run `create.yml` from
   `MAIN/platform/ansible` as above. It takes a few minutes, so run it in the background.
3. Task 3, step 2: tunnel the chat UI to a free local port (the dev VM's own chat UI holds 3000):
   `ssh -F ~/.ssh/config agent-service-1 -N -L 13000:127.0.0.1:3000 -L 18100:127.0.0.1:8100`, then
   `sessions.py --url http://127.0.0.1:13000 --compose-file /nonexistent --scenario compaction-live --shots
   <evidence>/denbi`. `compaction_live` never reads the compose file. `archive.yml` and `verify.yml` follow (step 3).
4. Task 4 (N = ceil(262144/3) = 87382, C = 699056), then task 4, step 7.

## Rulings (decision — why — cost if wrong)

- **The plan's de.NBI texts rewritten to the gateway's `max_input_tokens`**: that is the figure that was read.
  — Cost if wrong: if vLLM's own limit is lower, task 4's overflow error shows it; correct `all.yml` and the docs then.
