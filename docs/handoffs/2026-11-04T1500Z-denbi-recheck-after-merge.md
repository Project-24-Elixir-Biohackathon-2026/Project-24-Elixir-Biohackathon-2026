# 2026-11-04: redeploy `denbi-agui-01` from `main` after the upstream merge, re-run the all-features check

**Unit: `change/denbi-recheck-2026-11-04`**, step (1) of `BACKLOG.md` *Next*, *AG-UI via Coder*. Then the
same item's step (2) (Coder workspace) and the *Upstream PR for the AG-UI package* item, as
`2026-11-04T1130Z-merge-upstream-start.md` lists them. Approved already: de.NBI redeploys with their paid qwen
calls; instances and paid calls for the Coder test (one instance at a time).

**State.** `upstream/main` merged in #35 (`a3cf960`, a merge commit; DCO red on upstream's commits only, merged by
the user's decision, now in `docs/guides/contributing-upstream.md`). #34 (tool-card wording, theme toggle) merged
just before, so `main` holds both. `denbi-agui-01` runs #34's worktree, deployed by that session on the **old**
layout (`spe_agui_source_dir`, rendered compose file): this redeploy is the first one of upstream's clone-on-VM
layout (`platform/instance/compose.yml`, `spe-apply`, images `:local`, `~/sperange` on the VM).

**Before `create.yml`:**
- The private `instances/denbi-agui-01.yml` (main checkout) must set
  `spe_repo_url: https://github.com/thodkatz/elixir-biohackathon-2026-test.git`: the default is kraatz, which
  lacks our commits (`AGENTS.md`, *Worktrees and deploying*). `spe_repo_ref` defaults to the main checkout's HEAD,
  so it must be pushed (it is: `a3cf960` plus this handoff's commit).
- The old layout's containers and `~/spe-frontend` files differ from the new: watch for leftovers
  (`spe-frontend` project, the old `docker-compose.yml` as a file where a link is expected, old `spe-agent:<hash>`
  tags filling the disk; `docs/knowledge/denbi-disk-full.md`). `-e spe_min_free_gb=5` as before.
- Key: `docs/knowledge/denbi-llm-key.md`, never printed.

**Then** the all-features check as in the 1130Z handoff (tunnel, theme, sidebar drag, tool-call cards in a group,
model title, rename, `/compact <focus>`, reload), now with #34's wording ("Explored", toggle top right) and the
`chat-sessions` volume from `platform/instance/compose.yml` (`docker exec spe-frontend-chat-ui-1 ls /data/sessions`).
Then `archive.yml` (live) from the main checkout. A failure is fixed in its own PR before step (2).

**Known gaps from #35 (BACKLOG):** the `ui-dev` profile has no archive (export refuses it); the canary ladder plan's
stale tasks. **Gotcha this session:** a background `while pgrep -f "<pattern>"` wait loop matches its own shell and
never ends (`docs/knowledge/pkill-self-match.md`); match with a bracket, `pgrep -f "[a]nsible-playbook …"`.
