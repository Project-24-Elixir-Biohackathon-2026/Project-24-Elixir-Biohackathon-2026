# 2026-11-10: experiments slice 2, mid-unit (context budget): local review round next

**Unit:** `impl/experiments-2-template`, fork PR #86 (`Experiments: the new template (2/7)`), **marked ready**.
Its body holds the task list, progress and every ruling; read it first. The SDD ledger is in this worktree's
git-ignored `.superpowers/sdd/slice-2-plan/` (`progress.md`, task reports and reviews, `final-review.md`).

## State

- Tasks 1–5 done and reviewed; whole-branch final review done and its findings fixed (88122fe, e067cd6,
  2fb7dc6). Slice 3's handoff, the *Current work* line and the knowledge note on building an arm without the
  portal: c7d064f. All pushed.
- Checks run on e35c344 (session 3): `validate.py` OK, `platform/dev/tests` 294 passed (tofu tests included),
  promptfoo-evals 407 passed; the fix agents later reported `platform/dev/tests` 309 passed at 2fb7dc6.
- **de.NBI `ladder-l2` build**: passed (session 3, at 2fb7dc6, `denbi-agui-01` rebuilt in place from the worktree as `docs/knowledge/experiment-arm-build-without-portal.md` says; first run stopped at `agui : LLM key present`, re-run with the key exported): ok=179 failed=0; `hardening.json` `level: 1`, `mitigations: [L1]`, `experiment: ladder-l2`, `injections: true`, `spe_harden_trs_readonly: true`. Put this in the PR body's checks.

## Next

1. **The local review round** (`development-workflow.md`, *Review and merge*, step 2, *Local review*): reviewer
   subagents on PR #86 with the correctness and methodology focuses (plus one on `sync-template.sh`, which runs on
   the portal VM), findings as one PR comment starting `Methodology <sha>`; address each (step 4), one reply
   comment.
2. **Before the merge** (AGENTS.md *Overrides*): DCO (every commit is signed off), the *Running things* test
   commands this slice touches run at the PR head (`validate.py`, `platform/dev/tests` with tofu on PATH,
   promptfoo-evals), `methodology sync --check`. `origin/main` moved on by docs commits: merges cleanly; diff with
   three dots. Write the `Checks:` line in the PR body.
3. **Merge** squashed with `gh api -X PUT repos/thodkatz/elixir-biohackathon-2026-test/pulls/86/merge -f
   merge_method=squash` (`gh pr merge` fails on this token), clean up the worktree (`--force`: it holds
   `.methodology/`; check `git status --porcelain` first), move the pin in `biohackathon`, write the short
   post-merge handoff naming `docs/handoffs/2026-11-10T1455Z-experiments-slice-3.md`, and
   `methodology next --unit impl/experiments-3-spe-eval <that handoff>`.

## Notes

- `methodology worktree --prune` and `gh pr ready` fail on this token: `docs/knowledge/gh-pr-create-token.md`.
- OpenTofu is at `~/.local/bin/tofu` (on PATH).
