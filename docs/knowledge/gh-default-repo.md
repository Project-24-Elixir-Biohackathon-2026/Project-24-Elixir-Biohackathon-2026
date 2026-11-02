# `gh` without `--repo` resolves to upstream

Found 2026-11-02, ending a session at PR #10's merge gate.

**Symptom.** `next-session.sh --end --blocked 10` printed "could not add waiting-on-user to PR #10; nothing is
marked and this session goes on", even after the label had been added by hand. `gh pr view 10` printed
`GraphQL: Could not resolve to a PullRequest with the number of 10.`

**Cause.** The checkout has two GitHub remotes (`origin`, the fork; `upstream`, kraatz). With no default set
(`gh repo set-default --view` printed nothing), `gh` resolves `{owner}/{repo}` to upstream. The methodology's
`forge.sh` calls `gh pr view <n>` and `gh api repos/{owner}/{repo}/…` without `--repo`, so it asks upstream.

**Fix.** Once per clone: `gh repo set-default thodkatz/elixir-biohackathon-2026-test`. It is stored in the
local `.git/config`, which worktrees share. Commands you type yourself still take `--repo` (`AGENTS.md`,
*Development workflow*).
