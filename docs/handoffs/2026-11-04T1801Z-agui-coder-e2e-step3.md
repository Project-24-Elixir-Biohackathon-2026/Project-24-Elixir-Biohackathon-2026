# 2026-11-04: AG-UI via Coder, step 3 start (the final archive)

**Unit: step 3 of `BACKLOG.md`'s *AG-UI via Coder* item**; steps (1)-(2) done (#36, #38). Claim a new
`change/<slug>` branch and draft PR (`development-workflow.md`, *Claiming*). Named `T1801Z` to sort after #38's
own handoffs (`T1800Z`); the start routine is pointed at this file by `next-session.sh --next`.

**Question.** The archive on stop runs from the portal's upstream checkout, which has no AG-UI export yet, so a
portal stop can't test it. Test it with `create.yml`/`destroy.yml` from **our** checkout, both frontends on (#39).

**Before anything:**
1. **Stop `theo/agui-e2e`** (`coder stop theo/agui-e2e`): at most one instance at a time, and a Coder workspace
   counts (the user's approval, 2026-11-03, in the *AG-UI via Coder* item). Its fake `hosts.yml` is already removed;
   its `context_window_tokens: 48000` dies with it. Check nothing else of ours runs (`theo/theo-workspace`
   stopped; `denbi-agui-01` is shared de.NBI, see the memory notes on it).
2. Push the branch you deploy: the instance clones `spe_repo_url` at `spe_repo_ref` (default: the main checkout's
   HEAD, which must be pushed).

**Run**, from the **main checkout's** `platform/ansible/` (private instance files live only there), `</dev/null`
(under `script -qefc` in a sandbox, `docs/knowledge/ansible-nonblocking-stdout.md`):
- Instance file with `spe_repo_url: https://github.com/thodkatz/elixir-biohackathon-2026-test.git` and
  `spe_frontends: [openwebui, agui]`. `instances/denbi-agui-01.yml` still sets the old `spe_frontend: agui`:
  replace it, or copy the file under a new name. The LLM key: `docs/knowledge/denbi-llm-key.md`.
- `create.yml`, then a few chats in both frontends (AG-UI: two sessions, one compaction or `/compact`; the driver
  `docs/knowledge/agui-coder-e2e-check.py` can do it through a tunnel), then `destroy.yml`, which archives.

**Passes when** (the item's criteria): Open WebUI's `chats/` and `index.md` are intact, `<run>/agui/` is complete
(every session, its journal, the run log), the top `index.md` links `agui/index.md`, and each session's messages in
the chat, its rebuilt journal and the final archive agree, run for run. How the step-2 checks were made and their
gotchas: `docs/knowledge/agui-coder-e2e-check.md`.

**Then:** the item done in `BACKLOG.md`, the *AG-UI via Coder* line in `AGENTS.md`'s *Current work* removed, the
instance destroyed. Next on the track: the *Upstream: port the AG-UI package* item (handoff
`docs/handoffs/2026-11-04T1111Z-upstream-package-start.md` on `main`).
