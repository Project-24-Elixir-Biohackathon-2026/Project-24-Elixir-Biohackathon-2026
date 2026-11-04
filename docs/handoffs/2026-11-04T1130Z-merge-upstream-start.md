# 2026-11-04: merge `upstream/main`, then AG-UI via Coder, then the upstream package branch

**Asked by the user (2026-11-04):** "let's have the ag ui via coder and merging upstream and be ready to open a pr
to the kraatz repo". Three units, in this order; each is `BACKLOG.md`'s *Next* item of the same name, which has
the steps and the pass criteria. Approved already: instances and paid model calls for the Coder test (one
instance at a time, a Coder workspace counts), and de.NBI redeploys with their paid qwen calls.

1. **This unit: `change/merge-upstream-2026-11-04`.** `docs/guides/contributing-upstream.md`, *Merge upstream into
   our `main`*. Upstream is 52 commits ahead of our `main` (fetched 2026-11-04), including the clone-on-VM layout
   (`platform/instance/compose.yml`, `spe-apply`; `roles/agui/templates/docker-compose.yml.j2` is gone upstream):
   our AG-UI work (sessions, record, compaction, `/compact`, chat minors, tool-call cards, title cap) moves onto
   it. Merge commit, not squash (`AGENTS.md`, *Overrides*). Run every area's tests (*Running things*) and the
   local review round. After it merges, redeploy `denbi-agui-01` from `main` and re-run the all-features check
   below; the layout change makes that the first real test of the merge.
2. **AG-UI via Coder** (`BACKLOG.md`): from a portal workspace, `~/sperange` on our fork's branch, `spe-apply all`,
   then the checklist there. Fixes found go in their own PRs before step 3.
3. **Upstream package**: one `contrib/<slug>` branch from `upstream/main` (*Port fork work to upstream*), pushed
   to `origin` with the title and body written into a file, and the compare link given to the user. **The user
   opens the kraatz PR** (`gh` gets 403 there, `docs/knowledge/gh-pr-create-token.md`). No fork PR tracks it.

**State at hand-off.** `main` at `174062e` (#33 merged), pinned in `biohackathon` (`45de606`). `denbi-agui-01`
runs that tree. Every AG-UI feature passed there on 2026-11-04, through an SSH tunnel and Playwright: theme
without a flash, sidebar drag, tool-call cards (10 calls in one group), a model title ("Sensitive Dataset File
Audit", after #33 fixed empty titles on qwen: `docs/knowledge/reasoning-model-max-tokens.md`), rename, and
`/compact keep the canary paths` (divider, no bubble), each also after a reload. The script, adaptable for
step 1's re-check:

- tunnel: `ssh -F ~/.ssh/config -f -N -L 13000:127.0.0.1:3000 agent-service-1`
- flow: theme select Dark, reload, `data-theme` at DOMContentLoaded; drag `.spe-sidebar-resizer` +120 px, reload;
  New chat (`heading "New chat"`), a list-the-dataset prompt, wait for `run_end` in
  `docker exec spe-frontend-chat-ui-1 cat /data/sessions/<id>.jsonl`; `.spe-tool` attached (cards sit in a
  collapsed `.spe-tool-group`); header title; header *Chat actions* → Rename; a no-tool question, `/compact
  <focus>`, the same question; `.spe-compaction` count 1; reload; title line in the agent's
  `/var/lib/spe-agent/runs.jsonl` (`"type": "title"`).

**Gotchas met this session.**
- `create.yml` against `denbi-agui-01` needs `-e spe_min_free_gb=5` (`platform/ansible/README.md`, the default
  is 15). The VM had 3.1 GB free; unused `spe-agent`/`spe-chat-ui` tags and dangling images freed 11 GB (14 GB
  free now). Old tags pile up with every redeploy: prune them again before the next one if it's tight.
- The LLM key: `export DENBI_LLM_API_KEY=$(coder ssh theo/theo-workspace 'docker exec spe-frontend-open-webui-1
  printenv OPENAI_API_KEY')` (`docs/knowledge/denbi-llm-key.md`); never print it.
- **`theo/theo-workspace` is running** (template `spe-ga4gh-baseline`, outdated). It counts as the one instance
  for the Coder test: stop it before creating another, or use it if its template fits.
- A worktree's `uv run` can die with "Too many open files" and leave a broken `.venv`
  (`ImportError: cannot import name 'AsyncAnthropic'`): drop caches, `rm -rf .venv`, run again
  (`docs/knowledge/dev-vm-converge.md`).
