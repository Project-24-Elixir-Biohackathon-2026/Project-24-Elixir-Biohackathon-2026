# 2026-11-11: experiments slice 7

**Track:** experiments. **Spec:** `docs/specs/2026-11-10-experiments-design/` (README: decisions 1–23; slices in
`inputs-for-plan.md`). No plan stage: each slice is one PR, `impl/experiments-<n>-<slug>`, titled `… (n/7)`, its
task list in the PR body, worked with `superpowers:subagent-driven-development`.
**Previous:** slice 6, **contribution** (fork PR #94):
- `check_experiment.py [<name>] [--json]` at the root: the experiment's structure, catalogue labels, injection
  entries (`select`'s shape, a `..` guard on `payload`) and leftover `TODO`s, as `file:line: id: what: do`;
- `experiments/TEMPLATE.yml`, `mitigations/TEMPLATE.yml`; every reader skips `TEMPLATE.*`;
- `spe-eval new <name> [--threat] [--path] [--injection <surface>] [--from <experiment>]` (every slot with
  `TODO`s), `spe-eval test [<name>]`, `spe-eval results [--run] [--json] [--test]` (verdict per metric over graded
  runs: closed, narrowed, unchanged, worse, no data), `spe-eval pr-body [<name>] [--run]` (`title: …` line, blank
  line, body);
- `.github/pull_request_template.md` (05's *The PR* block, with the reviewer items for a planting role and
  detector), `CONTRIBUTING.md`, the workspace guide's *Experiments* section (L1 as the worked mitigation),
  `experiments/README.md`'s *Adding one*.
- Its rulings (`spe-eval test` built here, `--path` prefills `tests` only, `--from` carries the build parameters)
  are in #94's body.

## Next

Slice 7, **proven with an agent** (decision 20). Branch `impl/experiments-7-proven-with-an-agent`. Scope:
`inputs-for-plan.md` row 7: a coding agent in a de.NBI workspace is given only "propose an attack and a mitigation
for TM-003 through P2 and measure it" and must reach a pushed `experiment/<name>` branch with `check_experiment.py
<name>` exiting 0 and a filled `spe-eval pr-body`; the reference answer is a TRS write guard against a new
injection whose action is a TRS write (so a new detector). What it stumbles on is fixed, or written into the
workspace guide's *Experiments* section. Acceptance: README decision 20.

Needs one de.NBI instance (standing OK, `AGENTS.md` *Setup*) and the portal or a workspace from the
`spe-experiments` template; the portal follows upstream, so check first what the workspace's clone carries (slice
6 is on our fork only until the port).

## Carried

- **gh on the org parent:** `gh pr create` fails (the org forbids the token); open the PR over REST and mark it
  ready over GraphQL (`docs/knowledge/gh-pr-create-token.md`). `methodology worktree --prune` cannot read the forge
  for the same reason and only prunes worktrees whose remote branch is gone.
- **Credentials:** if the VM has no working de.NBI LLM key, ask the user.
- Slice 6's open leftovers are in `BACKLOG.md` (the narrowed lint-gap item: the mitigation id pattern, the
  empty-fixture-list test).
