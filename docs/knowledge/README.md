# Project knowledge index

<!-- One line per entry: [topic.md](topic.md) — the symptom or question, and the answer in brief. See
     AGENTS.md, "Project knowledge", for what belongs here. -->
- [gh-pr-create-token.md](gh-pr-create-token.md) — `gh pr create`: "Resource not accessible by personal access token (createPullRequest)": the fine-grained token lacked *Pull requests: write* on the fork (granted 2026-10-22). It has no access to upstream kraatz: open upstream PRs from the compare page.
- [node-test-directory.md](node-test-directory.md) — `node --test lib/` on Node 24: "Cannot find module '…/copilotkit-chat/lib'", `ℹ tests 1` and no test file run: pass the quoted glob, `node --test 'lib/*.test.ts'` (what `npm test` runs).
- [playwright-new-page.md](playwright-new-page.md) — Python Playwright: `page.context.new_page()` after `browser.new_page()` raises "Please use browser.new_context()": open the second tab with `page.context.browser.new_context().new_page()` instead.
- [agui-chat-sessions.md](agui-chat-sessions.md) — CopilotChat explicit threadId clears restored messages; `[role=alert]` matches Next's route announcer; `node --test lib/` MODULE_NOT_FOUND; `docker compose stop` exits 0 for a missing service and for a container that exited 1 or was killed (137): read `ps -a --format '{{.Service}} {{.ExitCode}}'`; Next's SIGTERM handler vs a detached run.
- [dev-vm-converge.md](dev-vm-converge.md) — `create.yml` on the dev VM: "only 3 GB free on the filesystem of /storage/docker, need 15" → `-e spe_min_free_gb=5`; "The agent's LLM key is empty" → `set -a; . ~/.config/spe-dev/llm.env; set +a`.
- [gh-default-repo.md](gh-default-repo.md) — `next-session.sh --end --blocked <n>`: "could not add waiting-on-user to PR #n"; `gh pr view <n>`: "Could not resolve to a PullRequest": no gh default repo, so gh asks upstream: `gh repo set-default thodkatz/elixir-biohackathon-2026-test`.
