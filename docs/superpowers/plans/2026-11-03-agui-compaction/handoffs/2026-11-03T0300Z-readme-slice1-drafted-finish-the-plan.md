# 2026-11-03: AG-UI compaction plan: README and slice 1 drafted, finish the plan

Unit: `plan/agui-compaction`, draft PR #16. Worktree `.claude/worktrees/plan-agui-compaction`. The session hit
the context budget after writing `README.md` (committed) and `slice-1-agent.md` (committed with this handoff).
The previous handoff's research (`2026-11-03T0130Z-facts-verified-write-the-plan.md`) is the input for slices 2
and 3: read its *Ruling*, *Repo facts* and *Slicing* sections only, not the whole file again.

## Next

1. **Tidy `slice-1-agent.md`** (one pass, with the `writing-plans` self-review):
   - Task 4, step 3: drop the paragraph about the `next_input_tokens` condition and write the simple form in
     the code (`if run.records and run.records[-1].next_input_tokens is None:`).
   - Task 5, step 2: the fallback sentence is garbled ("restructure … is **not** possible"); rewrite it as: if
     the answer does not reach the stream, record a ruling and end the slice blocked (decision 3 depends on it).
   - Check the tests named in the slice header match the test functions written (e.g. `test_providers.py` vs
     `test_compaction_providers.py`).
   - Add `SUMMARY_PROMPT`, `EMPTY_SUMMARY`, `over_trigger`, `CHARS_PER_TOKEN` to the README's shared interfaces.
2. **Write `slice-2-chat-archive.md`** (5 tasks, per README's slices table and *Shared interfaces*): chat
   renderer (`lib/compaction.ts` + test, `app/compaction-divider.tsx`, `CopilotChat messageView={{
   assistantMessage: AssistantOrCompaction }}` in `app/page.tsx:272-285`, falling back to
   `CopilotChatAssistantMessage` from `@copilotkit/react-core/v2`, module-scope constant), recorder test of a
   compacting run (schema-valid, auto title unchanged, stop after the marker keeps it), `fake_agent.py`
   `compact` keyword (+ `function=` summary, small window in its inline config l. 83–89), archive `## Compacted`
   + `Compactions` column (`write_agui_run.py` l. 102–130 and 226–248, `fence` from `write_run.py:46`),
   Playwright `check_compaction` with light/dark screenshots in `evidence/slice-2/`, chat sessions spec §4
   clarification, then the early output on the dev VM (window 20000, Haiku, `verify.yml` shows the block).
3. **Write `slice-3-denbi-docs.md`** (3 tasks): de.NBI window beside `spe_webui_model_id` (vLLM `/v1/models`
   by hand), docs (ansible README `## Agent frontend (AG-UI)` l. 236–262, getting-started table l. 132, agent
   README `compaction` block), decision 13's model-backed check.
4. Then the previous handoff's step 2: local review round, squash-merge (sign-off address:
   `docs/knowledge/gh-squash-signoff.md`), plan row in `docs/README.md`, the track's line in `AGENTS.md`,
   parent pin, handoff to slice 1.
