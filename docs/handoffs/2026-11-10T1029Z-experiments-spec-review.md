# 2026-11-10: experiments spec review

**Unit:** `spec/experiments`, fork PR #84 (draft, label `spec`), worktree `.claude/worktrees/spec-experiments`.
**Spec:** `docs/specs/2026-11-10-experiments-design/` (README first: decisions 1–21, early output).

## Where it stands

Written with the user in one long session (2026-11-10) and amended through it. The user's calls, each in a commit
message: no guard on paid models; a **new** Coder template `spe-experiments` (the existing `spe` unchanged, keep or
delete later); built for coding agents (part 07); no Run evaluation button (runs by `spe-eval run`); every run kept
(another session's commit `c065eb1`); a new experiment is written and run inside a workspace created from an
existing one (`ladder-l0`); no `coder` CLI path (participants work in their workspace); nothing a participant makes
is lost at stop (decision 21).

The builder check ran early (before the new template, part 07 and decisions 18–21); its findings are folded in.
**No review round yet.** The user has not approved.

## Next

1. Review round (`development-workflow.md`, *Review and merge*, *Local review*): reviewer subagents, at least the
   correctness focus (the spec against the code it cites: `platform/coder/`, `platform/instance/spe-apply`,
   `platform/promptfoo-evals/`, `platform/ansible/roles/{handoff,repo,run_archive}`, `platform/report/canary_*`)
   and the methodology focus (decisions each with a check that can fail, early output, no links to fork-only
   files since it is written for upstream, parts consistent after the many amendments). Post the findings on #84
   as one comment, address each.
2. Then ask the user to approve (the `approved` label; `methodology gate approve` fails on this token, see
   `docs/knowledge/gh-pr-create-token.md`: add the label with `gh api …/issues/84/labels`).
3. After approval: merge (squash, `gh api -X PUT …/pulls/84/merge`), clean up, move the pin in `biohackathon`,
   then the plan unit `plan/experiments`.

## Watch for

- Another session pushed to this branch during the conversation (`c065eb1`); fetch before working, rebase local
  commits, never force.
- The ladder (`run.sh`, `isolation.py`, `matrix.py`, the `spe_harden_*` switches) and the canary hit viewer are not
  upstream yet; the spec states that as a dependency (`inputs-for-plan.md`).
- `gh pr create`/`ready`/`merge` fail with "organization forbids access via a fine-grained personal access token";
  use `gh api` (`docs/knowledge/gh-pr-create-token.md`).
