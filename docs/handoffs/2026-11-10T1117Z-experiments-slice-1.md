# 2026-11-10: experiments slice 1

**Track:** experiments. **Spec:** `docs/specs/2026-11-10-experiments-design/` (README: decisions 1–23; slices in
`inputs-for-plan.md`). Merged as `c5107e3` (fork PR #84, squash).
**Previous:** `docs/handoffs/2026-11-10T1040Z-experiments-spec-approval.md` (now stale: the gate it waited on is
closed).

## What the merge settled

- **Approved by the user** in the session ("okey lets approve and start implemneting right away"); the agent added
  `approved` at their word (`methodology gate approve` refuses in an unattended-mode session), recorded on #84.
- **No plan stage, at the user's word.** Ruling, for the user to overrule: each slice of `inputs-for-plan.md` is
  one implementation PR, `impl/experiments-<n>-<slug>`, titled `… (n/7)`; its PR body carries its task list (what a
  plan task would have said) and names this ruling. Work each slice with `superpowers:subagent-driven-development`
  from that task list.
- After the review round, the user's questions in the session added: one owner per Ansible key (decision 4);
  how a participant plants an attack, including a new surface and a new action with its detector, and what of the
  injection schema stays fixed (decision 23, part 01 *Attacks*); the live-apply tag rule for mitigations; the
  ladder as regression (decision 5) and an agent proof that proposes an attack too (decision 20).
- **How it is tested end to end:** offline checks every slice; the ladder experiments as regression from slice 3
  (closed probes exact, agent counts same direction as `docs/results/`); slice 7's TRS guard against a new
  injection for what the ladder cannot exercise.

## Next

Slice 1, **the catalogue as files** (decisions 2, 3, 4, 23), branch `impl/experiments-1-catalogue`, no instance:

- `paths/` (P1–P4 from part 06's table, `paths/TEMPLATE.md`), `mitigations/` (L1–L3, L4–L5 `status: planned`),
  `validate.py` over threats, paths and mitigations (including one owner per Ansible key, `off` equal to
  `group_vars/all.yml`), `matrix.CATALOGUE` built from the files, `tests/experiments/`, `injections` in the
  experiment block;
- `drs_register` and `trs_install` plant every catalogue entry whose switch is on (today: first entry per
  surface, three switches by name); `injections_schema.py` reads ids, surfaces (a `surfaces` map beside
  `fixtures.json`) and actions (the detectors in `metrics.py`) instead of listing them.
- Acceptance: decisions 2, 3, 4 and 23's checks that need no instance; `matrix.py counts` on committed ladder
  results unchanged; the test commands in AGENTS.md *Running things* (validate, promptfoo-evals, platform/dev).

## Watch for

- `gh pr merge` and `methodology gate approve` fail on this token: merge with
  `gh api -X PUT repos/thodkatz/elixir-biohackathon-2026-test/pulls/<n>/merge -f merge_method=squash`
  (`docs/knowledge/gh-pr-create-token.md`).
- `methodology sync --check` notes AGENTS.md's blocks lag the template by 3 commits (`methodology update`); not
  this track's work.
