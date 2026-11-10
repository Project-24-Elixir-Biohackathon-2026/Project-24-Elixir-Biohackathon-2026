# 2026-11-10: slice 4 fix wave done

Slice 4/5 (`impl/canary-hit-viewer-4-admin-page`, draft PR **#80**, opened by REST: `gh pr create` fails on the
org's token rule, `docs/knowledge/gh-pr-create-token.md`). Tasks 12–13 are implemented, each passed its task review,
and the final whole-branch review (correctness, opus) ran; its fix wave is `c6967e1`. Handed off at the context
budget. **Next: finish the unit**, nothing more to build.

**On the branch** (pushed): `20ab54c` admin page, `hits.json`, stream, `hits-admin.js`; `f311ca6` task-review fixes
(one bad file dropped from the admin stream, reload at most once a minute, admin order by `detected`); `e275b03`
admin link on `/reports/`, READMEs, screenshot `evidence/slice-4/admin-page.png`; `c3391e1` rulings 27–33 in
[progress.md](../progress.md), slices table (`done (#80)`), *Current work* line; `c6967e1` final-review fixes (an
unreadable hits file no longer fails the admin page or `hits.json`; a failed first scan no longer replays every
file; "Newest (detected)" column; the Watcher cell wraps, screenshot retaken; four `BACKLOG.md` lines). Report
suite: 246 passed.

**To do, in order:**
1. A scoped re-review of the fix wave, `c3391e1..c6967e1`, against the final review's findings: Important 1
   (`read_all` crashed the admin page and `hits.json` on an unreadable file), and minors 2 (failed first scan
   replays), 3 (column label), triple blank line, table overflow. The full findings text is in the SDD ledger,
   `.superpowers/sdd/slice-4-admin-page/progress.md` (git-ignored, in this worktree), and the implementer's
   report `task-12-report.md` beside it ("Final review fix wave").
2. The PR's local review round (`development-workflow.md`, *Review and merge*): the final whole-branch review
   above is the **correctness** focus (post its findings and the fix commit); still to run: the **methodology**
   focus. Post both as one comment starting `Methodology <sha>`; reply with one line per finding.
3. PR title `Canary hit viewer: admin page, its stream and filters (4/5)`, body with the screenshot, rulings
   27–33, the checks run; mark ready by the GraphQL mutation (`gh-pr-create-token.md`); checks (*Overrides*): the
   report suite, `methodology sync --check`, sign-offs; squash-merge; clean up; pin in `biohackathon`; the
   merged handoff on `main`, then `methodology next --unit impl/canary-hit-viewer-5-upstream <handoff>`.

**Rulings made in this session** (beyond 27–33 in progress.md): the final review's leave-alone triage, now in
`BACKLOG.md` *Unscheduled* (render→stream gap, silent stop after a non-200 stream, full parse per load and 0.5 s
rescans, serial Coder lookups); a deleted workspace's row keeps the UUID as its name; the widened logged-out check
(`endswith("hits.json")`) stays (only 401 vs redirect on non-routes).
