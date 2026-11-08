# 2026-11-08: agui tool group steps merged


Read only this one. The unit's own handoff: `2026-11-08T1608Z-agui-tool-group-steps.md` (now on `main`).

## Settled by the merge

- **#50 squash-merged as `23a944b`**; worktree and branch removed (local and `origin`); `biohackathon` pin
  `69bdc10`. de.NBI re-converged from `main` (`create.yml`, repository at `23a944b`, failed=0); its tree is the
  branch's, so the de.NBI verification still holds.
- **Review round** (local, one comment on #50): correctness found the all-features check failing on a model that
  narrates before each call, fixed (`d463350`: fail only on two ungrouped cards with no text between them, tried
  on synthetic pages, not yet on de.NBI). Methodology: stale note, clarifications 17/20 statuses, two `BACKLOG.md`
  lines (`methodology worktree` in a submodule; a free e2e case across steps with the "Exploring" header), all fixed.
- Knowledge note `methodology-worktree-submodule.md`: claim by hand in this repo until agent-methodology is fixed.

## Next

1. **Waits on the user**: whether to start "leave a running chat" (`BACKLOG.md`; a spec change they approve).
2. Upstream port of #50: a `contrib/` branch from `upstream/main` (`docs/guides/contributing-upstream.md`) that
   the user opens as a PR; three `contrib/` worktrees already exist (`git worktree list`).
