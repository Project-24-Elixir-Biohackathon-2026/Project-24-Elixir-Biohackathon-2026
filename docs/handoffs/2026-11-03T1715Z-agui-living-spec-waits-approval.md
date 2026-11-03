# 2026-11-03: AG-UI living spec — review addressed, waits for `approved`

Continues [`2026-11-03T1530Z-agui-one-living-spec-step3.md`](2026-11-03T1530Z-agui-one-living-spec-step3.md).
Unit: spec PR **#19** (`spec/agui-conversation-record`, worktree `.claude/worktrees/spec-agui-conversation-record`),
ready, labelled `waiting-on-user`.

## Done

- `75b3e02`: the sessions spec is cut to pointers (clarification 8). Compaction slice 2/3's Step 4 is
  re-pointed.
- `720f25b`: AGENTS and BACKLOG pointers.
- The local review round is posted on #19 (C1–C20, M1–M12) and every finding is addressed (`e49274c`,
  `02bc601`), with one reply comment and a gate comment asking for `approved`.
- #18's session (compaction slice 2) was told about the Step 4 change and acknowledged it. The compaction
  plan's handoff `2026-11-03T1700Z-slice-2-task-4-step-4-retargeted.md` records it.

## Next

1. Read #19's comments newer than the gate comment.
2. If the user added `approved`:
   - **If #18 merged first** with a sessions-spec clarification 8, rebase. Then renumber the fold clarification
     to 9 (the sessions spec's *Latest clarification*, and the living spec's references to "clarification 8").
     Move #18's clarification into `docs/specs/2026-10-15-agui-frontend-design/clarifications.md`, amending
     §14's paragraph on the archive as built.
   - Run `sync-agents.py --check` and the DCO check.
   - Squash-merge.
   - Clean up the worktree.
   - Move the pin in `biohackathon`.
   - Set the proposal `docs/proposals/2026-11-03-agui-history-integrity.md` to *folded*.
   - The next unit is the record's plan, `plan/agui-conversation-record` (`writing-plans`, from
     `inputs-for-plan.md`).
3. If the user left comments instead, address each one, then return to the gate.
