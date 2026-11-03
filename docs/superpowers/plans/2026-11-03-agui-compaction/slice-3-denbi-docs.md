# Slice 3/3: the de.NBI window, the docs, a de.NBI session on qwen, and decision 13's check

Delivers the last of the configuration and the record of how to use it: the de.NBI model's context window set
beside `spe_webui_model_id`, so an instance on that model compacts before vLLM refuses a request; the
`compaction` block described in the agent's README, the Ansible README and `docs/getting-started.md`; and
decision 13's model-backed check on de.NBI's qwen (moved from Haiku at the user's request, task 4), a session
that already fails with vLLM's own overflow error and then recovers. It ends the track.

**Implements:** spec [`2026-11-03-agui-compaction-design.md`](../../specs/2026-11-03-agui-compaction-design.md)
§9 (the de.NBI value, the docs), decision **12**'s remaining part (the window beside `spe_webui_model_id`, the
dev VM's in its instance file) and decision **13** (task 4), with proposed clarification 5 (plan README); and a
de.NBI session on qwen that compacts (task 3, the user's request, the spec's clarification 8).

**Review Focus** (plan README): none of its items is this slice's; task 4, step 3 is the one live check of
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

- [x] **Step 1: read the window, by hand, no model call.** From the main checkout, with the de.NBI key in the
  environment as for a deployment (`DENBI_LLM_API_KEY`):

```bash
curl -s -H "Authorization: Bearer $DENBI_LLM_API_KEY" https://denbi-llm-api-internal.bihealth.org/v1/model/info \
  | python3 -c 'import json,sys; print([(m["model_name"], m["model_info"].get("max_input_tokens")) for m in json.load(sys.stdin)["data"]])'
```

  Expected: `qwen3.8-27b` with an integer `max_input_tokens`. The gateway is LiteLLM: its `/v1/models` has no
  `max_model_len`, and vLLM is not reachable directly (read 2026-11-03: 262144). Model info is not a completion
  and costs nothing.
  If the endpoint is not reachable from here, or the key is not set, or the entry has no `max_input_tokens`, this
  is a gate the loop cannot pass by guessing: open the draft PR, ask in one comment for the value (and how it
  was read), and end with `next-session.sh --end --blocked <PR>` (`development-workflow.md`, *Gates*). Do not
  put a model card's figure in: vLLM's `max_model_len` is what the server enforces, and it may be set below the
  model's own.

- [x] **Step 2: set it.** In `all.yml`, after `spe_webui_model_id: qwen3.8-27b`:

```yaml
# Its context window in tokens: max_input_tokens from the de.NBI gateway's (LiteLLM)
# GET /v1/model/info, read on 2026-11-03. Change the two together.
spe_webui_model_context_tokens: 262144
```

  and replace slice 1's `spe_agent_context_window_tokens: null` (keep its comment above) with:

```yaml
# Set for the de.NBI model; another model needs its own value in the instance file.
spe_agent_context_window_tokens: "{{ spe_webui_model_context_tokens if spe_agent_model == spe_webui_model_id else none }}"
```

  Ansible 2.20 keeps the template's native value (an integer or `None`); step 3 checks both cases.

- [x] **Step 3: render it locally.** From `ANSIBLE`:

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

- [x] **Step 4: commit.**

```bash
git add platform/ansible/inventory/group_vars/all.yml
git commit -s -m "Set the de.NBI model's context window for the agent's compaction" \
  -m "qwen3.8-27b's max_input_tokens from the de.NBI gateway's /v1/model/info (LiteLLM exposes no max_model_len); the agent uses it only while its model is that one."
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

- [x] **Step 1: the agent's README.** After the **Providers.** paragraph, add:

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

- [x] **Step 2: the Ansible README.** In `## Agent frontend (AG-UI)`, in the **agent** bullet after "Run log in
  volume `agent-runs` (player input and canaries: private).", add: "When a conversation nears the model's context
  window the agent compacts it (summarises the older part with the same model; the chat shows a divider, the
  archive a `## Compacted` section, the run log a `compactions` entry): `spe_agent_compaction_enabled` (true),
  `spe_agent_context_window_tokens`, `spe_agent_compaction_trigger_ratio` (0.8) and
  `spe_agent_compaction_summary_max_tokens` (4096), rendered as `agent.yaml`'s `compaction` block, which
  `verify.yml` shows. The window defaults to the de.NBI model's (`spe_webui_model_context_tokens`, the vLLM
  gateway's `max_input_tokens`) while `spe_agent_model` is `spe_webui_model_id`, and to null otherwise: set it for
  another model, or only a provider's "too long" error triggers a compaction." Keep the bullet's line width.

- [x] **Step 3: getting-started.** In step 3's table, after the `spe_agent_model_provider, …` row, add:

```markdown
   | `spe_agent_context_window_tokens` | only for a model other than de.NBI's `qwen3.8-27b` (whose window is already set): the model's context window in tokens, so the agent compacts a long conversation before the provider refuses it, e.g. a vLLM server's `max_model_len` (`GET <base_url>/models`), a LiteLLM gateway's `max_input_tokens` (`GET <base_url>/model/info`) or the vendor's documented window. Unset, the agent compacts only after a "too long" error. `spe_agent_compaction_enabled: false` turns compaction off |
```

- [x] **Step 4: check and commit.** `grep -rn "context_window_tokens\|compaction" AGENT/README.md ANSIBLE/README.md
  docs/getting-started.md`: every key name matches `config.py` and `all.yml` exactly. Read the three diffs once
  for any mention of a plan, slice, handoff or `dev-local` (upstream-clean).

```bash
git add platform/agui/pydantic-ai-agent/README.md platform/ansible/README.md docs/getting-started.md
git commit -s -m "Document the agent's compaction configuration"
```

---

### Task 3: a de.NBI session on qwen compacts (added at the user's request, 2026-11-03)

The user asked for it while slice 2 ran (2026-11-03): "as a test for compaction when we finish please include a
test on denbi with qwen, a dummy conversation that stretches the context and verifying that compaction works".
Paid on de.NBI's quota: a scripted session of ordinary commands, no participant data.

**Files:**
- Create: `docs/superpowers/plans/2026-11-03-agui-compaction/evidence/slice-3/denbi/` (screenshots, the archived
  chat `.md`, the run log's `compactions` entry)

- [x] **Step 0: the instance.** Use a running de.NBI AG-UI instance on `qwen3.8-27b` (the main checkout's
  `instances/denbi-agui-01.yml`, if it is up) and redeploy its agent and chat from this slice's worktree
  (`-e spe_agui_source_dir=<worktree>/platform/agui`). If none is running, creating one is a cloud instance the
  user has not yet approved for this check: ask on the PR (one comment, `next-session.sh --end --blocked <PR>`),
  do not create it.
- [x] **Step 1: the window.** Task 1's `spe_webui_model_context_tokens` is qwen's full window, so a scripted
  session would take many turns to pass 0.8 of it. For this check only, set `spe_agent_context_window_tokens:
  20000` in that instance file (as slice 2 did on the dev VM), and say so in the evidence. (Ran at 40000: at
  20000 one turn of re-read `seq` output passed the trigger alone; `evidence/slice-3/denbi/README.md`.)
- [x] **Step 2: the session.** `python3 platform/dev/e2e/sessions.py --url <the instance's chat URL> --compose-file
  <its frontend compose file> --scenario compaction-live --shots <evidence>/denbi` (the dummy conversation: `seq
  1 3000` turns until the agent compacts). Expected: `session <id>, <n> compactions after <t> turns` with
  n ≥ 1, the divider, and a later answer that still knows the task (the summary carried it).
- [x] **Step 3: verify and archive.** `verify.yml` shows the `compaction` block; `archive.yml`, then the session's
  `index.md` row (`Compactions` ≥ 1), its `## Compacted` section, and the run log's `compactions` (each entry's
  trigger `threshold`, `next_input_tokens` below the window). Copy only the screenshots, the chat `.md` and the
  run log's `compactions` entry (as `compactions.json`), each grepped for canaries and keys first. Put the window
  back to task 1's value afterwards.

---

### Task 4: decision 13 on de.NBI's qwen, clarification 5, the dev VM's window, the end of the track

**Moved from Haiku to qwen at the user's request (2026-11-03, slice 3's session):** "to not burn a lot of
token on haiku let's test that on qwen". It runs on task 3's de.NBI instance, after task 3, against qwen's own
window `W` = task 1's `spe_webui_model_context_tokens` (262144, the gateway's `max_input_tokens`), on de.NBI's quota: two
requests vLLM rejects as too long (refused before inference), one small summary request, two ordinary answers.
Haiku makes no call in this slice. No cloud instance is created or destroyed.

**Files:**
- Modify (not committed): `MAIN/platform/ansible/instances/denbi-agui-01.yml`, then
  `MAIN/platform/ansible/instances/dev-local.yml` (step 5)
- Modify: `docs/superpowers/specs/2026-11-03-agui-compaction-design.md` (clarification 5, decision 13's row)
- Create: `docs/superpowers/plans/2026-11-03-agui-compaction/evidence/slice-3/decision-13/` (screenshots,
  run-log fields)
- Create: the handoff in `handoffs/`; Modify: the README's slices table, `AGENTS.md` *Current work*

The ruling behind this task is proposed clarification 5 (plan README): at window 20000 the proactive trigger
compacts long before the model's own window, so "the same session with compaction disabled fails with the
provider's error" cannot happen there. The check is therefore run against qwen's own window: one tool result
large enough to overflow it, which shows vLLM's real error with compaction off, then the reactive recovery with
it on. The proactive half of decision 13 (window 20000, divider, `next_input_tokens` below it) is slice 2's
early output on Haiku, cited, not repeated, and task 3's session on qwen.

- [x] **Step 0: the user’s answer, and the size.** Read plan PR #16's comments and the user's since (`gh pr
  view 16 --repo thodkatz/elixir-biohackathon-2026-test --comments`): if the user objected to clarification 5
  or asked for another check, stop here and end blocked on this slice's PR (`development-workflow.md`,
  *Gates*). `W` is task 1's value. Size the output to about 2.3 × `W` tokens so the request is rejected, not
  run: Qwen's tokenizer splits numbers into single digits, so `seq 1 N` costs about one token per character
  (≈ 6.9 a line for N in 10^5–10^6), and `N = ceil(W / 3)` gives ≈ 2.3 `W` tokens in ≈ 2.3 `W` bytes; the
  output cap `C = 8 * N` bytes. (Sized against Haiku's window, 1,000,000 tokens from Anthropic's Models API
  `max_input_tokens` on 2026-11-03, the same check would have sent ≈ 7 MB.)

- [x] **Step 1: compaction off, tool results uncapped.** In `denbi-agui-01.yml`, remove task 3's
  `spe_agent_context_window_tokens: 20000` and add `spe_agent_compaction_enabled: false`. Redeploy in place from
  the main checkout with this worktree's agent and the output cap `C` for this check only:

```bash
cd /workspace/biohackathon/biohackathon/elixir-biohackathon-2026-test/platform/ansible
ansible-playbook playbooks/create.yml -e @instances/denbi-agui-01.yml -e spe_agent_max_output_bytes=<C> \
  -e spe_agui_source_dir=$PWD/../../.claude/worktrees/impl-agui-compaction-3-denbi-docs/platform/agui </dev/null
```

- [x] **Step 2: the overflow.** *(Ran 2026-11-03: the refusal was de.NBI's LiteLLM gateway's "Context Window
  exceeded", not vLLM's; the folded text is the spec's clarification 5, the run `evidence/slice-3/decision-13/`.)* In the chat UI (Playwright or by hand, screenshots into the evidence
  directory), a new chat: "Run `seq 1 <N>` exactly as written, without pipes, filters or redirection, then read
  its whole output and tell me only the last line it printed." Expected: the tool call and its result show,
  then the red error bar with vLLM's "maximum context length" error (through `Service.sanitize`); the session
  record's last run is `failed`. Then check, in that order:
  - **The request was rejected.** If the run completed instead, the digits tokenised coarser than assumed: the
    request ran on de.NBI's quota, no money. Note the run log's `usage`, raise `N` to `W` (≈ 7 `W` bytes) and
    `C` with it, and redo steps 1–2 once; if it completes again, stop and end blocked on this slice's PR.
  - **The result is whole.** The run log's tool result (or the session record's) is ≈ 7 `N` characters, not cut:
    a `[truncated: …]` mark means the cap did not take (check `agent.yaml`'s `max_output_bytes`); a shorter
    result without one means the sandbox caps output too: note the limit, and use as many `seq` commands in one
    message as reach 2–3× `W` together, each under it.
  - If the request never reaches vLLM (a body limit in the chat UI, the runtime or de.NBI's gateway, e.g. a
    413), note where; splitting does not shrink the body, so end blocked on this slice's PR with the limit.

  Screenshot `overflow-disabled`.

- [x] **Step 3: compaction on, the same session recovers.** In `denbi-agui-01.yml`, remove
  `spe_agent_compaction_enabled: false` and set `spe_agent_context_window_tokens: null` (only the reactive
  trigger can act, which is what decision 13 checks; without it task 1 sets qwen's window). Redeploy as in step 1,
  with the same `-e spe_agent_max_output_bytes=<C>`. Reopen the same session from the sidebar and send "What was
  the last line?". Expected: the divider appears, then an answer naming `<N>`; the run is `completed`.
  Screenshots `recovered` and `recovered-open` (summary expanded). The first request of this run fails at vLLM
  exactly as in step 2; the capability's overflow list must recognise vLLM's real wording here. If it does not,
  the run fails as before: that is a slice 1 bug (the listed wording is wrong); add the real body to
  `test_compaction_providers.py`'s overflow cases, fix the list, and redo this step.

- [x] **Step 4: the run log.** From `ANSIBLE`, `ansible-playbook playbooks/archive.yml -e
  @instances/denbi-agui-01.yml </dev/null`, then in the output directory it prints, `agent-runs.jsonl`'s record
  for step 3's run: `compactions` has one entry with `trigger: "overflow"`, `messages_cut` ≥ 3, `usage` of the
  summary request, and `next_input_tokens` below `W`. Copy those fields (not the record, not `canaries.json`)
  into the evidence directory's `run-log.json`, after checking the summary holds no canary or key (the session
  ran `seq` only). The record for step 2's run has `compactions: []`.

- [x] **Step 5: put the instances back.** In `denbi-agui-01.yml`, remove `spe_agent_context_window_tokens`
  (task 1's value applies), redeploy without the `-e spe_agent_max_output_bytes` override, then
  `ansible-playbook playbooks/verify.yml -e @instances/denbi-agui-01.yml </dev/null`: the compaction task shows
  `enabled: true` and `W`, and `max_output_bytes` is back to 16384 in `agent.yaml`. On the dev VM, set
  `dev-local.yml`'s `spe_agent_context_window_tokens` to Haiku's window, 1000000, so it compacts proactively as
  decision 12 says, redeploy (no model call) and run `verify.yml` the same way. The dev VM's disk had 1.6 GB free
  on 2026-11-03, under the preflight's 5: if it still refuses, the dev VM step waits on the user (pruning there
  is not ours to decide) and the PR says so.

- [x] **Step 6: fold clarification 5.** In the spec, add to *Clarifications* (after 4; template:
  `spec-and-plan-layout.md`):

```markdown
### 5. Decision 13 is checked against the model's own window, on qwen — folded

**Status:** folded (2026-11-03, plan; slice 3/3).
**Question:** decision 13's check pushes a session past `context_window_tokens: 20000` and expects the same
session to fail with the provider's error when compaction is disabled; at 20000 the proactive trigger acts long
before any provider fails. And the user asked to run it on qwen rather than Haiku (2026-11-03), to spare Haiku's
tokens.
**Answer:** the check runs at the model's own window, on de.NBI's `qwen3.8-27b`. One tool result past qwen's
window (`seq`, with the output cap raised for the check) fails the run with vLLM's "maximum context length"
error while compaction is disabled; with compaction on and no window configured, the same session's next
message compacts through the reactive trigger and completes. The proactive part (window 20000, the divider, the
first request after the compaction below the window) is the early output's session (slice 2, Haiku) and the
de.NBI session on qwen (slice 3).
**Changed:** decision 13's acceptance check.
```

  and rewrite decision 13's acceptance check to: "On de.NBI (`qwen3.8-27b`): a session whose tool output is
  past qwen's own window fails with vLLM's \"maximum context length\" error while compaction is disabled; with
  compaction enabled and no window set, its next message compacts (trigger `overflow`), the divider shows, the
  run completes and the run log's input tokens of the first request after the compaction are below the window
  (clarification 5). The proactive path on a small window (`context_window_tokens: 20000`) is the early
  output's session." Also update the plan README's *Proposed spec clarifications* item 5 only if the wording
  changed in the run.

```bash
git add docs/superpowers/specs/2026-11-03-agui-compaction-design.md \
  docs/superpowers/plans/2026-11-03-agui-compaction/evidence/slice-3
git commit -s -m "Check decision 13 on qwen; fold spec clarification 5" \
  -m "vLLM's real overflow error with compaction off, the reactive recovery with it on."
```

- [x] **Step 7: the end of the track.** Write the handoff (`handoffs/<UTC stamp>-slice3-merged-track-done.md`):
  what ran, the evidence paths, the run-log fields, qwen's and Haiku's windows and where each was read, any ruling, and that
  participants get compaction only through an upstream port (spec §9). Check `BACKLOG.md`'s *AG-UI compaction
  upstream* item (slice 1, task 7, step 4) is there and still true; add it if it is missing.
  Update the slices table (all three done) and **remove the track's line** from `AGENTS.md`, *Current work*.
  Open the PR `de.NBI window, docs, decision 13 (3/3)` with `gh pr create --repo
  thodkatz/elixir-biohackathon-2026-test --base main`; the body says what ran (the syntax check, the three
  renderings, `verify.yml`, the dev VM session, the archive) and links the evidence. Then the local review round,
  the merge and the cleanup (`AGENTS.md`, *Development workflow*), the parent pin in `biohackathon`, and
  `next-session.sh --end` (the track's last unit).
