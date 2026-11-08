# 2026-11-08: denbi haiku disk


Read only this one. Previous: `2026-11-08T0302Z-agui-notes-brainstorm.md` (all of it done).

## Done this session

- Upstream moved to `Project-24-Elixir-Biohackathon-2026/Project-24-Elixir-Biohackathon-2026`; remote `upstream`
  re-pointed. `upstream/main` merged into ours: fork #48 (`68134c2`, merge commit; local review fixes in
  `6c2e97c`), kraatz #17 marked merged, `contrib/agui-package` deleted, pin moved in `biohackathon` (`1620689`).
  Upstream now has the portal **run report service** (`platform/report/`), TM-007 became TM-005, images bumped
  (open-terminal 0.16.1, Open WebUI 0.13.0, Node 26, Python 3.14).
- **Notes feature dropped** (user, 2026-11-08): the portal Report covers it; `BACKLOG.md` line (`cfa0913`).
- `contrib/denbi-example-data-root` pushed (fork `8e0b891`), PR text in fork issue #49, ledger line (`bed547e`).
  Three upstream PRs wait on the user to open them (issues #45, #47, #49; compare links in
  `docs/guides/contributing-upstream.md` step 5 form). Once the user gives the numbers: ledger + *Current work*.
- Dev-local on this NixOS guest is not possible (`docs/knowledge/machines/nixed-microvm.md`, `b10a7cc`). The user's
  plan instead: **develop model-backed features on the de.NBI VM with our Claude Haiku key.** Key:
  `~/.config/spe-dev/llm.env` (0600, `ANTHROPIC_API_KEY`). `instances/denbi.yml` (private, ignored) now has
  `spe_agent_model_provider: anthropic`, `spe_agent_model: claude-haiku-5-5`, `spe_agent_allowed_models:
  [claude-haiku-5-5]`, `spe_agui_smoke: false` (backup of the qwen version in the old session's scratchpad, not
  needed). `instances/dev-local.yml` also exists (unusable here).

## Where it stopped

`create.yml -e @instances/denbi.yml` (with `set -a; . ~/.config/spe-dev/llm.env; set +a`) failed at `spe-apply
build sandbox`: **no space left on device** on agent-service-1 (50 GB disk). The open-terminal 0.16.1 base needs
~5.7 GB new; I pruned dangling images + build cache only (back to 5.3 GB free). Our running stack is unchanged
(old images, containers not recreated). The other stack on the VM, `agent-stack` (Open WebUI v0.11.3 + its
`open-terminal-ca:0.12.4`, up 3 weeks), shares the 0.12.4 layers and costs ~13 GB.

## Next: drop `agent-stack` on agent-service-1, then re-converge with Haiku

The user (2026-11-08): "can we keep only our ag ui workflow? and maybe drop openwebui there so we don't test it
now". That is the go-ahead to remove `agent-stack` (Open WebUI + its terminal). Steps:

1. `ssh agent-service-1`: find the stack's compose dir (`docker inspect agent-stack-open-webui-1 --format
   '{{index .Config.Labels "com.docker.compose.project.working_dir"}}'`) and its volumes.
2. **Back up first**: tar its volumes and compose dir to `/data-share/backups/agent-stack-2026-11-08/` (the Manila
   share has 137 GB free). Check the tarballs list fine.
3. `docker compose down` in its dir (not `-v` until the backup is verified), then remove its images
   (`open-webui:v0.11.3`, `open-terminal-ca:0.12.4`, base `ghcr.io/open-webui/open-terminal:0.12.4` once unused)
   and, after the backup checks out, its volumes. Leave `workflow-stack-*` and `spe-frontend-*` alone.
4. Re-run the deploy from the main checkout's `platform/ansible` (under `script -qefc '…' log`, `</dev/null`).
   If it still is short, `spe_min_free_gb` is 5 in `denbi.yml`.
5. Then one Haiku check, which the user has agreed to in principle (paid, tiny): a chat through the tunnel or
   `spe_agui_smoke: true` for one verify run. Record what worked in `docs/knowledge/` (de.NBI with Anthropic).
6. Report to the user; next is the model-backed feature work they want to do there (ask what first).
