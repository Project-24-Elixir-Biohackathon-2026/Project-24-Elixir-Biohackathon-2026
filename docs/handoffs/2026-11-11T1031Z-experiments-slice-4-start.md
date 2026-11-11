# 2026-11-11: experiments slice 4: start

Slice 3 (`spe-eval`, PR #88) is merged: squash commit `377365c`. Start slice 4/7 (the viewer and apps) on
branch `impl/experiments-4-viewer` from **`docs/handoffs/2026-11-11T1012Z-experiments-slice-4.md`**, which has
the unit's context; read it after this one.

What only the merge settled:

- **Review round**: local, one round (PR #88, issuecomment-6791735363); every finding fixed on the branch before
  the merge (`f26f102`, `a28765b`, `ab71580`). The PR carried `large-slice`.
- **Checks after merging `origin/main` (incl. #89, `via: chat`)**: `validate.py` OK, `platform/dev/tests` 446
  passed, `platform/promptfoo-evals` 471 passed, `methodology sync --check` 0, DCO green. #89's provider defaults
  to `via: agent` and `agent.yaml` does not set it, so `spe-eval`'s runs are unchanged; a later slice that wants
  the chat path through `spe-eval` sets `SPE_AGENT_VIA=chat` in `spe_eval.promptfoo_env` (the tunnel's
  `127.0.0.1:3000` default holds on the VM).
- **denbi-agui-01** is back on main's `instances/denbi.yml`; a leftover `~/spe-eval` on it is BACKLOG (`c6229b3`).
