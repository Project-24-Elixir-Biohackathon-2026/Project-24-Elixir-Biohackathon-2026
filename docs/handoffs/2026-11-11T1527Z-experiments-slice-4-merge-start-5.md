# 2026-11-11: experiments slice 4 merged; start slice 5

Slice 4 (the viewer and apps, PR #92) is merged: squash commit `42e25ee`. Start slice 5/7 (eval runs apart in
canary hits) on branch `impl/experiments-5-canary-source` from
**`docs/handoffs/2026-11-11T1513Z-experiments-slice-5.md`**, which has the unit's context. Read it after this one.

What only the merge settled:

- **Review round:** local, one round: PR #92, issuecomment-6799710984, reply issuecomment-6799730095.
  - Correctness ran on opus, methodology on sonnet.
  - Every finding was fixed before the merge (`46d816c`, `8b3e8a5`, `695fc29`) or recorded in the PR body.
  - Two items went to `BACKLOG.md`, *Unscheduled*: decision 16's live check, and the viewer's egress.
- **Checks at `8b3e8a5`:**
  - `validate.py` OK;
  - `platform/dev/tests`: 553 passed, 1 skipped;
  - `platform/promptfoo-evals`: 471 passed;
  - `methodology sync --check` 0;
  - DCO pass.
- **denbi-agui-01** is back on main's `instances/denbi.yml`, and the `/etc/hosts` DNS pin is removed. Its resolver
  may still time out on `*.ubuntu.com` (`docs/knowledge/denbi-apt-dns.md`).
- **A slip in the merge commit:** `42e25ee`'s squash body was written by hand. It signs off as `theo
  <theoclaude2@pm.me>`, not the repo's `thodkatz@pm.me`, and it does not carry each commit's trailers, as earlier
  squashes did. `main` is not rewritten. For the next merge, keep GitHub's default squash body (`gh pr merge
  --squash` without `--body`), or sign off with `git config user.email`.
