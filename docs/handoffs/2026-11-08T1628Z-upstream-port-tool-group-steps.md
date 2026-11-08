# 2026-11-08: upstream port tool group steps


Read only this one.

## Done

- **#50 ported upstream**: `contrib/agui-tool-group-steps` (`6627135`, from `upstream/main` `c42e31b`), pushed to
  `origin`; worktree `.claude/worktrees/contrib-agui-tool-group-steps`. Spec conflict resolved by keeping only
  clarification 25 (24 rides with `contrib/agui-chat-ui-polish`; whichever merges second fixes *Latest
  clarification*); the all-features check reference reworded (fork-only script). `npm run build` ok, `npm test`
  248/248 on the branch. Title and body in fork issue #51; no screenshots (the de.NBI ones show instance data; a
  clean one needs a paid run).
- Ledger (`749fbcb`): `23a944b` pending #51; `171398a` and `231ba4c` ruled out (fork-only / the upstream merge).
- `gh` cannot read the upstream org at all now (fine-grained token lifetime > 366 days refused), so check
  upstream PRs in the browser.

## Next (all wait on the user)

1. Open the upstream PRs from fork issues #42, #45, #47, #49, #51 (compare links at their tops), then record
   their numbers (`contributing-upstream.md`, step 6).
2. Whether to start "leave a running chat" (`BACKLOG.md`).
3. Canary ladder: accept `biohackathon` 0015; PR #3 (slice 1) is open, and the plan rewrite in *Next* waits on it.
