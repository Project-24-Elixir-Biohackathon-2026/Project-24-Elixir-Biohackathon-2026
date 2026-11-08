# 2026-11-08: spec leave running chat merged



Read only this one. Previous: `2026-11-08T1813Z-spec-leave-running-chat-draft.md` (the spec unit's own; its *Done*
is the brainstorm and the draft).

## Done this session

- **Spec approved and merged**: the user approved in session ("ok please add approved and let's proceed"); comment
  and `approved` label added by hand, since `methodology gate approve` can't read labels on the fork
  (`docs/knowledge/gh-pr-create-token.md`; BACKLOG item to carry the fix to agent-methodology). PR #55 squashed as
  `651f0d8`. Clarification 27 of the living AG-UI spec, decisions 26 and 40–44.
- **One local review round**, 15 findings (correctness 9, methodology 6), all addressed in `ea5e03b` (one no
  change), posted on #55. What changed after the user's approval, none of it changing intent (the agent's calls):
  the list is also fetched on `visibilitychange`/`focus` (decision 44's check: mark within 3 s of the first tab
  regaining focus); `CopilotChat` stays non-explicit, remounted per session, and the holder rejoins with
  `connectAgent`; decision 42's fallback has its own check; errors subscribed per holder, "New chat" when untitled;
  an open idle session that turns running is rejoined; Delete is a page-only rule; inputs-for-plan names the e2e
  checks in `platform/dev/e2e/sessions.py` that assume a locked page.

## Next

1. **Plan unit**: `plan/agui-leave-running-chat`, the `writing-plans` skill into
   `docs/superpowers/plans/2026-11-08-agui-leave-running-chat/`, from §6 and `inputs-for-plan.md`'s *Leaving a
   running chat* (slice 1 builds decision 42's rejoin check first; the stop point there is a gate).
2. Waiting on the user, unchanged: the six upstream PRs (fork issues #42, #45, #47, #49, #51, #53); canary ladder
   `biohackathon` 0015 and PR #3.
