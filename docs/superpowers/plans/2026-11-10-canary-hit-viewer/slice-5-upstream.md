# Slice 5/5: the port to upstream

Branch `impl/canary-hit-viewer-5-upstream`. Spec: all decisions, as ported; plan ruling 2 (what upstream gets).
Global constraints: [README](README.md#global-constraints). Steps: `docs/guides/contributing-upstream.md`.

Upstream (read 2026-11-10) has `platform/report/` (the service, its static files, `test_report.py`) and no
`platform/promptfoo-evals/metrics.py`, `handoff.py` or `spe_agent/airlock.py`: those are the canary ladder's,
which has its own upstream port (`BACKLOG.md` *Next*). So the hit viewer goes up as a **package** (the guide's
*Or port a package*): its final files from `origin/main`, without the ladder's files.

### Task 14: `contrib/canary-hit-viewer`

**Files (on the `contrib/` branch, from `origin/main`):**
- `platform/report/` (`canarymatch.py`, `canary_record.py`, `canary_hits.py`, `canary_reader.py`,
  `canary_watch.py`, `hits_view.py`, `sperange_report.py`, `static/hits.js`, `static/hits-admin.js`,
  `static/hits.css`, `README.md`, `tests/` with its fixtures)
- `platform/coder/deploy/sperange-canary-watch.service`, `sperange-report.service`, `report.env.example`,
  `platform/coder/README.md`, `platform/coder/template/main.tf`
- `docs/specs/2026-11-10-canary-hit-viewer.md`
- Not: `platform/promptfoo-evals/` and `platform/agui/pydantic-ai-agent/tests/test_airlock.py` (slice 1's
  changes there go up with the ladder's port), anything fork-only.

**On the fork (this slice's PR):** the plan's slices table (slice 5 done), `AGENTS.md` *Current work* (the
track's line removed; the upstream PR's line is added once it has a number, guide step 6), the `BACKLOG.md`
*Next* line for the ladder's upstream port (slice 1 rewrote it; adjust it only if the dependency changed, e.g.
this port merged first), the handoff.

- [ ] **Step 1: The worktree** from `upstream/main` (guide step 2), `git merge-base --is-ancestor upstream/main
  origin/main` (else merge upstream into our `main` first, its own unit), then take the files above with
  `git checkout origin/main -- <paths>` and commit with `-s`.
- [ ] **Step 2: Check the spec's upstream claims** on the branch: `platform/report/` imports nothing from
  `platform/promptfoo-evals/` (`grep -rn "promptfoo-evals\|import handoff\|import metrics" platform/report`:
  nothing); the spec and READMEs link nothing fork-only (guide step 4's grep). Fix what either finds in a commit of
  its own on the branch and, if the fork has the same text, in this slice's PR.
- [ ] **Step 3: Run** the fork-only check (`AGENTS.md`, *Contributing upstream*: `ok`), and the report suite
  (the only area with tests the package touches; `main.tf` gets `terraform fmt -check` where `terraform` is
  installed). Expected: PASS on upstream's code.
- [ ] **Step 4: Push** `git push -u origin contrib/canary-hit-viewer` (our fork, never `upstream`).
- [ ] **Step 5: The PR text** for the user, as an issue on our fork (guide step 5): what changes and why (the
  spec's *Problem* and *Decision*), how to try it (the watcher unit, the hits root, `--archive` on one run), what
  ran, and slice 3's and 4's screenshots from `pr-assets` (`canary-hit-viewer/<name>.png`), which show fixture
  tokens only. Opening the upstream PR is publishing: the user does it from the compare link; this slice
  does not wait for it.
- [ ] **Step 6: Commit** on this slice's branch: the slices table, *Current work*, the `BACKLOG.md` line, and the
  handoff (the track's last: `methodology next --end` after the merge).
