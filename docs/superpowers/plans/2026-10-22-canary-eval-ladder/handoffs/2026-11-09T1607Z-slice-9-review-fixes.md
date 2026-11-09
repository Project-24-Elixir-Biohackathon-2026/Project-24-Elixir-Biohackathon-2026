# 2026-11-09: slice 9, address the review round, then merge (mid-unit, context budget)

Slice 9 is built, live-checked and ready on PR #69 (`acfdf9d`, pushed); read
[2026-11-09T1602Z-slice-9-done.md](2026-11-09T1602Z-slice-9-done.md) for what it built and ran. The one local
review round ran and is posted as PR comment **6744845722** (10 numbered items). No second round. Left: fix,
reply, merge, clean up, chain.

## Rulings on the findings (decided; do them)

- **1 (Important, ReDoS in `sensitive_path`)**: fix as suggested, the `(?<![\w./-])` lookbehind; add a test that
  100k `ACGT` redacts in under 1 s.
- **2 (Important, Markdown credential pairs)**: fix: allow `` ` ``/`*`/quote decoration around the name and before
  the value, `|` as a separator, a quoted value up to its closing quote; add the reviewer's four cases and the
  `CLIENT_SECRET: "two words"` case to `test_redacts_each_class`. Keep every existing test passing.
- **3 (`STUDY-0042_R1`)**: fix, lookahead `(?![0-9A-Za-z])`; add the case.
- **4 (bare tier dir, `sensitive/genomes`)**: fix both (`/data-share/sensitive` followed by `/` or a word end;
  `genomes` added to the relative form); add cases.
- **5 (lowercase `*_key` redacted)**: keep case-insensitive (an `api_key=` leak matters more than a changed
  `cache_key` line); say so in the agent README's *Airlock (L5)* paragraph. Cost if wrong: benign schema/code
  answers show a redacted value.
- **6**: README names compaction summaries as unfiltered too.
- **7 (probe hard-codes `STUDY-0001`)**: `BACKLOG.md` line (probe should build the id from
  `$SPE_STUDY_ID_PREFIX`); not this slice.
- **8**: add the two-message test (text, tool call, answer: each CONTENT between its own START/END, the first
  before `TOOL_CALL_START`).
- **9 (key gate stale)**: `BACKLOG.md` *Next* says the de.NBI key is in reach (`d8a5c1b`). Reword the
  `AGENTS.md` *Current work* line and the slice-9-done handoff's *Next* (it is this PR's own, not yet merged
  history): slice 10 runs once its key gate passes; the key is in reach (`BACKLOG.md` *Next*).
- **10 (lesson only in the ledger)**: add `docs/knowledge/` note + index line: an implementer subagent dispatched
  from a unit worktree committed in the main checkout (`ee378e3` on local `main`; moved by cherry-pick to
  `fdcca13` and `git -C <main> reset --keep 138f791`); a dispatch must name the worktree's absolute path for every
  command and check `git branch --show-current` before committing. Link it from the done handoff.

Fixes 1–4 and 8 are code: one fix subagent (Sonnet) with the list, telling it to work only in this worktree;
then a scoped re-review. Agent tests: `(cd platform/agui/pydantic-ai-agent && uv run --group dev pytest -q)`.
The regex change does not need a new de.NBI run (the probe's text stays covered by the unit tests); say so in the
PR reply.

## Then

Reply on #69 in one comment, one line per item with its fixing commit. Before merging: DCO, the test commands
above plus `platform/dev/tests` (needs `--with mkdocs-material --with jinja2`) and promptfoo-evals, `methodology
sync --check`. Merge squashed (`gh pr merge` fails on the org-token rule: use the REST merge,
`docs/knowledge/gh-pr-create-token.md`), clean up the worktree, move the pin in `biohackathon`, write the short
post-merge handoff and chain to slice 10 (`methodology next --unit impl/canary-eval-ladder-10-agent-runs …`).

The SDD ledger is `.superpowers/sdd/slice-9-airlock/progress.md` (git-ignored, in this worktree), with both
review files beside it.
