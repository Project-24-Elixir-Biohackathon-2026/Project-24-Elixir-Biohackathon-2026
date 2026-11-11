# 2026-11-11: experiments slice 3 (`spe-eval`, PR #88): task 7 done, review addressed; merge left

Mid-unit handoff (context budget). Same unit, same worktree:
`.claude/worktrees/impl-experiments-3-spe-eval`, branch `impl/experiments-3-spe-eval`, PR **#88** (still draft).

## Done this session

- **L3 measured**: run `20261111T085943Z`, both arms ok, controls "all 10 as expected"; the `--force-recreate` fix
  (`2bb3077`) verified (the mitigated arm ran, the return to the build's arm kept the `agent` alias).
  `hardening.json` L2-mitigated vs L3-baseline: equal except `experiment`, `restore_seconds` (ruling holds).
  Reports copied to the main checkout's `platform/ansible/output/denbi-agui-01/spe-eval/` (git-ignored).
- **Local review round** posted (issuecomment-6791735363); findings fixed `f26f102`, `a28765b`, `ab71580`,
  `large-slice` label created and added.
- **PR body rewritten** on the PR (rulings, *Why one unit*, task 7 tables, the three bugs). Missing: a
  `Checks:` line.
- **denbi-agui-01 restored** from main's `instances/denbi.yml`: destroy (needed `-e spe_runs_root=…`, note
  `03aead2`) ok, create ok=173 failed=0. Leftover `~/spe-eval` on the VM: BACKLOG `c6229b3`.
- Slice 4 handoff and *Current work* line: `22041dc`.
- **Merged `origin/main`** (`32de18b`, spec clarification 2: no contribution kinds; #89 `via: chat`) into the
  branch: `b761e96`, BACKLOG conflict resolved. **Suites not re-run after the merge.** Before it: dev 446
  passed, promptfoo-evals 459, validate OK, `methodology sync --check` 0.

## Next

1. Re-run after the merge: promptfoo-evals, dev `-k "spe_eval or spe_apply or local_vars"` (or the full ~6 min
   suite with nothing committing), `validate.py`, `methodology sync --check`. Check that #89's `via: chat` and
   slice 3's `run.sh`/`agent.yaml` changes agree, and that nothing on the branch says `--kind` or red/blue
   (another session's heads-up; a grep at `22041dc` found none).
2. Add the `Checks:` line to the PR body (what ran), `gh pr ready 88`, DCO green, squash-merge (forge sheet),
   clean up the worktree and branch, move the pin in `biohackathon`.
3. Short handoff on main naming `docs/handoffs/2026-11-11T1012Z-experiments-slice-4.md` plus the merge commit;
   `methodology next --unit impl/experiments-4-viewer <that handoff>`.
