# Handoff: AG-UI titles, sidebar, theme (Change #29), task 6 review onward

**Unit:** `change/agui-titles-sidebar`, draft PR #29, worktree `.claude/worktrees/change-agui-titles-sidebar`. Being
implemented with `superpowers:subagent-driven-development`. The session hit its context budget, and task 6's review
was cut off by a rate limit.

## Where things are

- **Plan for the subagents:** `.superpowers/sdd/plan-29/plan-29.md`, git-ignored and in this worktree. It splits the PR
  body's plan into 7 tasks. **Ledger:** `.superpowers/sdd/plan-29/progress.md`, with every task's status, the deferred
  minors and the rulings. Trust it and `git log`.
- The workspace also holds reusable prompts: `implementer-template.md`, `reviewer-template.md`,
  `re-review-template.md` and `global-constraints.md`. Briefs come from the skill's `scripts/task-brief
  .superpowers/sdd/plan-29/plan-29.md N`, and review packages from `scripts/review-package
  .superpowers/sdd/plan-29/plan-29.md BASE HEAD`.
- **Done and reviewed:**
  - Task 1: the agent's `POST /title`.
  - Task 2: `write_run.py` counts only run lines.
  - Task 3: the chat UI's title route and browser call. A New chat's header shows no visible title, which the user
    asked for on 2026-11-03.
  - Task 4: the Ansible var `spe_agent_title_generation`.
  - Task 5: the resizable sidebar, capped to the viewport.
- **Task 6 (theme toggle):** implemented in `1e62ab8` (base `18035b8`); 204/204 chat tests pass and the build is clean.
  **Its review has not run.** Re-dispatch it with the reviewer template, the package
  `.superpowers/sdd/plan-29/review-18035b8..1e62ab8.diff`, the brief `task-6-brief.md` and the report
  `task-6-report.md`. Give the reviewer three named risks:
  - Do the dark tokens apply under both `data-theme="dark"` and System with the OS in dark mode, and not under
    `data-theme="light"`?
  - Is there no hydration warning or flash?
  - Does the chat's colour-scheme hook follow the effective theme?
- **The user's search-box request was dropped:** the placeholder already exists, and the user confirmed that.

## Next

1. Task 6 review, plus fix rounds if it finds anything.
2. Task 7, the docs, from the brief: spec §5 and §6, `13-conversation-record.md`, a clarification, and `BACKLOG.md`
   (delete *AG-UI chat minors* and add the tool-call cards item).
3. The final whole-branch review on the most capable model. Point it at the ledger's deferred minors. Two of them
   should be fixed before the merge:
   - The e2e's fake agent should handle `/title` on purpose.
   - `firstExchange` should send the first completed run's own user message.
4. Run every check from the PR body (agent, chat UI, host tests, `sync-agents.py --check`) and mark the PR ready.
   Then the local review round per `AGENTS.md` *Reviewers*: correctness and methodology, posted as one PR comment.
   Then squash-merge, clean up the worktree, and move the pin in `biohackathon`.
5. Redeploy `denbi-agui-01` from `main` (the user approved this in `BACKLOG.md`) and try it. The last redeploy, from
   `cab5a1d`, finished OK on 2026-11-03.
6. PR #28 (`/compact` slice 1) also edits the agent's `app.py` and config. If it merges first, rebase onto `main`.
