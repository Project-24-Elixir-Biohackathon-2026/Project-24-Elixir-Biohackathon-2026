# 2026-11-03: slice 2/3 mid-unit; task 5's live session did not compact, rerun it

Handed off at the context budget. The unit is claimed: branch `impl/agui-compaction-2-chat-archive`, draft PR #18,
worktree `.claude/worktrees/impl-agui-compaction-2-chat-archive`. The SDD ledger, briefs and reports are in the
worktree's git-ignored `.superpowers/sdd/slice-2-chat-archive/` (`progress.md` first); task 5's full report is
`task-5-report.md` there.

## Done

| Task | Commits | Review |
|---|---|---|
| 1 chat divider, recorder tests | `d2ac5da` | clean |
| 2 fake agent compacts on `compact` | `1e231c4` | clean |
| 3 archive `## Compacted`, `Compactions` column | `6368a1a` | clean |
| 4 Playwright light/dark, `compaction-live`, sessions spec clarification 8 | `f9403ad` | clean |
| — slice 3 gains the user's de.NBI qwen check (task 3; old task 3 is task 4) | `e7652f3` | — |
| 5 steps 1–3, first live run: **no compaction** | `4f1dd7e` (evidence of that run) | — |

## Next: task 5 again, then the final review and the PR

1. **Fix `compaction_live`'s prompt** in `platform/dev/e2e/sessions.py`. Haiku ran `seq 1 3000 | tail -n 1`, so
   each turn added ~515 tokens (input 8840 → 12445 over 8 turns), never the 16000 trigger (0.8 × 20000). The
   threshold works; the prompt lets the model avoid the long output. Ask for the whole output, e.g. "run
   `seq 1 3000` exactly as written, without pipes, and tell me only the last line" (or `seq 1 6000`). Commit.
2. **Rerun once** (paid, approved 2026-11-02; at most one more run). The dev VM already has
   `spe_agent_context_window_tokens: 20000` in the main checkout's `dev-local.yml` and this worktree's agent
   deployed. Note: `spe_agui_source_dir` must be `<worktree>/platform/agui`, not the worktree root (task 5
   report, *Decision*); `AGENTS.md`, *Worktrees and deploying*, and slice 3 say `<worktree>`: fix them in the
   final wave, with a `docs/knowledge/` note. Replace `evidence/slice-2/live/` with the new run's screenshots and chat `.md` (grep for
   canaries and keys first). Leave the window at 20000 (slice 3 reuses it).
3. **Archive gap:** `archive.yml` run from the main checkout uses `main`'s `write_agui_run.py`, which lacks
   task 3's rendering until this PR merges. Render the live session with the worktree's
   `platform/ansible/roles/run_archive/files/write_agui_run.py` over the archived bundle, or say in the PR that
   the archived `.md` predates the rendering. Slice 3's checks hit the same gap only if they archive before #18
   merges.
4. **Final whole-branch review** (most capable model) over `050ee0f..HEAD`, pointing at the ledger's deferred
   minors. One fix wave must include: `write_agui_run.py:13` docstring lacks `compactions` (a stale doc), and
   plan task 4, step 1's text rewritten to the regex and constant actually used (the ruling below); do **not**
   edit task 4's Files list, step 4 or step 5 (PR #19 rewrites those lines).
5. **Task 5, steps 4–5**: handoff for slice 3, the slices table, `AGENTS.md` *Current work*, PR body (what ran,
   screenshots, the archived chat, the run log's `compactions`, and the ask to look at the early output), mark
   #18 ready, local review round, merge, cleanup, move the pin in `biohackathon`.

## Rulings (decision — why — cost if wrong)

- **Fake agent window 6000, not 8000**: FunctionModel's usage omits tool schemas, so 8000 never compacts (verified
  by hand both ways); plan task 2 and README rewritten in `1e231c4`. — A test window that compacts early in a long
  fake session.
- **README *Shared interfaces*' fake-agent summary** follows task 2's form (`Scripted summary of N characters…`).
  — One line.
- **`check_compaction` matches the later answer on `… the command ran\. Its output was:`** and names its constant
  `COMPACTION_XSS`: the plan's `$`-anchored regex never matches an ordinary answer (turn numbers restart after a
  compaction), and its `XSS` would reassign the module's `XSS`. — None; plan text still to rewrite (step 4 above).
- **Clarification 8 in the chat sessions spec** follows `main`'s plan although PR #19 moves that spec; commented on
  #19 so the PR merging second reconciles. — A renumbering in #19.
- **Slice 3 task 3 (de.NBI on qwen)** uses a running de.NBI instance and asks on the PR before creating one; it
  sets the window to 20000 for the check only. — A check on a smaller window than qwen's real one.

## Waiting on the user

Clarification 5 on PR #16 (slice 3's decision 13) is unchanged.
