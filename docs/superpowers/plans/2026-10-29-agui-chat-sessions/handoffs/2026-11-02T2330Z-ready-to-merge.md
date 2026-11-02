# 2026-11-02: slice 3 ready to merge, waiting on the user

**State.** PR #11 has passed every check and is waiting for the user to merge it (`AGENTS.md`, *Overrides*). The
reviews it went through:

- **Final whole-branch review** (Opus): 0 Critical or Important, 4 Minor. The fixes are `04cbfd3..2421457`, and a
  scoped re-review found every finding addressed.
- **Local review round** (correctness: Opus; methodology: Sonnet): 7 items, posted on #11 as one comment. The
  fixes are `6386a10..aa51dfc`, and the replies are in a second comment.

The PR body lists what ran. This file adds this session's rulings to those in
[`2026-11-02T2127Z-task-6-done-next-is-final-review.md`](2026-11-02T2127Z-task-6-done-next-is-final-review.md).

**Rulings** (decision, why, cost if wrong):

1. **The final fix wave covered M1, M2, M4 and deferred minor 1.**
   - M1 is the task-6 comments and docs that were wrong.
   - M2 rewrites the spec's decision 4 check and §3 *Refresh* to say what clarification 1 decided.
   - M4 makes `ready` also wait for `active !== null`.
   - Deferred minor 1 resets the search box's Escape state on blur.

   Deferred minor 6 (no error bar when `/info` fails) went to `BACKLOG.md`. Minor 2 was already fixed
   (`e9d2bba`). Minors 3 and 4 need nothing: the first is correct code the plan gave, and the second's `mkdtemp`
   directory also holds `prompt.txt`.

   Why: the reviewer's triage. Cost if wrong: a few lines of extra churn, or a small UI dead state left for later.
2. **The re-review's last nit was folded into the local round's fixes, with no second final fix wave.** The nit
   was the knowledge index line for note 6 leaving out `active !== null`. Cost if wrong: none; it is fixed in
   `cc396ce`.
3. **Local review finding 5 got a pushback instead of a `BACKLOG.md` item.** It was the triple parse in
   `checks.yml` and the `mkdtemp` in `fake_agent.py`. Why: both are non-defects (ruling 1), so nothing is
   deferred. Cost if wrong: a micro-cleanup that never gets done.
4. **Local review findings 1 and 4 went to `BACKLOG.md`.** Finding 1 is that `showsRun` takes a metadata PATCH as
   the run's save. Finding 4 is that no browser check covers a refused run. Why: both are rare, the current
   behaviour matches the spec's text, and fixing either is new design or a new scenario. Cost if wrong: in a rare
   case, a failed save goes unreported, or a regression goes unnoticed.
5. **No second paid run after task 6 changed `two_turn`.** The PR body says so. Why: the change only removed a
   wait in the test code, and it passed locally against the fake agent. Cost if wrong: `two_turn` breaks against
   the real model, and the next paid run finds it.
6. **The local fix round's 3-line `sessions.py` diff was reviewed by the controller reading it, not by a
   subagent.** Cost if wrong: none beyond the user's own review.

**Next:** the user merges #11 and removes `waiting-on-user`. After the merge:

1. Clean up the worktree and branch.
2. Move the pin in `biohackathon` to the merge commit.

The track is done. No next unit follows.
