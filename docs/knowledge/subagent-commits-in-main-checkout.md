# An implementer subagent committed in the main checkout, not the unit's worktree

**Symptom.** Slice 9 of the canary ladder (#69): the task-1 implementer, dispatched from the session in
`.claude/worktrees/impl-canary-eval-ladder-9-airlock`, ran its commands from the main checkout and committed
there: `ee378e3` landed on local `main`, and the unit's branch had nothing.

**Fix used.** Cherry-pick onto the unit's branch in the worktree (it became `fdcca13`), then move local `main`
back without touching its working tree: `git -C <main checkout> reset --keep 138f791` (the commit `main` was
at). Nothing had been pushed, so no rewrite reached a remote.

**Prevent it.** A dispatch prompt names the worktree's absolute path and says to run every command there
(`cd <abs worktree path> && …`, or `git -C <abs path>`), and to check `git branch --show-current` shows the
unit's branch before each commit. A subagent does not inherit the dispatching session's working directory
reliably, and the main checkout is the repo it finds first.
