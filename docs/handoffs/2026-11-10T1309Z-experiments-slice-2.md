# 2026-11-10: experiments slice 2

**Track:** experiments. **Spec:** `docs/specs/2026-11-10-experiments-design/` (README: decisions 1–23; slices in
`inputs-for-plan.md`). No plan stage (the user's word, ruling in
`docs/handoffs/2026-11-10T1117Z-experiments-slice-1.md`): each slice is one PR, `impl/experiments-<n>-<slug>`,
titled `… (n/7)`, its task list in the PR body, worked with `superpowers:subagent-driven-development`.
**Previous:** slice 1, *the catalogue as files* (fork PR #85): `paths/`, `mitigations/`, `validate.py` over all
three, `matrix.CATALOGUE` and the injection catalogue read from files, every fixture whose switch is on planted.

## Next

Slice 2, **the new template** (decisions 1, 5, 6), branch `impl/experiments-2-template`, one de.NBI build (the
`ladder-l2` preset: level 1; the standing OK covers one instance at a time):

- `spe-experiments` Coder template with `experiment` and `mitigations` parameters; the sync
  (`platform/coder/deploy/sync-template.sh`) assembling and pushing it, and `experiment/<name>` branches;
- the experiment's and mitigations' vars merged into `ansible_vars` (one owner per key, decision 4, already
  linted by `validate.py`); `spe_experiments` gating; `requires`/`conflicts` checked in `create.yml`;
- `hardening.json` gains `mitigations`;
- the ladder levels as experiment files (an experiment's own tests go in `tests/experiments/`, empty so far).
- Acceptance: decisions 1, 5, 6's checks; the *Running things* test commands; the de.NBI build of `ladder-l2`.

## Carried from slice 1 (rulings on #85)

- Two questions for this slice, in `inputs-for-plan.md`, *For the plan to settle*: where an experiment's
  `injections` ids map to `spe_inject_*` values, and `hardening.json`'s `injections` beside `mitigations`.
- Fixture and mitigation lint gaps wait for slice 6 (`BACKLOG.md`, *Unscheduled*).

## Watch for

- `gh pr create`, `gh pr ready`, `gh pr merge` fail on this token: REST and the GraphQL ready mutation in
  `docs/knowledge/gh-pr-create-token.md`; prefix `GH_REPO=thodkatz/elixir-biohackathon-2026-test` for
  `methodology` commands that call `gh`.
- The portal follows upstream: the template reaches participants only through an upstream port, after the ladder's
  (`inputs-for-plan.md`, *Dependencies*). A `template/<name>` branch for trying it needs upstream push.
