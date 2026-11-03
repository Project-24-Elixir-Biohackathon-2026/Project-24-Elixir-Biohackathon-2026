# 2026-11-03: AG-UI compaction, write the plan

Next unit of the AG-UI compaction track (Full mode, stage 2): the plan, on branch `plan/agui-compaction`,
cut from `origin/main`. The spec merged as #15 (`f97697b`), approved under the user's delegation. The user's
instruction still holds: `2026-11-02T2351Z-agui-chat-minors-next.md`, *The user's instruction* (work
unattended, no upstream PRs, paid Haiku runs approved, merge fork PRs yourself).

## Next

1. Claim: `.methodology/shared/claude/worktree.sh plan/agui-compaction`, push, draft PR on the fork.
2. Write the plan with `superpowers:writing-plans` into `docs/superpowers/plans/2026-11-03-agui-compaction/`
   (a directory: three slices), from the spec
   `docs/superpowers/specs/2026-11-03-agui-compaction-design.md`. Read its decisions table, *Early output*
   and *Inputs for the plan* first; open sections only as a task needs them. The slices are named there.
3. Plan tasks must carry the spec's checks: the round-trip test first (CopilotKit 1.79), mocked-transport
   provider tests, decision 3 tested through `AGUIAdapter.run_stream`, slice 1's Haiku summary sample, and
   the *Texts this work makes stale* list.
4. One local review round, address it, merge squashed, add the plan's row to `docs/README.md`, update the
   track's line in `AGENTS.md`, move the parent pin, then hand off to slice 1.

## Lessons

- The squash sign-off still mismatched on #15: take the address from the last squash, not the last commit
  (`docs/knowledge/gh-squash-signoff.md`, updated).
- Hand library reading (pydantic-ai 2.56 internals, CopilotKit's runtime) to Explore subagents; the spec's
  cited line numbers (`_agent_graph.py:1488`, `models/anthropic.py:1490`, `ui/ag_ui/_utils.py:71`) are
  already checked.
