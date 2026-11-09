# 2026-11-09: slice 6, address #65's review round (items 2–6), then merge

Read [2026-11-09T1316Z-slice-6-done.md](2026-11-09T1316Z-slice-6-done.md) for the slice itself (L1 built on
de.NBI, controls 10/10). This note covers only the review round, posted on #65 as comment 6741177935.

- **Item 1 fixed** in `e7f2f13` (guard refuses RFC 2231 `filename*` params; 208 tests pass). Not yet deployed to
  the VM: the VM runs `31dd547`'s guard. A redeploy is optional (WESkit reads only `workflow_attachment`, so it
  was not exploitable); if you rebuild, use the build command in the slice-6-done handoff.
- **Item 2, still to do (the important one):** add `spe_agent_tool_surface`, `spe_harden_trs_readonly`,
  `spe_harden_data_tiers`, `spe_harden_egress`, `spe_harden_airlock` (check names in `group_vars/all.yml`) to
  `spe_local_vars` in `platform/ansible/inventory/group_vars/all.yml`, with a test in
  `platform/dev/tests/test_harden_trs_readonly.py` (or `test_ladder.py`) that every `spe_harden_*` switch and
  `spe_agent_tool_surface` is listed; remove the `BACKLOG.md` item "Canary ladder: `spe_local_vars` lacks the
  `spe_harden_*` switches" (it waits for slice 6). Why: `remove_orphans: true` makes `spe-apply stack` on an L1
  VM drop `wes-guard` under a level-1 `hardening.json`.
- **Item 3:** plan `README.md` slice 5 row: `planned` → `merged #64 (\`d460cdf\`)`.
- **Item 4:** slice 6 row reads `merged #65`: push back (true once the squash lands, the only way the row reaches
  `main`), or set it to `merged #65 (\`<sha>\`)` in the after-merge handoff. Ruling is yours; record it in the reply.
- **Item 5:** `instances/L0.example.yml:2` and `L1.example.yml:3` cite `docs/superpowers/specs/…` (fork-only, the
  files go upstream). Replace with "(the canary evaluation ladder spec, parts 01 and 02)" without a path.
- **Item 6:** in the slice-6-done handoff *Rulings*, add *cost if wrong* to `\Z`, `engine-environment` (and its
  *why*: the value names a file sourced before the engine starts, so a client could run code) and the runbook.

Then reply on #65 in one comment, one line per item naming the commit; push; run the checks (*Overrides*: the
dev suite, `methodology sync --check`, DCO) and squash-merge with
`gh api -X PUT repos/thodkatz/elixir-biohackathon-2026-test/pulls/65/merge -f merge_method=squash`
(`gh pr merge` fails on the org token, `docs/knowledge/gh-pr-create-token.md`). Then the usual cleanup, the pin
in `biohackathon`, and the after-merge handoff that chains to slice 7.

Use `GH_REPO=thodkatz/elixir-biohackathon-2026-test` for any `gh pr`/`methodology gate` command (same note).
