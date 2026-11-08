# 2026-11-08: upstream port title on send done


Read only this one. Previous: `2026-11-08T1706Z-upstream-port-title-on-send.md`.

## Done this session

- **#52 ported upstream**: `contrib/agui-title-on-send` at `7ec2752` (one signed-off commit on `upstream/main`
  `c42e31b`), pushed to `origin`; title and body in fork issue #53. The two spec conflicts resolved as #50's port:
  clarification 26 alone after 23, *Latest clarification: 26* (24 and 25 ride with the other two AG-UI ports).
  Step-4 grep clean, fork-only check `ok`, `npm test` 250/250, `npm run build` ok on the branch.
- Ledger line for `9eec3a8` committed to `main`; no unported candidates remain.
- de.NBI runs `646d331`, #52's branch head, whose tree equals `9eec3a8`: no re-converge needed.
- The `contrib-*` worktrees stay until their upstream PRs are open (review fixes go on those branches).

## Next (all wait on the user)

1. Open the upstream PRs from fork issues #42, #45, #47, #49, #51 and #53 (compare links at their tops), then
   record their numbers (`contributing-upstream.md`, step 6) and close the issues.
2. Whether to start "leave a running chat" (`BACKLOG.md`).
3. Canary ladder: accept `biohackathon` 0015; PR #3 (slice 1) is open, and the plan rewrite in *Next* waits on it.
