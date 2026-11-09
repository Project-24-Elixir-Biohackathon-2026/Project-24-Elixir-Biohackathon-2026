# The de.NBI LLM key and the model's window

**Symptom.** `curl -H "Authorization: Bearer $KEY" https://denbi-llm-api-internal.bihealth.org/v1/models`
returns 401, `"Authentication Error, Key is blocked. Update via /key/unblock if you're an admin."` (LiteLLM).
Seen 2026-11-03 with the key on agent-service-1 (`denbi-agui-01`): every copy there is the same blocked key
(agent container, `~/agent-stack/webui.env`, `~/spe-frontend/agent.env`, the Coder spike's
`~/.config/coder-spike/server.env`). The endpoint does not resolve from the dev VM, so run curl on a de.NBI VM.

**Where a working key is.** The portal (`sperange.bihealth.org`) hands its own key
(`/etc/sperange/coder.env`, `DENBI_LLM_API_KEY`) to every workspace's Open WebUI. The portal VM itself is not
reachable by SSH from here (its SSH is open to admin networks only; `10.0.2.50` has no route from
agent-service-1), but a workspace is, through the Coder CLI:

```bash
# once: the CLI from the portal (same version), then the user logs in in their browser
curl -fsSL https://sperange.bihealth.org/bin/coder-linux-amd64 -o ~/.local/bin/coder && chmod +x ~/.local/bin/coder
coder login https://sperange.bihealth.org          # the user, interactively (`! coder login …`)
coder list --all                                     # use your own workspace, not another user's
coder ssh theo/theo-workspace 'docker exec spe-frontend-open-webui-1 printenv OPENAI_API_KEY | sha256sum | cut -c1-8'
```

Compare hashes, never print the key. For a deployment, read it into the environment for that run only
(`export DENBI_LLM_API_KEY=$(coder ssh … printenv OPENAI_API_KEY)`), never into a file.

**The window.** LiteLLM's `/v1/models` has no `max_model_len`; `/v1/model/info` (free, no completion) gives
`qwen3.8-27b` `max_input_tokens: 262144` (2026-11-03). That is LiteLLM's model info, not read from vLLM itself,
and LiteLLM enforces it itself: a request past it gets 400 `litellm.ContextWindowExceededError` ("Context
Window exceeded for given call … Max Input Tokens=262144, Got=…") before vLLM sees it (compaction plan, slice 3,
task 4, 2026-11-03). Whether vLLM's own `max_model_len` is the same figure is still unread.

**`coder ssh` starts a stopped workspace** (2026-11-04, step 3 of *AG-UI via Coder*): with `theo/theo-workspace`
stopped, the `coder ssh … printenv` above hung past the Bash tool's 2-minute timeout, and `coder list` showed
the workspace `Starting`. It is a full portal build (about 12 minutes), `coder stop` refuses it meanwhile ("A
workspace build is already active"), and it counts against "one instance at a time". Check `coder list` first.
With every workspace stopped, reuse the key the last deploy wrote on the VM instead (only while an instance is
deployed there: a `destroy.yml` reset removes `~/spe-frontend` and its `agent.env`), after checking it on a
de.NBI VM (prints only the status, 200 or 401):

```bash
ssh -F ~/.ssh/config agent-service-1 'K=$(grep -h "^OPENAI_API_KEY=" ~/spe-frontend/agent.env | cut -d= -f2-);
  curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $K" https://denbi-llm-api-internal.bihealth.org/v1/models'
export DENBI_LLM_API_KEY=$(ssh -F ~/.ssh/config agent-service-1 'grep -h "^OPENAI_API_KEY=" ~/spe-frontend/agent.env | cut -d= -f2-')
```

**With Coder out (2026-11-08)** there is no other copy within reach: agent-service-1 has only the blocked key
(`281aa6c1`), `spe-ga4gh-api-2` has none in `~/*/*.env`, `wes-service-1` has no route from the jump host. The
`spe_denbi_api_key` tracked in `platform/ansible/instances/test-1.yml` hashes to `281aa6c1` too: the blocked key,
not the portal's (`52bb9f98`). Without Coder a working key comes only from the project (or an admin unblocking
`281aa6c1` via LiteLLM's `/key/unblock`).

**`create.yml` stops at `agui : LLM key present`** ("The agent's LLM key is empty. Export SPE_LLM_API_KEY on the
controller (any provider), or DENBI_LLM_API_KEY (openai_compatible) / ANTHROPIC_API_KEY (anthropic)"), seen
2026-11-09 re-provisioning `denbi-agui-01` in place from a nixed guest with no key in its environment. The
assertion runs after the `repo` role, so the VM's clone has already moved to the controller's commit (and its
`instances/local.yml` is rewritten) while the stack keeps running the old build. Export a working key for that
run only, as above (`instances/denbi.yml` uses Anthropic: `ANTHROPIC_API_KEY`; de.NBI's model:
`DENBI_LLM_API_KEY`), never into a file; a run that needs no rebuild (slice 2's live check) needs no key.
