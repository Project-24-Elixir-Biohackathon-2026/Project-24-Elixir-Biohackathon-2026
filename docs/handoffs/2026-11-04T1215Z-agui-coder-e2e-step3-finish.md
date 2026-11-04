# 2026-11-04: AG-UI via Coder, step 3: finish #41 and #40

**Unit: `change/agui-coder-e2e-step3` (#40)**, mid-unit handoff at the context budget. The test itself is
**done and passed**. Only the PR work is left.

**What ran.** `create.yml` on denbi-agui-01 from main (de2b6d8), with `spe_frontends: [openwebui, agui]` (the
private instance file now sets that). Then 2 Open WebUI chats, the AG-UI all-features check (16/16) and a second
AG-UI session, and `destroy.yml`. The final archive `/data-share/runs/2026-11-04T115601Z_denbi-agui-01` passes the
item's criteria. Open WebUI `chats/` (2) and `index.md` are intact, `agui/` holds all 17 sessions, 17 journals and
the run log, and the top `index.md` links `agui/index.md`. Chat (pre-destroy `/api/sessions/<id>`), journals
(byte-identical) and archive agree for all 17 (`docs/knowledge/agui-archive-compare.py`: 0 mismatches). How to
repeat it: `docs/knowledge/agui-coder-e2e-check.md`, *The final archive*.

**Bug found and fixed in its own PR, #41** (`change/reset-compose-link`, worktree
`.claude/worktrees/change-reset-compose-link`). The reset left the `spe-frontend` containers up
(`docs/knowledge/compose-symlink-env.md`). The reset of denbi-agui-01 was finished with the fix (failed=0,
nothing of the instance left, `agent-stack` untouched), so **the instance is destroyed**. All workspaces are
stopped.

**Next, in order:**
1. **#41**: its local review round ran (correctness: no blockers, 2 low; methodology: 4). Everything was addressed
   in `28a2f73`: `COMPOSE_PROFILES='*'` on `down` (probed locally through a link with a template `.env`: 5
   services, `down` exit 0), the out-of-bounds link test, the docstring and the note. The BACKLOG mention rides in
   #40 (`8408a2e`). Post the findings and replies as one PR comment, check DCO, then squash-merge. **Add
   `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` to the squash body**: this session's commits lack it,
   and pushed branches are not rewritten. Clean up its worktree and branch.
2. **#40**: `git merge --signoff origin/main` (the fix `74c84b8` is already in this branch with the same content,
   so it should merge cleanly and drop out of the diff). Write the PR body (what ran, as above). Mark it ready,
   run the local review round (correctness and methodology), address it, squash-merge with the same trailer, and
   clean up.
3. Move the pin in `biohackathon`. Then `next-session.sh --next <branch> docs/handoffs/2026-11-04T1111Z-upstream-package-start.md`
   for the *Upstream AG-UI package* item (`BACKLOG.md`). It now also carries #41's fix upstream.
