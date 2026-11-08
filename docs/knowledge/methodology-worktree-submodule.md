# `methodology worktree <branch>` in this submodule: worktree under `.git/modules/`, no claim

Seen 2026-11-08, claiming `change/agui-tool-group-steps` from the main checkout
(`/workspace/biohackathon/elixir-biohackathon-2026-test`, a submodule of `biohackathon`).

**Symptom.** `methodology worktree change/agui-tool-group-steps` printed a worktree path under the parent's git
directory, not under this checkout:

```
/workspace/biohackathon/.git/modules/elixir-biohackathon-2026-test/.claude/worktrees/change-agui-tool-group-steps
```

and opened no draft PR: its `gh pr create` stops on the organization token error (`gh-pr-create-token.md`).

**Cause.** The script (`shared/claude/worktree.sh`) takes the main checkout from the first line of
`git worktree list --porcelain`. In a submodule whose git directory lives in the parent, that line is the git
directory, `worktree /workspace/biohackathon/.git/modules/elixir-biohackathon-2026-test`, not the checkout. The
path the workflow expects is `<main checkout>/.claude/worktrees/<branch, / as ->` (`AGENTS.md`, *Claim before you
work*).

**Fix: claim by hand.** Remove the misplaced worktree, then from the main checkout:

```bash
B=change/<slug>; W=.claude/worktrees/${B//\//-}
git worktree remove --force /workspace/biohackathon/.git/modules/elixir-biohackathon-2026-test/$W  # the misplaced one
git fetch origin && git worktree add -b "$B" "$W" origin/main
ln -s "$(readlink .methodology)" "$W/.methodology"   # git-ignored, as in the main checkout
git -C "$W" push -u origin "$B"
gh api repos/thodkatz/elixir-biohackathon-2026-test/pulls -f title='…' -f head="$B" -f base=main \
  -F draft=true -f body='…' --jq .number
```

**The chain lands there too, and status doesn't see it** (seen 2026-11-08, the leave-running-chat plan and slice
1). `next-session.sh` takes the main checkout from the same first line (`mc=…` for `--unit`'s new worktree, and
the `repo=` deck hint), so `methodology next --unit` starts the next unit's session in
`/workspace/biohackathon/.git/modules/elixir-biohackathon-2026-test/.claude/worktrees/<branch>` with
`am.repo` set to the git directory. `methodology status` from the checkout takes its repo as
`dirname "$(git rev-parse --git-common-dir)"` (`status.sh`), here `/workspace/biohackathon/.git/modules`, which
matches neither, so the running unit has no row; `git worktree list` from the checkout does show it. To see it:

```bash
AGENT_SUPERVISE_REPOS=/workspace/biohackathon/.git/modules/elixir-biohackathon-2026-test methodology status
agent-deck list --all          # every session, with its id for `methodology attach <id>`
```

The worktree is a working one: commits, pushes and PRs from it are fine; only its place is wrong.

Until `methodology worktree` resolves the main checkout another way (an agent-methodology change, `BACKLOG.md`),
use these commands for every claim in this repo.
