# Handoff: `/compact` spec reviewed, waiting on `approved` (PR #26)

**State.** Branch `spec/agui-compact-command`, worktree `.claude/worktrees/spec-agui-compact-command`, PR #26
ready, label `waiting-on-user`. The local review round (correctness and methodology) ran and every finding
was addressed (the PR's review comment, commits b6289e1 and 313157d). `sync-agents.py --check` exits 0.

**Once the user adds `approved`:**
1. Re-read the PR's comments newer than the review comment. Address any the user left, each in its own thread.
2. Merge #26 squashed (`forge-github.md`, *Merge*), after the checks in `AGENTS.md`, *Overrides*. A docs-only
   PR has no tests to run, so the checks are DCO and `sync-agents.py --check`. Clean up the worktree and the
   branch. Move the pin in `biohackathon`.
3. Next unit: the plan, `plan/agui-compact-command`, written with `writing-plans` from §15 and
   `inputs-for-plan.md`, *`/compact`*. It has two slices. Slice 2 builds the early output first and waits on the
   conversation record's slice 4 (#25). Update the track's line in `AGENTS.md` and BACKLOG's *Next* item.

**If the user asks for changes instead:** fix them on this branch, reply in their threads, and gate again.
