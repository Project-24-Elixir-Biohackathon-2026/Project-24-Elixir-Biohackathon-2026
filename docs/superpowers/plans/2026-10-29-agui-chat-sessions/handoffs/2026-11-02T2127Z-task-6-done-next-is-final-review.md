# 2026-11-02: slice 3, task 6 done, next is the final review

**State.** All of slice 3's tasks are done, reviewed and pushed on `impl/agui-chat-sessions-3-complete` (draft
PR #11). That includes task 6, which the user asked for after the plan was written. The paid check passed, and
[`2026-11-02T2055Z-slice-3-done.md`](2026-11-02T2055Z-slice-3-done.md) holds its evidence, tasks 1–5's rulings
and the track's closing edits. This file adds task 6 and what is left before the merge gate. The session ended at
the context budget.

**Task 6** (`ef15a86..b7f9708`, review by Opus: approved). The user asked for a real signal in place of the
browser check's stand-in waits after page loads, and for an audit of the check's other timing-dependent spots.

- The chat UI's action buttons (both *New chat* buttons, a row's open and `⋯`, the header's `⋯`) are disabled
  until `ready` (`app/use-hydrated.ts`, `app/page.tsx`). Playwright's click waits for them, and a real user's
  early click is no longer dropped silently.
- `sessions.py`: the stand-in waits are gone. The "no tag was saved" check now watches PATCH requests instead of
  sleeping 0.5 s. `check-shutdown.mjs`'s 300 ms sleep is explained, and `lib/api.test.ts`'s poll has a deadline.
- Knowledge note 6 in [`agui-chat-sessions.md`](../../../../knowledge/agui-chat-sessions.md) is rewritten.
- **Ran:** `npm test` (92), `npm run build`, the full local `sessions.py` run (31 `ok`), and `--scenario stop`
  standalone 10 times out of 10 (0 out of 10 before the ruling below).

**Rulings added since the slice-3-done handoff** (decision, why, cost if wrong):

1. **Task 6 was added to slice 3, at the user's request.** Why: the race that broke the first paid-check attempt
   also drops a real user's early click. Cost if wrong: about 7 extra commits in this PR.
2. **`ready = useHydrated() && isReady`, not hydration alone.** Why: once hydration was gated, an early *New chat*
   click before the agent's `isReady` mounted the chat ahead of the first-load effect. The stop scenario failed
   10 out of 10 until this was fixed. Cost if wrong: the buttons stay disabled a little longer than needed. The
   failure is loud, not silent.
3. **No React unit test for the gate.** Why: `node --test` has no renderer, and no new dependencies are allowed.
   The standalone stop scenario covers it instead: it clicks right after `goto` and then expects the button
   disabled. Cost if wrong: a regression shows up only in the browser run.
4. **Two short fix diffs were re-reviewed by the controller reading them, not by a subagent.** These are task 5's
   fix round 1 (4 lines of comment and prose) and task 1's `h3`→`h2`. Cost if wrong: none beyond the final
   review.

**Deferred minors for the final review to triage.** Each one is fixed in this PR or moved to `BACKLOG.md`:

- `SearchBox`'s Escape-dismissal is not reset on blur or refocus (task 1).
- `roles/agui/tasks/checks.yml:59-64` parses the `docker inspect` JSON three times (task 3, code the plan gave).
- `fake_agent.py` still makes a scratch dir with `mkdtemp()` when `--run-log` is given (task 4).
- Stale doc text from task 6:
  - `sessions.py:801`'s comment ("its own hydration wait") is stale.
  - These omit `isReady`: the note-6 line in `docs/knowledge/README.md`, and the "disabled until React has
    hydrated" comments at `sessions.py:602-604`, `:678-679` and `:698-700`.
  - The comment at `chat-header.tsx:143` reads awkwardly.
- `ready` stays false when the runtime's `/info` sync fails. That state was dead already, but it now shows no
  error bar, so a reload is the only way out (task 6 review). Fix it, or record it in `BACKLOG.md`.

**Next, in order:**

1. **Final whole-branch review.** Use `superpowers:subagent-driven-development`, *Final Review*: a review
   package over `git merge-base origin/main HEAD`..HEAD, the most capable model, and the minors above. Then one
   fix dispatch and one scoped re-review.
2. **The local review round** (`AGENTS.md`, *Reviewers*). Run correctness and methodology reviewer subagents,
   post their findings as one comment on #11, and address each one.
3. **Before the gate:**
   - Set the PR body to what ran (the *Running things* suites, the browser runs, `verify.yml`, the four archive
     checks, `destroy.yml` with the user's OK, the paid check) and link both handoffs.
   - Run `python3 .methodology/shared/sync-agents.py --check`.
   - Mark the PR ready and post one comment saying it is ready to merge.
4. **End** with `next-session.sh --end --blocked 11` (`AGENTS.md`, *Overrides*). After the user merges, move
   the pin in `biohackathon`.
