# 2026-11-03: AG-UI compaction plan: slice 2 drafted, write slice 3 and finish the plan

Unit: `plan/agui-compaction`, draft PR #16. Worktree `.claude/worktrees/plan-agui-compaction`. This session
tidied `slice-1-agent.md` (the four points of the previous handoff; README *Shared interfaces* gained
`CHARS_PER_TOKEN`, `SUMMARY_PROMPT`, `EMPTY_SUMMARY`, `over_trigger`) and wrote `slice-2-chat-archive.md`
(5 tasks), then hit the context budget. Inputs for slice 3: the earlier handoff
`2026-11-03T0130Z-facts-verified-write-the-plan.md`, *Repo facts* (stale-text line numbers) only.

## Next

1. **One self-review pass of `slice-2-chat-archive.md`** (`writing-plans` self-review), with these known points:
   - Task 1's *Files* says "Test: `recorder.test.ts` (one test)"; it adds two. Fix the count.
   - README *Shared interfaces*, **Chat**: `isCompactionMarker`'s parameter gained `toolCalls?: unknown[]`
     (same rule as the agent's `_is_marker_message`); update the README line to match.
   - Task 4 step 2's `compaction_live` uses guessed selectors (`.copilotKitMessage, [data-message-id]`,
     `copilot-stop-button`); it tells the implementer to take `slow_loop`/`two_turn`'s (sessions.py l. 693–742).
     Either read those now and write them in, or leave the instruction.
   - Add the slice 2 file's Review Focus coverage: README Review Focus 4 (slice 2, task 1, second recorder test)
     and 5 (task 3, `SUMMARY` with backticks and `## Not a section`) are covered; say nothing else is needed.
2. **Write `slice-3-denbi-docs.md`** (3 tasks), as the previous handoff's step 3 says: de.NBI window beside
   `spe_webui_model_id` in `inventory/group_vars/all.yml` (l. 171; vLLM `/v1/models` `max_model_len`, read by
   hand, no model call); docs (ansible README `## Agent frontend (AG-UI)` l. 236–262, getting-started
   `## 4. Configure an instance` table l. 132, agent README `compaction` block); decision 13's model-backed
   check on the dev VM (window 20000 is still in `dev-local.yml` from slice 2, task 5, step 4; the same session
   with `spe_agent_compaction_enabled: false` fails with the provider's error; then reset the instance file).
   Include the spec's *Inputs for the plan* stale-texts list: what slice 1/2 did not already update.
3. Then: local review round on PR #16, squash-merge (sign-off address: `docs/knowledge/gh-squash-signoff.md`),
   plan row in `docs/README.md`, the track's line in `AGENTS.md` (*Next: slice 1/3*
   `impl/agui-compaction-1-agent`), parent pin in `biohackathon`, handoff to slice 1, `next-session.sh --next`.
