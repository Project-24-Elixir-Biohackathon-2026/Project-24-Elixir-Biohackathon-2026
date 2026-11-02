# Upstream ports

Which fork commits with project changes have been decided for upstream (`kraatz/elixir-biohackathon-2026-test`):
ported in an upstream PR, or not for upstream and why. Fork-only: upstream's history carries no fork hashes.
The procedure that reads and writes it: `docs/guides/contributing-upstream.md`.

One line per fork commit (the squash commit of a fork PR), oldest first, its sha abbreviated to 7 characters
(`git log --abbrev=7`, as the guide's step 1 prints it):

    - `<short sha>` <fork subject> → kraatz #<n> (open | merged | closed: <why>)
    - `<short sha>` <fork subject> → not for upstream: <why>

A fork commit with no line here is still a candidate (the guide's step 1). Lines are not pruned, since a removed
line puts its commit back on the candidate list; the one deletion is a `closed` line removed on purpose to offer
its commit again (the guide's step 7).

- `c21f954` Spec: the canary evaluation ladder (draft) → not for upstream: its only shared file is the fork's `CLAUDE.md`
- `77cf95f` Make AGENTS.md the fork's single entry point; drop CLAUDE.md → not for upstream: fork entry point
- `bc5d944` AG-UI agent: per-run token cap optional, off by default (#4) → kraatz #9 (open)
