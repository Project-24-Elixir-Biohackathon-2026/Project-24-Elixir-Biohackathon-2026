# 2026-11-03: AG-UI compaction plan: review round posted, address the findings

Unit: `plan/agui-compaction`, PR #16 (ready, not draft). Worktree `.claude/worktrees/plan-agui-compaction`. This
session self-reviewed slice 2, wrote `slice-3-denbi-docs.md` (proposed clarification 4: decision 13 checked
against Haiku's own window), ran the local review round (correctness + methodology subagents) and posted it as
one PR comment, 17 numbered findings: https://github.com/thodkatz/elixir-biohackathon-2026-test/pull/16#issuecomment-6598326476
(read it: `gh pr view 16 --repo thodkatz/elixir-biohackathon-2026-test --comments`). Then hit the budget.

## Done of the findings (commit after this handoff's)

- 1 (partly): slice 1 verified facts gained the tool-definitions note; `BIG` = 15,000 chars; every
  `window(1000)` → `window(6000)`; the "summary past the trigger" test uses 16,000 chars. **Still to check**:
  `test_over_trigger_boundaries` (l. ~871) uses its own `context_window_tokens=1000`, fine as is; reread
  task 4's prose and task 6 tests for numbers that assumed the old sizes (e.g. `messages_cut` expectations,
  "about 1000 estimated tokens", slice 1 task 5 `test_overflow_after_a_proactive_compaction_fails`).
- 2: done (fact rewritten, the retry's own usage increment removed; `test_overflow_compacts_and_retries`
  still expects 2).
- 4: done (test string `{"command":"cat f"}`).

## Next

1. Remaining findings, then reply on the PR in one comment, one line per number (fixed in <sha> / why not):
   - 3: `transcript` always keeps the latest (non-framed) user entry: build a set of pinned indices
     (previous summary, last entry, latest `User: ` entry), drop the others oldest first; add
     `test_transcript_keeps_the_latest_request` (history: old user 400 chars, "the request", two long
     assistant texts; `max_chars=300`; "User: the request" kept, "old " gone).
   - 5, 6 (slice 2): `COMPACT_WINDOW` ≈ 8000, long output ≈ 30,000; the stop test asserts the marker kept and
     `cancelled`, not the exact list.
   - 7, 9, 13 (slice 3, task 3): read Haiku's documented window before step 1, size the `seq` output to 2–3×
     it, stop if the first overflow request is not rejected, check the result's length (the sandbox may cap);
     PR #16's body and slice 3's PR point the user at clarification 4 (it rewrites an approved acceptance check).
   - 8: tests for `enabled: false` with a reactive overflow (task 5, `overflow_run(..., **window(6000,
     enabled=False))` → `RUN_ERROR`, no summaries); summary tokens in usage (task 4); a later-run variant of
     `test_later_run_cuts_at_marker` with `window(6000)` and no summary (estimate starts after the marker).
   - 10: slice 1, task 7 adds a `BACKLOG.md` line (port compaction upstream; upstream's frontend spec
     *History* stale); slice 3, step 7 checks it.
   - 11: name mid-slice handoff points in slice 1 (after task 4 and after task 6) in the README's slice note.
   - 14–17: README fixes (clarification 3 folds in slice 1 task 6; file row; l. 11; Status `planned`; rulings
     also rewrite the text they change; slice 2's PR rewrites slice 3's tasks for a user-asked change).
2. Then merge as the previous handoff's step 3 says: squash (sign-off: `docs/knowledge/gh-squash-signoff.md`),
   `docs/README.md` plan row, *Current work* line → *Next: slice 1/3* `impl/agui-compaction-1-agent`, parent pin,
   handoff to slice 1, `next-session.sh --next` (finding 12).
