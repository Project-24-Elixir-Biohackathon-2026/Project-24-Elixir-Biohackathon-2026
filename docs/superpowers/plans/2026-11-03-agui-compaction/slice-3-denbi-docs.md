# Slice 3/3: the de.NBI window, the docs, and decision 13's check

Delivers the last of the configuration and the record of how to use it: the de.NBI model's context window set
beside `spe_webui_model_id`, so an instance on that model compacts before vLLM refuses a request; the
`compaction` block described in the agent's README, the Ansible README and `docs/getting-started.md`; and
decision 13's model-backed check on the dev VM, a session that already fails with Haiku's own overflow error and
then recovers. It ends the track.

**Implements:** spec [`2026-11-03-agui-compaction-design.md`](../../specs/2026-11-03-agui-compaction-design.md)
§9 (the de.NBI value, the docs), decision **12**'s remaining part (the window beside `spe_webui_model_id`, the
dev VM's in its instance file) and decision **13** (task 3), with proposed clarification 5 (plan README).

**Review Focus** (plan README): none of its items is this slice's; task 3, step 3 is the one live check of
the overflow list against a provider's real wording.

**Branch:** `impl/agui-compaction-3-denbi-docs`, from `main` after slice 2 merged. Global constraints, shared
interfaces, the ruling and Review Focus: [plan README](README.md). `ANSIBLE` means `platform/ansible`, `AGENT`
`platform/agui/pydantic-ai-agent`, `MAIN` the main checkout
(`/workspace/biohackathon/biohackathon/elixir-biohackathon-2026-test`).

**Before starting, check this file's tasks against the user's comments on slice 2's PR**: a change the user asked
for after the early output (prompt, ratio, rendering) was rewritten into this slice's tasks, as a task before
task 2's docs, by slice 2's PR or a follow-up commit on `main` (README, *PR slices*). If a comment asks for one
that is not here, add the task first, in its own commit.

**Verified facts this slice builds on** (read in the repo, 2026-11-03):

- `ANSIBLE/inventory/group_vars/all.yml`: `spe_llm_base_url: https://denbi-llm-api-internal.bihealth.org/v1`
  (l. 127), `spe_webui_model_id: qwen3.8-27b` (l. 171, under a comment), `spe_agent_model:
  "{{ spe_webui_model_id }}"` (l. 183). Slice 1, task 2 added `spe_agent_context_window_tokens: null` after
  `spe_agent_total_tokens_limit` with its comment, and `roles/agui/tasks/main.yml` renders it as
  `(… | int) if … is not none else none`.
- Ansible is `core 2.20.1`: templates return native types, so `"{{ … else none }}"` yields `None`, not the
  string `"None"` (task 1, step 3 checks it).
- `spe_agent_max_output_bytes: 16384` (all.yml l. 197) caps each tool result in the agent
  (`sandbox.py:244`, `truncate`). `lib/sessions.ts` caps tags, titles and the list, not a message's size.
- Stale texts: the spec's *Inputs for the plan* list is done by slices 1 and 2 (agent README *Runs*, the chat
  sessions spec clarification, the `BACKLOG.md` check, upstream's frontend spec noted in slice 1's PR). This
  slice's own: `ANSIBLE/README.md`, `## Agent frontend (AG-UI)` (l. 236–262, the **agent** bullet and the
  model paragraph); `docs/getting-started.md`, `## 4. Configure an instance`, step 3's table (l. 132,
  the model row); `AGENT/README.md`, after **Providers.** (l. 40–48), and the *Runs* paragraph slice 1
  rewrote.
- The dev VM's instance file `MAIN/platform/ansible/instances/dev-local.yml` (private) holds
  `spe_agent_context_window_tokens: 20000` from slice 2, task 5, step 4.

---

### Task 1: the de.NBI model's window beside `spe_webui_model_id`

**Files:**
- Modify: `ANSIBLE/inventory/group_vars/all.yml` (after `spe_webui_model_id`; slice 1's
  `spe_agent_context_window_tokens` line)

**Interfaces:**
- Consumes: `spe_agent_context_window_tokens` and its rendering (slice 1, task 2).
- Produces: `spe_webui_model_context_tokens` (the de.NBI model's window); `spe_agent_context_window_tokens`
  derived from it while the agent uses that model, `null` for any other model unless an instance sets it.

- [ ] **Step 1: read the window, by hand, no model call.** From the main checkout, with the de.NBI key in the
  environment as for a deployment (`DENBI_LLM_API_KEY`):

```bash
curl -s -H "Authorization: Bearer $DENBI_LLM_API_KEY" https://denbi-llm-api-internal.bihealth.org/v1/models \
  | python3 -c 'import json,sys; print([(m["id"], m.get("max_model_len")) for m in json.load(sys.stdin)["data"]])'
```

  Expected: `qwen3.8-27b` with an integer `max_model_len`. Listing models is not a completion and costs nothing.
  If the endpoint is not reachable from here, or the key is not set, or the entry has no `max_model_len`, this
  is a gate the loop cannot pass by guessing: open the draft PR, ask in one comment for the value (and how it
  was read), and end with `next-session.sh --end --blocked <PR>` (`development-workflow.md`, *Gates*). Do not
  put a model card's figure in: vLLM's `max_model_len` is what the server enforces, and it may be set below the
  model's own.

- [ ] **Step 2: set it.** In `all.yml`, after `spe_webui_model_id: qwen3.8-27b`:

```yaml
# Its context window in tokens: the vLLM server's max_model_len for it (GET /v1/models,
# read on <YYYY-MM-DD>). Change the two together.
spe_webui_model_context_tokens: <N>
```

  and replace slice 1's `spe_agent_context_window_tokens: null` (keep its comment above) with:

```yaml
# Set for the de.NBI model; another model needs its own value in the instance file.
spe_agent_context_window_tokens: "{{ spe_webui_model_context_tokens if spe_agent_model == spe_webui_model_id else none }}"
```

  Ansible 2.20 keeps the template's native value (an integer or `None`); step 3 checks both cases.

- [ ] **Step 3: render it locally.** From `ANSIBLE`:

```bash
T="msg={{ {'context_window_tokens': (spe_agent_context_window_tokens | int) if spe_agent_context_window_tokens is not none else none} | to_nice_yaml }}"
ansible localhost -m debug -e @inventory/group_vars/all.yml -a "$T" </dev/null
ansible localhost -m debug -e @inventory/group_vars/all.yml -e spe_agent_model=claude-haiku-5-5 -a "$T" </dev/null
ansible localhost -m debug -e @inventory/group_vars/all.yml -e spe_agent_model=claude-haiku-5-5 \
  -e spe_agent_context_window_tokens=20000 -a "$T" </dev/null
ansible-playbook --syntax-check playbooks/create.yml playbooks/verify.yml </dev/null
```

  Expected: `context_window_tokens: <N>`, then `context_window_tokens: null`, then `context_window_tokens: 20000`;
  the syntax check passes. (As in slice 1, task 2, step 8: if loading the whole `all.yml` fails on an unrelated
  lookup, pass the variables with `-e`.)

- [ ] **Step 4: commit.**

```bash
git add platform/ansible/inventory/group_vars/all.yml
git commit -s -m "Set the de.NBI model's context window for the agent's compaction" \
  -m "vLLM's max_model_len for qwen3.8-27b, read from /v1/models; the agent uses it only while its model is that one."
```

---

### Task 2: the docs describe the `compaction` block

**Files:**
- Modify: `AGENT/README.md` (after **Providers.**), `ANSIBLE/README.md` (`## Agent frontend (AG-UI)`),
  `docs/getting-started.md` (`## 4. Configure an instance`, step 3's table)

**Interfaces:**
- Consumes: the keys and defaults (README, *Global Constraints*), `spe_webui_model_context_tokens` (task 1), the
  run log's `compactions` (README, *Shared interfaces*), the `verify.yml` task (slice 1, task 2, step 7).

Upstream-clean: none of these texts names the fork, a plan, a slice or the dev VM's instance file by path.

- [ ] **Step 1: the agent's README.** After the **Providers.** paragraph, add:

```markdown
**Compaction.** The `compaction` block (all keys optional):

    compaction:
      enabled: true                 # false: neither trigger acts, as before compaction existed
      context_window_tokens: null   # the model's context window; null: only the reactive trigger
      trigger_ratio: 0.8            # compact at this share of the window, in (0, 1)
      summary_max_tokens: 4096      # the summary request's output cap

Before each model request the agent estimates what it would send (the latest response's usage plus three
characters a token for what came after it); at `trigger_ratio` × `context_window_tokens` or more it compacts
first. Whatever the window, a request the provider rejects as too long (Anthropic's, OpenAI's and vLLM's
wording) is compacted and sent once more. Compacting asks the same model, without tools, for a summary of the
history (`compaction_prompt.md`; tool results cut to their first and last 1000 characters), then sends the
system prompt, the summary framed as a record rather than the participant's words, the latest user request and
what follows. The summary request counts towards the run's usage and limits. At most one compaction per model
request and three per run; past that the run fails with "The conversation is still too long after compacting
it. Start a new chat." Set `context_window_tokens` to the window the server enforces: too high and only the
reactive trigger acts, too low and it compacts early.
```

  Then reread the *Runs* paragraph (slice 1 rewrote its first sentence): it points to the window and the run
  log; it needs no change unless it repeats this paragraph, in which case cut the repeat there.

- [ ] **Step 2: the Ansible README.** In `## Agent frontend (AG-UI)`, in the **agent** bullet after "Run log in
  volume `agent-runs` (player input and canaries: private).", add: "When a conversation nears the model's context
  window the agent compacts it (summarises the older part with the same model; the chat shows a divider, the
  archive a `## Compacted` section, the run log a `compactions` entry): `spe_agent_compaction_enabled` (true),
  `spe_agent_context_window_tokens`, `spe_agent_compaction_trigger_ratio` (0.8) and
  `spe_agent_compaction_summary_max_tokens` (4096), rendered as `agent.yaml`'s `compaction` block, which
  `verify.yml` shows. The window defaults to the de.NBI model's (`spe_webui_model_context_tokens`, the vLLM
  server's `max_model_len`) while `spe_agent_model` is `spe_webui_model_id`, and to null otherwise: set it for
  another model, or only a provider's "too long" error triggers a compaction." Keep the bullet's line width.

- [ ] **Step 3: getting-started.** In step 3's table, after the `spe_agent_model_provider, …` row, add:

```markdown
   | `spe_agent_context_window_tokens` | only for a model other than de.NBI's `qwen3.8-27b` (whose window is already set): the model's context window in tokens, so the agent compacts a long conversation before the provider refuses it, e.g. the vLLM server's `max_model_len` (`GET <base_url>/models`) or the vendor's documented window. Unset, the agent compacts only after a "too long" error. `spe_agent_compaction_enabled: false` turns compaction off |
```

- [ ] **Step 4: check and commit.** `grep -rn "context_window_tokens\|compaction" AGENT/README.md ANSIBLE/README.md
  docs/getting-started.md`: every key name matches `config.py` and `all.yml` exactly. Read the three diffs once
  for any mention of a plan, slice, handoff or `dev-local` (upstream-clean).

```bash
git add platform/agui/pydantic-ai-agent/README.md platform/ansible/README.md docs/getting-started.md
git commit -s -m "Document the agent's compaction configuration"
```

---

### Task 3: decision 13 on the dev VM, clarification 5, the VM put back, the end of the track

Paid: Haiku on the dev VM, approved for this work (README, *Global Constraints*). About five model requests:
two that Anthropic rejects as too long, one small summary request, two ordinary answers. No cloud instance is
created or destroyed.

**Files:**
- Modify (not committed): `MAIN/platform/ansible/instances/dev-local.yml`
- Modify: `docs/superpowers/specs/2026-11-03-agui-compaction-design.md` (clarification 5, decision 13's row)
- Create: `docs/superpowers/plans/2026-11-03-agui-compaction/evidence/slice-3/` (screenshots, run-log lines)
- Create: the handoff in `handoffs/`; Modify: the README's slices table, `AGENTS.md` *Current work*

The ruling behind this task is proposed clarification 5 (plan README): at window 20000 the proactive trigger
compacts long before Haiku's own window, so "the same session with compaction disabled fails with the
provider's error" cannot happen there. The check is therefore run against Haiku's own window: one tool result
large enough to overflow it, which shows the provider's real error with compaction off, then the reactive
recovery with it on. The proactive half of decision 13 (window 20000, divider, `next_input_tokens` below it) is
slice 2's early output, cited, not repeated.

- [ ] **Step 0: the user's answer, and Haiku's window.** Clarification 5 rewrites an approved acceptance check
  and changes this paid run's shape; plan PR #16's body pointed the user at it. Read that PR's comments and the
  user's comments since (`gh pr view 16 --repo thodkatz/elixir-biohackathon-2026-test --comments`): if the user
  objected or asked for another check, stop here and end blocked on this slice's PR (`development-workflow.md`,
  *Gates*). Then read `claude-haiku-5-5`'s context window `W` (tokens) from Anthropic's model documentation and
  note where in the handoff; steps 1, 2 and 5 use it. Size the output to 2–3× `W` so the request is rejected,
  not billed: `N = W` (`seq 1 N` prints ≈ 6.9 characters per line for N in 10^5–10^6, ≈ 7 N characters, and
  digits tokenise at fewer than 3 characters per token, so ≥ 2.3 W tokens), and the output cap
  `C = 8 * N` bytes.

- [ ] **Step 1: compaction off, tool results uncapped.** In `MAIN/…/instances/dev-local.yml`, remove
  `spe_agent_context_window_tokens: 20000` and add `spe_agent_compaction_enabled: false`. Redeploy in place from
  the main checkout with this worktree's agent and the output cap `C` for this check only:

```bash
cd /workspace/biohackathon/biohackathon/elixir-biohackathon-2026-test/platform/ansible
ansible-playbook playbooks/create.yml -e @instances/dev-local.yml -e spe_agent_max_output_bytes=<C> \
  -e spe_agui_source_dir=$PWD/../../.claude/worktrees/impl-agui-compaction-3-denbi-docs </dev/null
```

- [ ] **Step 2: the overflow.** In the chat UI (Playwright or by hand, screenshots into `evidence/slice-3/`), a
  new chat: "Run `seq 1 <N>` and tell me only the last line it printed." Expected: the tool call and its result
  show, then the red error bar with Anthropic's `prompt is too long` (through `Service.sanitize`); the session
  record's last run is `failed`. Then check, in that order:
  - **The request was rejected.** If the run completed instead, the request was billed in full: stop, put the VM
    back (step 5), and end blocked on this slice's PR with the run log's `usage` in the comment; do not retry
    with a larger `N`.
  - **The result is whole.** The run log's tool result (or the session record's) is ≈ 7 `N` characters, not cut:
    a `[truncated: …]` mark means the cap did not take (check `agent.yaml`'s `max_output_bytes`); a shorter
    result without one means the sandbox caps output too: note the limit, and use as many `seq` commands in one
    message as reach 2–3× `W` together, each under it.
  - If the request never reaches Anthropic (a body limit in the chat UI or runtime), note where, and split the
    output across several commands the same way.

  Screenshot `overflow-disabled`.

- [ ] **Step 3: compaction on, the same session recovers.** In `dev-local.yml`, remove
  `spe_agent_compaction_enabled: false` (no window: only the reactive trigger can act, which is what decision 13
  checks). Redeploy as in step 1, with the same `-e spe_agent_max_output_bytes=<C>` (the session's history
  holds the large result either way). Reopen the same session from the sidebar and send "What was the last line?".
  Expected: the divider appears, then an answer naming `<N>`; the run is `completed`. Screenshots `recovered`
  and `recovered-open` (summary expanded). The first request of this run fails at Anthropic exactly as in step
  2; the capability's overflow list must recognise Anthropic's real wording here. If it does not, the run fails
  as before: that is a slice 1 bug (the listed wording is wrong); add the real body to
  `test_compaction_providers.py`'s overflow cases, fix the list, and redo this step.

- [ ] **Step 4: the run log.** From `ANSIBLE`, `ansible-playbook playbooks/archive.yml -e @instances/dev-local.yml
  </dev/null`, then in the output directory it prints, `agent-runs.jsonl`'s record for step 3's run:
  `compactions` has one entry with `trigger: "overflow"`, `messages_cut` ≥ 3, `usage` of the summary request,
  and `next_input_tokens` below Haiku's window. Copy those fields (not the record, not `canaries.json`) into
  `evidence/slice-3/run-log.json`, after checking the summary holds no canary or key (the session ran `seq`
  only). The record for step 2's run has `compactions: []`.

- [ ] **Step 5: put the VM back.** In `dev-local.yml`, set `spe_agent_context_window_tokens` to `W` (step 0), so the dev VM's instance compacts proactively as decision 12 says. Redeploy without the
  `-e spe_agent_max_output_bytes` override, then `ansible-playbook playbooks/verify.yml -e
  @instances/dev-local.yml </dev/null`: the compaction task shows `enabled: true` and that window, and
  `max_output_bytes` is back to 16384 in `agent.yaml`.

- [ ] **Step 6: fold clarification 5.** In the spec, add to *Clarifications* (after 4; template:
  `spec-and-plan-layout.md`):

```markdown
### 5. Decision 13 is checked against the model's own window — folded

**Status:** folded (2026-11-03, plan; slice 3/3).
**Question:** decision 13's check pushes a session past `context_window_tokens: 20000` and expects the same
session to fail with the provider's error when compaction is disabled; on Haiku, whose own window is far larger,
nothing fails at 20000.
**Answer:** the check runs at the model's own window. One tool result past Haiku's window (`seq`, with the
output cap raised for the check) fails the run with Anthropic's `prompt is too long` while compaction is
disabled; with compaction on and no window configured, the same session's next message compacts through the
reactive trigger and completes. The proactive part (window 20000, the divider, the first request after the
compaction below the window) is the early output's session (slice 2).
**Changed:** decision 13's acceptance check.
```

  and rewrite decision 13's acceptance check to: "On the dev VM (Haiku, approved): a session whose tool output
  is past Haiku's own window fails with Anthropic's `prompt is too long` while compaction is disabled; with
  compaction enabled and no window set, its next message compacts (trigger `overflow`), the divider shows, the
  run completes and the run log's input tokens of the first request after the compaction are below the window
  (clarification 5). The proactive path on a small window (`context_window_tokens: 20000`) is the early
  output's session." Also update the plan README's *Proposed spec clarifications* item 5 only if the wording
  changed in the run.

```bash
git add docs/superpowers/specs/2026-11-03-agui-compaction-design.md \
  docs/superpowers/plans/2026-11-03-agui-compaction/evidence/slice-3
git commit -s -m "Check decision 13 on the dev VM; fold spec clarification 5" \
  -m "Anthropic's real overflow error with compaction off, the reactive recovery with it on."
```

- [ ] **Step 7: the end of the track.** Write the handoff (`handoffs/<UTC stamp>-slice3-merged-track-done.md`):
  what ran, the evidence paths, the run-log fields, Haiku's window and where it was read, any ruling, and that
  participants get compaction only through an upstream port (spec §9). Check `BACKLOG.md`'s *AG-UI compaction
  upstream* item (slice 1, task 7, step 4) is there and still true; add it if it is missing.
  Update the slices table (all three done) and **remove the track's line** from `AGENTS.md`, *Current work*.
  Open the PR `de.NBI window, docs, decision 13 (3/3)` with `gh pr create --repo
  thodkatz/elixir-biohackathon-2026-test --base main`; the body says what ran (the syntax check, the three
  renderings, `verify.yml`, the dev VM session, the archive) and links the evidence. Then the local review round,
  the merge and the cleanup (`AGENTS.md`, *Development workflow*), the parent pin in `biohackathon`, and
  `next-session.sh --end` (the track's last unit).
