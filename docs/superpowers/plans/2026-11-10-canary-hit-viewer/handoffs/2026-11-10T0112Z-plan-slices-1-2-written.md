# 2026-11-10: plan: index and slices 1–2 written, slices 3–5 to write


**Unit:** the plan, branch `plan/canary-hit-viewer`, draft PR #75 (opened this session by REST; label `plan`).
Mid-unit handoff at the context budget.

**Done (committed on the branch):**
- Spec clarification 1, folded (`2b811df`): Open WebUI's chats are a source. Verified in code
  (`roles/openwebui/templates/webui.env.j2`: Open WebUI calls `spe_llm_base_url` and the sandbox itself) and on the
  portal's archive (`ssh agent-service-1`, 50 runs, read-only probe, no values printed): 18 Open WebUI chats with
  tool calls in each assistant message's `output` (`function_call`, `function_call_output`), none in
  `agent-runs.jsonl`. Asked for by the user, relayed by peer session `elixir-biohackathon-2026-test-b6`.
- Also verified for the spec's *Inputs for the plan*: real journal event types (`TOOL_CALL_*`, `TEXT_MESSAGE_*`,
  `REASONING_*`, `RUN_*`); the Coder template sets no age recipient; the portal's archive is readable over
  `ssh agent-service-1` with passwordless `sudo` (the early output can run from here).
- Plan index `README.md` (rulings 1–6, constraints, file structure, 5 slices, Review Focus), `slice-1-match-archive.md`
  (Tasks 1–4), `slice-2-watcher.md` (Tasks 5–8).

**Next, in this unit:**
1. Write `slice-3-participant-page.md` (Tasks 9–11), `slice-4-admin-page.md` (Tasks 12–13),
   `slice-5-upstream.md` (Task 14), matching the README's slices table and Review Focus lines 1 and 5
   (`test_page_escapes_titles_and_excerpts`, `test_events_resume_past_end`, `test_events_before_file_exists` in
   Task 10). Facts gathered for them: `sperange_report.py` has `Coder.me`, `Coder.workspace_state(token, wid)`,
   `is_admin(user)` (role `owner`), `Handler.can_edit` (owner = sidecar `owner` == `username`), `page(title, body,
   user)`, CSP with no inline script (`static/`); the Report app is `coder_app "report"` in
   `platform/coder/template/main.tf:275` (the new one: slug `hits`, "Canary hits", `external = true`, URL
   `<access_url>/reports/<id>/hits`). Slice 3 holds decisions 6, 8 (10 s latency test with the fake instance), 10
   (no route takes a token; service logs), 11; slice 4 decision 7. Slice 5: `contrib/canary-hit-viewer` per
   `docs/guides/contributing-upstream.md`, the user opens the upstream PR (publishing); it also removes the
   track's *Current work* line.
2. Self-review the plan (writing-plans skill), update `AGENTS.md` *Current work* (next: slice 1
   `impl/canary-hit-viewer-1-match-archive`), add `docs/README.md` index line for the plan if that index lists
   plans, write the unit's end handoff, PR body, local review (correctness + methodology), merge by REST
   (`docs/knowledge/gh-pr-create-token.md`), cleanup, move the `biohackathon` pin.
3. Reply to the peer session (`elixir-biohackathon-2026-test-b6`) that Open WebUI is in (clarification 1 and
   the plan's ruling 1), if it is still reachable; it was not answered in this session.

**Resume:** `cd /workspace/biohackathon/elixir-biohackathon-2026-test/.claude/worktrees/plan-canary-hit-viewer`,
`git log --oneline -4` shows this handoff on top of the plan commit and `2b811df`.
