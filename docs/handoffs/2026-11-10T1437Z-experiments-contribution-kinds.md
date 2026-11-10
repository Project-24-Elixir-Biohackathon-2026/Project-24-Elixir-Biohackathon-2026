# 2026-11-10: experiments spec, contribution kinds (PR #87)

**Unit:** `spec/experiments-contribution-kinds`, draft PR #87 on the fork, worktree
`.claude/worktrees/spec-experiments-contribution-kinds`. Amends the merged experiments spec
(`docs/specs/2026-11-10-experiments-design/`) with clarification 1: a contribution is red (attack, `mitigation:
null`, harm shown on a named base), blue (mitigation measured against attacks on `main`), end-to-end, or other;
a new threat or path comes only with an attack; `check_experiment.py` reads the kind from the files against
`--base`; one PR template per kind, opened through `spe-eval pr-body`'s link (GitHub has no PR template picker);
labels added by the reviewer until CI exists. The user decided each of these in session (2026-11-10). Commit
`f7c1520`; it also removed the folded `BACKLOG.md` item (template's attack line and rationale).

## Next

1. **Local review round** (correctness and methodology focuses) on PR #87: not run, the session hit its budget.
   Address findings, then mark ready.
2. **The user's `approved`** on #87 (a spec gate), then merge (squash, signed off), clean up, move the pin in
   `biohackathon`.
3. Slice 6 (contribution) builds it, in the track's order; nothing built so far changes. Slice 2 (PR #86) is in
   progress; #87 touches `README.md` and `inputs-for-plan.md` of the spec, so rebase if #86 merges first and
   conflicts.

## Watch for

- Untried: whether GitHub applies `.github/pull_request_template.md` beside `.github/PULL_REQUEST_TEMPLATE/`;
  05 says slice 6 checks it, with `CONTRIBUTING.md`'s links as the fallback.
- `gh pr create` fails on the org token check (`repository.parent`); open and label PRs with
  `gh api -X POST repos/thodkatz/elixir-biohackathon-2026-test/pulls …` (`docs/knowledge/gh-pr-create-token.md`).
