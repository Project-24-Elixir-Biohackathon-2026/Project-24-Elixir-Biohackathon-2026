# Handoff: AG-UI `/compact` slash menu (#32): merge and clean up

**Unit:** Change-mode PR #32, `change/agui-compact-slash-menu`. Worktree:
`.claude/worktrees/change-agui-compact-slash-menu` of the main checkout. The previous session ended at its
context budget.

**Done**
- `/compact` entry in CopilotKit's slash menu: offered while the whole input is a prefix of `/compact`, and
  picking it sends a bare `/compact`.
- The composer is marked (`data-command`: border, monospace text, a "command" badge) while the text parses as a
  command.
- Docs: spec §15 *In the chat input*, clarification 19, out-of-scope, the chat README, BACKLOG.
- The local review round is posted on the PR, and every finding is fixed (`17cfca0`, `34c4f94`).
- After the fixes: `npm test` 247 pass, `npm run build` ok, `sessions.py --scenario compact-command` ok.

**Next (no new review round: it is done)**
1. Re-read the PR's comments newer than the review comment, for anything from the user.
2. Before the merge, run `python3 .methodology/shared/sync-agents.py --check`, and check that the DCO check on
   #32 is green.
3. Squash-merge #32, signed off (`forge-github.md`, *Merge*).
4. Clean up: `git -C <worktree> status --porcelain` must print nothing, then `git worktree remove --force <worktree>`,
   `git branch -D change/agui-compact-slash-menu`, `git fetch --prune`, and `git pull --ff-only` on `main`.
5. In `biohackathon`, move the submodule pin to the merged `main` (`Pin test repo at <sha>: …`) and push.
6. No track line in *Current work* to update: this was a BACKLOG item. End with `next-session.sh --end`.

**Lessons:** the `compact-command` e2e scenario was stale on `main` since #29 (empty chat's title is an sr-only
`h1`, not `.spe-header-title`); fixed in this PR. CopilotKit's slash menu runs the highlighted entry on Enter
instead of sending, and its query is the first line only — the reason `offersCompact` checks the whole text
(spec §15 says so).
