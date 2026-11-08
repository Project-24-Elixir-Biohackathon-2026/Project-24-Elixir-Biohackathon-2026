# 2026-11-08: upstream port title on send


Read only this one. Previous: `2026-11-08T1628Z-upstream-port-tool-group-steps.md` (its *Next* still stands:
items 1–3 there wait on the user).

## Done this session

- **#52 squash-merged as `9eec3a8`**, "AG-UI chat: title a new session as its first run starts" (the user asked:
  the title did not show until the answer finished). A New chat's first run now fetches the list at once (fallback
  title on send) and asks for the model title from the first question alone, in parallel with the run; a session
  not listed in time is asked for once the run is recorded. Spec clarification 26 (supersedes 16's timing),
  decision 22. One local review round (comment on #52, 9 findings, all fixed or recorded). `npm test` 252/252,
  build ok, DCO green, `methodology sync --check` 0. The user tried it on de.NBI ("yep it worked").
- Worktree and branch removed (local and `origin`); `biohackathon` pin `2cb6b94`.
- de.NBI re-converge from `main` (no `spe_repo_ref`) was started in the background at the session's end; check
  `ssh agent-service-1 'cd ~/sperange && git log --oneline -1'` shows `9eec3a8`, else re-run
  `create.yml -e @instances/denbi.yml` (key: `set -a; . ~/.config/spe-dev/llm.env; set +a`).

## Next: the upstream port of #52 (memory *Upstream every change*)

Worktree `.claude/worktrees/contrib-agui-title-on-send`, branch `contrib/agui-title-on-send` at `upstream/main`,
clean, not pushed. Follow `docs/guides/contributing-upstream.md` steps 3–6:

1. `git diff --binary 9eec3a8^ 9eec3a8 -- . "${X[@]}" | git apply --3way --index` (X from step 1). Every code file
   applies cleanly; **two spec files conflict**: `docs/specs/2026-10-15-agui-frontend-design/README.md` (the
   *Latest clarification* line) and `clarifications.md` (clarification 26 lands after 25, which upstream lacks:
   24 rides with `contrib/agui-chat-ui-polish`, 25 with `contrib/agui-tool-group-steps`). Resolve as #50's port
   did: keep 26 alone at the end, *Latest clarification: 26*; whichever upstream PR merges later fixes the order.
   Also drop "the fork's PR #52" from clarification 26 and 16's status if the step-4 grep flags it.
2. Commit signed off, message without `(#52)`; step 4's grep and fork-only check; `npm test` and `npm run build`
   in `platform/agui/copilotkit-chat` on the branch.
3. Push to `origin`, post title and body as a fork issue with the compare link (step 5); ledger line for
   `9eec3a8` in `docs/upstream-ports.md` (`pending #<issue>`), committed to `main`.
4. Then report to the user: the six upstream PRs to open (issues #42, #45, #47, #49, #51 and the new one).
