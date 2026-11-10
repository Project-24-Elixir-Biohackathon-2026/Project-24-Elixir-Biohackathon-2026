# 2026-11-10: ladder replay built

Unit `change/ladder-replay`, fork PR **#83** (draft, label `change`), worktree
`.claude/worktrees/change-ladder-replay`. The user asked to rebuild the canary ladder's lost promptfoo results
so the team can view them in promptfoo, and to make sure promptfoo renders them.

**Why:** the ladder deleted `reports/` and `.promptfoo/` after each level, as `README.md` and spec part 06
say. The agent's run log `/var/lib/spe-agent/runs.jsonl` on `denbi-agui-01` (volume
`spe-frontend_agent-runs`, which `isolation.NOT_RESTORED` leaves alone) holds all 286 ladder runs (65+65+39×4,
all `completed`, 13 prompts per level). It is copied, with a matching sha256, to the main checkout's
`platform/ansible/output/denbi-agui-01/ladder-runs/runs.jsonl` (0600, git-ignored).

**Done (commit `8410eeb`):** `platform/promptfoo-evals/replay.py`.
- `build` splits the log into levels by each counts file's `started` and refuses on any per-test run-count
  mismatch or canary digest mismatch. It writes `<out>/<level>/{runs.jsonl,replay.yaml}`.
- The provider (`call_api`) returns the logged run by `vars.run_id`.
- `check` compares the re-scored `canary.answer`/`touched`/`sent` with `docs/results/qwen3.8-27b/L*.json`.
- Left out of the replay: `injection.followed`, `canary.delivered` and `reports_run_state` (they need the
  state diff), and `key.leak` (the log redacts the keys, and the LLM key is gone).

**Verified on the real data** (out dir `output/denbi-agui-01/ladder-runs/`, `PROMPTFOO_CONFIG_DIR=<out>/promptfoo`,
promptfoo 0.125.1):
- `build` gives the exact counts.
- `promptfoo eval` on each level exits 100 (failures are expected), with 0 errors.
- `check` prints `every level matches the committed canary.answer, canary.touched, canary.sent`.
- The pass/fail totals equal the original runs' (21/44, 23/42, 14/25, 13/26, 17/22, 14/25).
- `promptfoo view --port 15500` with that config dir lists all six evals; an eval page renders the
  prompts, answers, metric chips and reasons (Playwright screenshot, scratchpad only).
- To view: `cd platform/promptfoo-evals && PROMPTFOO_CONFIG_DIR=<main>/platform/ansible/output/denbi-agui-01/ladder-runs/promptfoo npx promptfoo view`.

**Left for this unit:**
1. `tests/test_replay.py`: synthetic log, counts and catalogue. Cover: build splits by window; a count
   mismatch and a digest mismatch are refused; `call_api` returns the run, and an error for an unknown id;
   `check` reports a difference. Run `uv run --group dev pytest -q`.
2. `README.md` (promptfoo-evals): a *Replaying the run log* section with the three commands above and the
   limits (three metrics not re-scored, the 16 KiB field cap: 567 of 5,310 tool fields carry `[truncated: …]`).
3. A knowledge note, `docs/knowledge/ladder-transcripts-in-run-log.md`, plus its index line: the reports are
   deleted, but `runs.jsonl` keeps every run; copy it before `destroy.yml`.
4. The PR body (plan, checks), mark it ready (GraphQL mutation, `docs/knowledge/gh-pr-create-token.md`), the
   local review round, merge with `gh api -X PUT …/pulls/83/merge`, cleanup, and move the pin in `biohackathon`.

**Context from the user, not part of this unit:**
- They decided canary values may be displayed to the team (per-instance, synthetic); the seed stays secret.
- They want the ladder's results viewable by the team: a shared promptfoo viewer on the portal, ladder levels
  as Coder presets, a trigger that runs `run.sh`. The suggested next step is a spec; nothing is recorded yet.
  Record it in `BACKLOG.md` *Next* in this PR.
