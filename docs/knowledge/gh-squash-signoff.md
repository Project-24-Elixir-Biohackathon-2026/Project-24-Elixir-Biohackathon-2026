# `gh pr merge --squash` authors the commit as the GitHub account

Found 2026-11-02, merging PR #14.

**Symptom.** The squash commit on `main` (`4157add`) has author `Theodoros Katzalis <thodkatz@gmail.com>`, the
GitHub account's own name and address, while the `Signed-off-by:` passed in `--body` said `theo
<theoclaude4@pm.me>` (and the branch's commits, `theo <thodkatz@pm.me>`). The DCO app checks only the PR's own
commits, so nothing went red, but the merge commit's sign-off does not match its author. It stays: `main` is not
rewritten.

**Fix.** Give the squash body a sign-off matching the account that merges:
`Signed-off-by: Theodoros Katzalis <thodkatz@gmail.com>` (check with `gh api user -q '.name + " " + .email'`
or the author of the last squash on `main`, `git log -1 origin/main --format='%an <%ae>'`), or leave `--body`
out and let GitHub fill it from the PR's commits.
