# `gh pr merge --squash` authors the commit as the GitHub account

Found 2026-11-02, merging PR #14.

**Symptom.** The squash commit on `main` (`4157add`) has author `Theodoros Katzalis <thodkatz@gmail.com>`, the
GitHub account's own name and address, while the `Signed-off-by:` passed in `--body` said `theo
<theoclaude4@pm.me>` (and the branch's commits, `theo <thodkatz@pm.me>`). The DCO app checks only the PR's own
commits, so nothing went red, but the merge commit's sign-off does not match its author. It stays: `main` is not
rewritten.

**Fix.** Give the squash body a sign-off matching the account that merges:
`Signed-off-by: Theodoros Katzalis <thodkatz@gmail.com>`, or leave `--body` out and let GitHub fill it from the
PR's commits. To look the address up, take the author of the last **squash** on `main`:
`git log -1 --grep='(#[0-9]*)$' origin/main --format='%an <%ae>'`. Neither `gh api user` (it returned
`thodkatz@pm.me`) nor the last commit on `main` (often a direct commit by `theo <thodkatz@pm.me>`) gives it:
PR #15's squash (`f97697b`, 2026-11-03) was signed off from the last commit and mismatches the same way.
