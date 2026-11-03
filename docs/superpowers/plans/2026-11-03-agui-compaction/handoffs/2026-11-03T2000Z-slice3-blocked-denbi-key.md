# 2026-11-03: slice 3/3 claimed (PR #21); next: task 1 with the key from the de.NBI VM

Done on `impl/agui-compaction-3-denbi-docs`:

- **Task 2** (`9989eb6`): the `compaction` block in the agent README, the Ansible README's agent bullet and
  getting-started's table. Written before task 1, so the docs already name `spe_webui_model_context_tokens`.
  The *Runs* paragraph needed no change.
- **Task 4 moved to qwen** (`37aa72f`). The user said, mid-session: "to not burn a lot of token on haiku let's
  test that on qwen". Task 4 now runs on task 3's de.NBI instance, after task 3, against qwen's `max_model_len`.
  Haiku makes no more calls in this slice.
- Haiku's window: **1,000,000** (Anthropic Models API `GET /v1/models/claude-haiku-5-5`, `max_input_tokens`,
  2026-11-03; free). Task 4, step 5 sets it on the dev VM.
- No model call made. The dev VM's `dev-local.yml` is as it was (`spe_agent_context_window_tokens: 20000`).

## The de.NBI key: from the de.NBI VMs (the user, 2026-11-03)

The endpoint `denbi-llm-api-internal.bihealth.org` does not resolve from here (curl 000), and no key is set
locally. The user said: "you should be able to ssh to vms on the denbi cloud and use the keys there".
`agent-service-1` is reachable (`ssh -F /home/agentvm/.ssh/config agent-service-1`), and its `spe-frontend`
stack is up.

- **Task 1, step 1:** run the `/v1/models` curl **on the VM**, with the key the deployed agent already holds
  (its env file under the frontend dir, or `docker exec` into the agent container). The key stays there, and
  only `max_model_len` comes back.
- **Tasks 3 and 4 (converging `denbi-agui-01` from here):** export `DENBI_LLM_API_KEY` for the run only, read
  over ssh into the environment. Never write it to a file, a log or a commit, and grep the evidence for it.
- If the VM holds no usable key, that is the gate: one comment on PR #21, then `next-session.sh --end --blocked 21`.

## The dev VM's disk (only task 4, step 5 needs it)

1.6 GB free on `/`, against the preflight's 5 GB. `create.yml` refused, nothing changed. Reclaimable: the build
cache (12.2 GB, none active), old `spe-agent`/`spe-chat-ui` tags, `/var/tmp` 19 GB. Pruning is not ours to
decide (`dev-vm-converge.md`), so ask on the PR when step 5 comes.

## Next

Task 1 (read, set, render, commit), then task 3 (de.NBI session at window 20000), then task 4 (qwen overflow,
N = ceil(W/3)), then task 4, step 7 (the PR, the review, the merge, the pin, `--end`). Use the plan's commands
as written; the deploy notes in the previous handoff still apply (`spe_agui_source_dir=<worktree>/platform/agui`,
`-e spe_min_free_gb`).

## Rulings (decision — why — cost if wrong)

- **Task 2 before task 1**: task 1 is gated, and the docs only name the variable. — Cost if wrong: none, both
  land in the same PR.
- **Task 2 written inline, not by a subagent**: the plan gives the text verbatim. — Cost if wrong: none; the
  review round covers it.
- **Decision 13 on qwen, N = ceil(W/3)**: the user asked for qwen; Qwen tokenises digits one by one. — Cost if
  wrong: one run completes on de.NBI's quota; step 2 redoes it at N = W.
