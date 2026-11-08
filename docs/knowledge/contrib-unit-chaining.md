# A `contrib/` unit cannot be chained with `next-session.sh`

**Resolved** in the methodology by 2026-11-08 (generation `9d83559`): a handoff hop from the main checkout on its
default branch is now allowed (`next-session.sh`, the worktree check). So: write the handoff in `docs/handoffs/` on
`main`, push it, and run `methodology next docs/handoffs/<file>` from the main checkout. Also, since 171398a
`.methodology` is a machine-install link, not a submodule. What follows is the original finding.

Found 2026-11-04 (the user), handing off the upstream package unit (kraatz #17).

**Symptom.** Neither place a `contrib/<slug>` unit runs from lets `.methodology/shared/claude/next-session.sh
<handoff>` start the next session:

- From the main checkout, where `docs/guides/contributing-upstream.md`, step 2, says to work (the contrib worktree
  has no hooks): `not in a linked worktree; a unit's sessions run in its own worktree, never the main checkout
  (development-workflow.md, Claim it).`
- From `.claude/worktrees/contrib-<slug>`: `uncommitted changes; commit the handoff and the work first.` The
  branch is cut from `upstream/main`, which has no `.methodology` submodule, so the SessionStart hook's clone of
  it there shows as untracked (`?? .methodology/`) and the script's `git status --porcelain` check never passes.
  The handoff could not be committed there either: it is fork-only (`docs/handoffs/`).

**Workaround.** Write the handoff in `docs/handoffs/` on `main`, push it, and let the user start the next session
from it by hand (in the main checkout: `continue with docs/handoffs/<file>`). Untried: `AGENT_CHAIN_MAIN_CHECKOUT=1
.methodology/shared/claude/next-session.sh docs/handoffs/<file>` from the main checkout passes the worktree check
(the flag is meant for repos that work on `main`, such as agent-methodology), and `main` there is clean and pushed.

**Fix, for agent-methodology** (never edited here): either the clean check ignores an untracked `.methodology/`
(a branch without the submodule), or the main checkout is allowed for a branch that carries no methodology.
