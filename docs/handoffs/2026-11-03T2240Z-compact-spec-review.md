# Handoff: `/compact` spec written, next the review round (PR #26)

**State.** Branch `spec/agui-compact-command`, worktree `.claude/worktrees/spec-agui-compact-command`, draft PR
#26 (label `spec`). The spec is §15 of the living AG-UI spec,
`docs/specs/2026-10-15-agui-frontend-design/15-compact-command.md`, with decisions 31–39 in its README,
clarification 12 (the why: the options compared, what Claude Code, Codex, OpenCode, Gemini CLI and Open WebUI
do) and *Inputs for the plans*, *`/compact`*. The design was agreed with the user in chat, section by section;
the written spec has not been reviewed yet.

**Agreed with the user (2026-11-03), already in the spec:**
- A command run (the chat UI journals `/compact` as a typed `command`, the agent compacts from
  `forwardedProps.spe_command`), not a separate endpoint and not a user message the agent parses.
- Manual compaction needs `compaction.enabled` (as Open WebUI's does).
- The model-backed check (decision 39) runs on **de.NBI's `qwen3.8-27b`, via the portal's setup (its LLM key and
  model), not on the dev VM's Haiku**: the user's request. Paid: ask before running it.

**Next, in this order:**
1. Read the spec's §15 and README rows 31–39 (only those) and self-review: placeholders, contradictions with §13,
   ambiguity. Fix inline, commit.
2. Local review round (`development-workflow.md`, *Review and merge*, *Local review*: correctness and
   methodology focuses), findings as one PR comment, address each.
3. Mark #26 ready, update its body, post one comment asking the user for `approved`, then end at the gate:
   `.methodology/shared/claude/next-session.sh --end --blocked 26`.

**Check the state:** `git -C .claude/worktrees/spec-agui-compact-command log --oneline origin/main..HEAD`;
`gh pr view 26 --repo thodkatz/elixir-biohackathon-2026-test`.
