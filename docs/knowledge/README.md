# Project knowledge index

<!-- One line per entry: [topic.md](topic.md) — the symptom or question, and the answer in brief. See
     AGENTS.md, "Project knowledge", for what belongs here. -->
- [gh-pr-create-token.md](gh-pr-create-token.md) — `gh pr create`: "Resource not accessible by personal access token (createPullRequest)": the fine-grained token lacked *Pull requests: write* on the fork (granted 2026-10-22). It has no access to upstream kraatz: open upstream PRs from the compare page.
- [node-test-directory.md](node-test-directory.md) — `node --test lib/` on Node 24: "Cannot find module '…/copilotkit-chat/lib'", `ℹ tests 1` and no test file run: pass the quoted glob, `node --test 'lib/*.test.ts'` (what `npm test` runs).
- [gh-default-repo.md](gh-default-repo.md) — `next-session.sh --end --blocked <n>`: "could not add waiting-on-user to PR #n"; `gh pr view <n>`: "Could not resolve to a PullRequest": no gh default repo, so gh asks upstream: `gh repo set-default thodkatz/elixir-biohackathon-2026-test`.
