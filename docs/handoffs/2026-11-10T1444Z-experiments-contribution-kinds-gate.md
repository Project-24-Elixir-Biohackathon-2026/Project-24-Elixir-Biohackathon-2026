# 2026-11-10: experiments spec, contribution kinds: waiting on `approved` (PR #87)

**Unit:** `spec/experiments-contribution-kinds`, PR #87 (ready), worktree
`.claude/worktrees/spec-experiments-contribution-kinds`. Follows
`docs/handoffs/2026-11-10T1437Z-experiments-contribution-kinds.md`.

The local review round ran (correctness and methodology focuses; findings in the PR's comment `Methodology c6a7dc1…`,
23 items) and every finding was addressed in `f69354e`, replied to in one PR comment. The agent's rulings (what
*new* means against the target ref, the kind table in 05 with the bypass and interaction cases, lone catalogue
files refused, no improvement bar in `pr-body`, labels named as the kinds) are written into clarification 1 for
the user to overrule on the PR.

## Next

1. **The gate**: the spec waits for the user's `approved` on #87 (`methodology gate wait 87`). A comment instead
   of the label: act on it, push, open the gate again.
2. On `approved`: `methodology gate clear 87`, merge (squash, signed off), clean up the worktree and branch, move
   the pin in `biohackathon`, then the second handoff on `main` and `methodology next --end` (the next unit of the
   track, slice 2, is already #86's session).
3. If #86 merges first and conflicts (both touch `AGENTS.md`'s *Current work* line, and #87 touches the spec's
   `README.md` and `inputs-for-plan.md`), merge `origin/main` in with `git merge --signoff`: pushed branches are
   not rebased here.

## Watch for

- `gh pr create` fails on the org token check; use `gh api` (`docs/knowledge/gh-pr-create-token.md`).
- Untried: whether GitHub applies `.github/pull_request_template.md` beside `.github/PULL_REQUEST_TEMPLATE/`
  (slice 6 checks it).
