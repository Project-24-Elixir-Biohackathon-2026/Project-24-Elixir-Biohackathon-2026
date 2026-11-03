# 2026-11-03: slice 3/3 done; the AG-UI compaction track is done

What slice 3 ran (`impl/agui-compaction-3-denbi-docs`, PR #21):

- **Task 1** (`56178dc`, `32da961`): `spe_webui_model_context_tokens: 262144`, qwen's window, read from de.NBI's
  LiteLLM gateway (`GET /v1/model/info`, `max_input_tokens`, 2026-11-03; `/v1/models` has no window).
  `spe_agent_context_window_tokens` is derived from it while the agent uses that model. Haiku's window,
  1000000, is from Anthropic's Models API `max_input_tokens` (2026-11-03).
- **Task 2** (`9989eb6`): the agent README, the Ansible README and getting-started describe the `compaction` block.
- **Task 3** (`4532a80`): a de.NBI session on qwen compacts at window 40000 (`evidence/slice-3/denbi/`; 20000 hit
  decision 6's cap, see its README).
- **Task 4** (`30cdc66`, `5ba3fd9`): decision 13 on qwen, `evidence/slice-3/decision-13/`. With compaction off, one
  `seq 1 87382` result was refused by the gateway (400 `litellm.ContextWindowExceededError`, Got=316927 >
  262144); the run `failed`, `compactions: []`. With compaction on and no window, the same session's next message
  compacted: `trigger: overflow`, `estimated_tokens` 237599, `messages_cut` 3, summary `usage` 1843 in / 317
  out, `next_input_tokens` 3312; the run `completed` and answered `87382`. Spec clarification 5 folded,
  decision 13's check rewritten. Archive `/data-share/runs/2026-11-03T151253Z_denbi-agui-01` (controller).
- `denbi-agui-01` is back to normal: `verify.yml` shows `enabled: true`, `context_window_tokens: 262144`, and
  `agent.yaml` has `max_output_bytes: 16384`.

**Participants get compaction only through an upstream port** (spec §9): the portal follows upstream's `main`.
`BACKLOG.md`'s *AG-UI compaction upstream* item is there and still true; the package-port item covers how.

## Rulings (decision — why — cost if wrong)

- **The overflow list was fixed before step 3 ran, not after it failed** (`30cdc66`): step 2's error was the
  LiteLLM gateway's, whose wording the list lacked, so step 3 was certain to fail as the plan foresaw. The fix
  (`context window exceeded`, the real body in both tests) went in first, so step 3 ran once. — Cost if wrong: none
  for the check; the failing run it skipped would only have repeated step 2's error.
- **Step 2's tool result was cut, and the check stands**: `seq 1 87382` printed 779703 bytes (`\r\n` endings),
  above `C` = 8 N, so 699014 bytes were shown. The cap took (`agent.yaml`); the request still overflowed by 21 %.
  — Cost if wrong: none; the check needs an overflow, not a whole result.
- **Step 5's de.NBI redeploy used this branch's inventory** (`-i <worktree>/platform/ansible/inventory/hosts.yml`):
  run from the main checkout, Ansible reads main's `group_vars`, which predate task 1, so the first redeploy
  rendered `context_window_tokens: null`. The two inventories differ only in task 1's lines. After the merge,
  main's own inventory gives the same 262144. — Cost if wrong: none; the value is the merged one.
  Note: `docs/knowledge/agui-worktree-deploy-inventory.md`, and `AGENTS.md`, *Worktrees and deploying*.
- **The dev VM was not redeployed**: 4.5 GB free, under the preflight's 5; pruning there is the user's call (the
  plan). `dev-local.yml` already says 1000000; the redeploy is in `BACKLOG.md`'s *Next*.

## Next

- **`/compact` in the chat**: due now (`BACKLOG.md`, *Next*, the user's request on PR #21), coordinated with the
  conversation record track, whose plan is next on its own line in `AGENTS.md`, *Current work*.
- The dev VM redeploy (`BACKLOG.md`, *Next*), once the user decides on its disk.
