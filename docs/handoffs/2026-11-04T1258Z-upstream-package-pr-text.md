# 2026-11-04: the upstream AG-UI package, PR text posted

**Unit:** `BACKLOG.md` *Next*, *Upstream PR for the AG-UI package*; follows
`docs/handoffs/2026-11-04T1233Z-upstream-package-cut.md`.

**Done.**
- **The reviewer's path, checked** (the user, 2026-11-04: no separate smoke test; the screenshots' workspace
  covers it): `theo/agui-e2e`, its clone clean on upstream `d2a6232`, `git fetch … contrib/agui-package && git
  checkout FETCH_HEAD && spe-apply all` exited 0 and rebuilt the images; five chats on neutral prompts (three
  questions, a tool run, `/compact keep the commands we ran`), model titles, one divider, no page errors. No
  `archive.yml` run. The workspace is stopped; its `~/sperange` stays on `bf152a8` (detached).
- **Screenshots** 01–03 on the orphan `pr-assets` branch (`agui-package/`), checked: no dataset paths or canaries.
- **PR text**: fork issue #42 (compare link, title, body).
- **Owed by the BACKLOG item, on `main`**: the guide's *package port* path (step 3) and *Latest clarification* 23,
  `9abdbb9`.

**Next: waits on the user.** They open the PR on kraatz from #42, then close kraatz #9 pointing at it, and #42.
Then, once the PR has a number (1111Z handoff, *Decided*; `docs/guides/contributing-upstream.md`, step 6):
`docs/upstream-ports.md` lines for the package's fork commits (`bc5d944` moves from #9 to it); *Current work*'s
#9 line and the package line become one line for the new PR; `contrib/agui-token-cap-optional` deleted (branch,
worktree `/workspace/biohackathon/wt-upstream`, remote); the BACKLOG item removed.
