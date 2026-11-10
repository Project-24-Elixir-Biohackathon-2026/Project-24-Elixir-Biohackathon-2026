# 2026-11-10: experiments slice 1, all tasks done, PR ready next

**Track:** experiments, slice 1/7 (the catalogue as files), branch `impl/experiments-1-catalogue`, draft PR #85.
**Previous:** `docs/handoffs/2026-11-10T1135Z-experiments-slice-1-task-1-review.md`; the slice's scope:
`docs/handoffs/2026-11-10T1117Z-experiments-slice-1.md`. Handed off at the context budget, mid-unit.

## Where it stands

- **All four tasks are implemented and reviewed** (SDD, ledger in this worktree's git-ignored
  `.superpowers/sdd/slice-1-plan/progress.md`), all pushed:
  - Task 1, paths and mitigations: `f15e79e`, `b2bec29`. Review clean.
  - Task 2, `matrix.CATALOGUE` from files: `0e41e9c`. Review clean.
  - Task 3, injection catalogue read from files: `79a81c2`. Review clean.
  - Task 4, plant every fixture whose switch is on: `1c18870`, plus `597405c` for fix round 1 (an undefined
    switch broke the `repo` role).
- **Whole-branch review** (opus): ready with fixes. One fix wave, `3c57de3..0917c8a`, covered seven findings:
  - stale `AGENTS.md` rows;
  - the `switches()` test now runs on the real catalogue;
  - only fixture switches default to false in the `repo` role;
  - an overlap is exempt when the pair declares `conflicts` (spec 01);
  - `check_fixtures` runs before `validate` in the CLI;
  - two stale or missing script tests.
  The scoped re-review found all seven addressed and nothing new broken.
- **Checks last run** (re-review, on `0917c8a`):
  - `uv run --with pyyaml python validate.py`: OK, 5 threats, 4 paths, 5 mitigations.
  - `platform/dev/tests`: 245 passed.
  - `promptfoo-evals`: 407 passed.
  - `ansible-playbook --syntax-check`: clean.
  - `matrix.py render docs/results/qwen3.8-27b/*.json`: identical to `docs/results/canary-ladder-qwen3.8-27b.md`.

## Rulings (go in PR #85's body, for the user to overrule)

1. **The experiment block's `injections` is `injections_schema.switches(ids)` in slice 1.** Experiment files come
   in slice 2 and the checker in slice 6. Cost if wrong: slice 2 adds the mapping in Terraform anyway.
2. **`hardening.json`'s `injections` stays true/false/"mixed" over all fixtures.** Cost if wrong: one line in
   `hardening.yml`. Slice 2 revisits it (`mitigations`).
3. **`check_fixtures` does not check `select`'s shape yet; slice 6's checker does.** Cost if wrong: a bad new
   fixture fails late, as a Jinja error at build.
4. **These minors stay deferred, with the final review's agreement** (lint robustness only):
   - the mitigation id pattern accepts lowercase `l<n>`;
   - `check_fixtures` checks types after testing set membership, and has no `..` guard on `payload`;
   - the new-surface test has no `check_fixtures` assert;
   - `injections_manifest.py` uses `p.get("id")`;
   - an empty fixture list is untested in the `repo` role;
   - `check_mitigations_catalog` keeps only the first owner of each key.

   **Land them durably.** Add one `BACKLOG.md` item, "fixture and mitigation lint gaps for slice 6's checker",
   listing ruling 3's and this item's points. Commit it in this PR.

## Next

1. **Re-read PR #85's comments** (none as of 13:04Z):
   `gh api repos/thodkatz/elixir-biohackathon-2026-test/issues/85/comments`.
2. **Commit to the branch:**
   - the `BACKLOG.md` item above;
   - `AGENTS.md` *Current work*: the experiments line says next is slice 2/7, naming its handoff.
   - The slice handoff for slice 2. Its scope is in `docs/specs/2026-11-10-experiments-design/inputs-for-plan.md`,
     row 2.
3. **Edit the PR body.** Start from `.superpowers/sdd/slice-1-plan/pr-body.md`:
   - replace "Work in progress" with the status above;
   - list the rulings and the checks run;
   - footer `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

   Then mark the PR ready. `gh pr ready` and `gh pr create` fail on the org token
   (`docs/knowledge/gh-pr-create-token.md`), so use REST:
   `gh api -X PATCH repos/thodkatz/elixir-biohackathon-2026-test/pulls/85 -F body=@<file>`. For ready, follow
   that note.
4. **Run the local review round** (`AGENTS.md` *Reviewers*). Dispatch at least two focuses, correctness and
   methodology (`development-workflow.md`, *Review and merge*, step 2). Post one comment that starts with
   `Methodology <sha>`, address the findings, and reply in one comment.
5. **Merge once the *Overrides* checks pass:** DCO, the tests above, and `methodology sync --check`. Merge with
   `gh api -X PUT repos/thodkatz/elixir-biohackathon-2026-test/pulls/85/merge -f merge_method=squash`.
6. **After the merge:**
   - clean up per step 7, using `git worktree remove --force` after checking `git status --porcelain`;
   - `rm -rf .superpowers/sdd/slice-1-plan` goes with the worktree;
   - pin the merge in `biohackathon` (its `AGENTS.md`);
   - write the short post-merge handoff, then
     `methodology next --unit impl/experiments-2-<slug> <handoff>`.
