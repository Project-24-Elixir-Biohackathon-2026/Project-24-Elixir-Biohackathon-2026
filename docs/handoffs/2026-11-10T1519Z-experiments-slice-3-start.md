# 2026-11-10: experiments slice 3 start (`spe-eval`), after slice 2 merged

Read **`docs/handoffs/2026-11-10T1455Z-experiments-slice-3.md`** (on `main` now): the slice's scope and what it
carries from slice 2. This file adds only what the merge settled.

- **Slice 2 merged**: fork PR #86, squash `75997e4`. One local review round (correctness, methodology,
  `sync-template.sh`): 11 findings, all fixed or answered on the PR. Worktree and branch removed.
- **The injections item is now a slice-3 input**: `docs/specs/2026-11-10-experiments-design/inputs-for-plan.md`
  ("Slice 3, from slices 1–2"): the Python mapping of injection ids for `spe-eval`, and whether
  `hardening.json`'s `injections` "mixed" needs changing once `run.sh`/`spe-eval` read the arms.
- **#87 (contribution kinds) merged before slice 2**: an experiment's `tests` may name any catalogue test id, and
  `spe-eval` builds the arm's suite from the files those ids are in (spec 01, *Tests*). Read 01's changed
  section before designing the suite config.
- Verified during the review: `coder templates push` (v2.38.6, `provisionersdk.Tar`) does not read `.gitignore`,
  so the assembled, git-ignored copies in `experiments-template/` are pushed.
