# 2026-11-03: conversation record plan, README done, write the four slice files

Continues `docs/handoffs/2026-11-03T1035Z-agui-conversation-record-plan.md`. Unit: `plan/agui-conversation-record`,
claimed as draft PR #20 (label `plan`), worktree `.claude/worktrees/plan-agui-conversation-record`.

## Done

- `f058c26`: the plan's [`README.md`](../README.md): order against compaction 2/3 (#18), rulings 1–5 (ruling 5
  answers inputs-for-plan bullet 4: the agent passes `context`/`state`/`forwardedProps` to pydantic-ai's
  `AGUIAdapter` untouched), Global Constraints, Shared interfaces, file structure, the 4-slice table, Review Focus,
  proposed clarifications. **It is the contract**: the slice files use its names.
- `7816bba`: `docs/README.md` indexes the plan; `AGENTS.md` *Current work* already points at slice 1 (rides in #20).
- The previous session dispatched four parallel writer subagents (one per slice file), then died past its
  budget. **None of the slice files was written.**

## Next

1. Write `slice-1-history.md`, `slice-2-export.md`, `slice-3-route.md` and `slice-4-live-archive.md`, one
   `general-purpose` subagent (opus) each, in parallel. Each prompt: read the README (contract; deviations go in a
   "Notes for the plan author" section at the file's end, not into the README), the spec parts the slice's row
   names (`docs/specs/2026-10-15-agui-frontend-design/`), the style precedent
   `docs/superpowers/plans/2026-11-03-agui-compaction/slice-2-chat-archive.md`, and the code it changes. TDD
   steps with full code, exact commands, `git commit -s`, no placeholders, no commits by the writer. Each
   slice's scope is its row and the README's *File structure*; the per-task split used last time:
   - slice 1: task 1 feasibility test (`lib/feasibility.test.ts` through `createCopilotRuntimeHandler`, test
     agent `echo-input`; failure ⇒ PR comment + `--end --blocked`), 2 `journal.ts`, 3 `rebuild.ts` (on
     `defaultApplyEvents`, `@ag-ui/client` 1.0.2 `dist/index.d.ts:616`; Review Focus 3, 4), 4 `anchor.ts`
     (Review Focus 1, 2; CopilotKit-shaped no-false-alarm fixture).
   - slice 2: step 0 checks #18 `MERGED`; 1 `lib/export.ts` with committed fixture bundles in
     `platform/dev/tests/fixtures/agui-record/` (`UPDATE_FIXTURES=1`), 2 `scripts/export-journals.ts` in the
     image (how standalone output gets `@ag-ui/client` + `rxjs` to the script, with a fallback), 3 `write_run.py`
     AG-UI rendering (Review Focus 5; Open WebUI output pinned byte-identical).
   - slice 3: 1 `Journals` + index, 2 recorder on journals (every check of decisions 1, 3, 4, 6–9, 24, 27),
     3 API/routes/shutdown, `SAVE_FAILED` gone, 4 archive export switch with the barrier kept,
     `write_agui_run.py` deleted, 5 `fake_agent.py` `echo-input`, check scripts and e2e on journals, docs, a
     clarification, early-output samples in `evidence/slice-3/`. Mid-slice handoff points after tasks 2 and 4.
   - slice 4: 1 `spe_archive_final` live/final, 2 Playwright (6, 13, 24–26), 3 key check (17), 4 TM-007 (18),
     5 dev VM acceptance (destroy only after the user's OK), spec marked built, track end.
   Facts from the archive side, read 2026-11-03: `export.yml` agui block l.42–139 (barrier l.68–116, `always`
   restart l.113), `write.yml` agui l.54–87, `archive.yml` l.78–94, `destroy.yml` l.11–12; `write_run.py`
   `main(argv)` takes `<bundle> <run dir> <report title>`, `active_branch`, `fence`, `render_message`;
   `test_write_agui_run.py` loads scripts by importlib; `e2e/sessions.py`, `check-built-server.mjs` and
   `check-shutdown.mjs` read `<id>.json`; Dockerfile is `node:24-slim`, standalone, `/data/sessions` created l.26.
2. Check each file for README consistency yourself with `grep` (interface names, no `TBD`/`similar to`), not by
   reading it whole; fold the writers' notes into the README.
3. Commit, mark #20 ready, local review round (correctness + methodology focuses), address, merge (squash, sign
   off as the GitHub author), clean up, move the pin in `biohackathon`, write slice 1's handoff in `handoffs/`,
   `next-session.sh --next impl/agui-conversation-record-1-history <handoff>`.
