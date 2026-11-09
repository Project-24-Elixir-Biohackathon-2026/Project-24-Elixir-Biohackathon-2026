# 2026-11-08: slice 1, review round half done

Mid-unit handoff (context budget). Read only this one. The unit's own handoff for slice 2 is
`2026-11-08T2133Z-slice-1-done.md`; once #57 merges, the after-merge handoff names it.

## State

- PR #57 (`impl/agui-leave-running-chat-1-rejoin-check`) is **ready**, all tasks done and pushed (head `b2a0d61`
  plus this handoff). Body says what ran. Every task review is clean (rulings in `progress.md` and the PR body).
- **Local review round:** the **correctness** reviewer finished (below). The **methodology** reviewer was stopped
  unfinished at the budget: **run it again** (`development-workflow.md`, *Local review*, methodology focus), over
  `git diff a7b81f1..HEAD`. When it was stopped it was checking whether the handoff's "Gotchas met" (the
  subagent stall after a usage-limit pause) should be a knowledge note.
- Then post both reviewers' findings as one PR comment (`Methodology 3a592f8c76d3…` first line: `git -C .methodology
  rev-parse HEAD`), address each, reply in one comment, run the checks (`npm test && npm run build` in
  `platform/agui/copilotkit-chat`, `methodology sync --check`), merge squashed
  (`gh api -X PUT repos/thodkatz/elixir-biohackathon-2026-test/pulls/57/merge -f merge_method=squash`), clean up,
  move the pin in `biohackathon`, write the after-merge handoff, `methodology next --unit`.

## Correctness review (opus): ready to merge, no Critical or Important

The task-3 snapshot finding (collector misses a replayed `MESSAGES_SNAPSHOT`'s ids) is ADDRESSED. Minors:

1. `slice-3-rejoin.md:54-60`: the collector misses an assistant message created with `id = toolCallId` when a
   `TOOL_CALL_START` names no parent (`@ag-ui/client` `resolveOrCreateAssistantMessage`); pydantic-ai always sets
   it. Fix: add "and `toolCallId` of a `TOOL_CALL_START`", or record the assumption.
2. `slice-3-rejoin.md:58-59`, `:70-72`: say the `onEvent` collector is in the same subscription as
   `onMessagesChanged`, made before `connectAgent` (as the passing page did, `658ba7b:…/app/rejoin-check/page.tsx`
   lines 93-105).
3. README ruling 2 (`README.md:44-47`) and `2026-11-08T2133Z-slice-1-done.md:14-15` say restore the page "from this
   PR's commits": name `658ba7b:platform/agui/copilotkit-chat/app/rejoin-check/page.tsx` (squash drops them).
4. `recorder.test.ts:189-225`: the failed run checks only `GET`'s `running`, not the list's; no `PATCH` during a
   run. Cancel goes through `handleOf(id)?.cancel()` rather than a client abort (same `cancelled`; accepted).
5. `progress.md:21`: "about 25–55 ms" — the evidence says 31–51 ms (off) and 21–53 ms (`wait`).

Deferred task-review minors triaged: none must be fixed before merge.
