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
- `bc5d944` AG-UI agent: per-run token cap optional, off by default (#4) → kraatz #17 (open; first kraatz #9, closed in favour of #17)
- `33774a6` AG-UI chat sessions: the store (1/3) (#9) → kraatz #17 (open)
- `cf3160c` Ignore __pycache__ under platform/dev → kraatz #17 (open)
- `b2b328b` Untrack a compiled test module committed by mistake → kraatz #17 (open)
- `b3ce239` Untrack the remaining compiled test modules → kraatz #17 (open)
- `bb7eef7` AG-UI chat sessions: sidebar, row menu, archive export (2/3) (#10) → kraatz #17 (open)
- `e525b0d` AG-UI chat sessions: complete (3/3) (#11) → kraatz #17 (open)
- `4157add` AG-UI chat minors (#14) → kraatz #17 (open)
- `050ee0f` Agent compacts the conversation (1/3) (#17) → kraatz #17 (open)
- `0337a7c` Spec: one living AG-UI spec, with the conversation record (#19) → kraatz #17 (open)
- `c8d1b46` Spec: the AG-UI archive copies live, only the final archive stops → kraatz #17 (open)
- `4f306cb` Chat and archive show a compaction (2/3) (#18) → kraatz #17 (open)
- `2eeb760` Plan: AG-UI conversation record (#20) → kraatz #17 (open)
- `81a35d0` AG-UI record: feasibility check, journal, rebuild, anchor (1/4) (#22) → kraatz #17 (open)
- `4c8fb78` AG-UI record: exporter in the image, write_run.py renders AG-UI chats (2/4) (#23) → kraatz #17 (open)
- `200e07e` The record on journals: store, run route, API and archive (3/4) (#24) → kraatz #17 (open)
- `ec1fc32` de.NBI window, docs, decision 13 (3/3) (#21) → kraatz #17 (open)
- `3e44059` Spec: /compact in the AG-UI chat (#26) → kraatz #17 (open)
- `008fa47` Live archive, final barrier, instance checks, record built (4/4) (#25) → kraatz #17 (open)
- `7850489` AG-UI /compact: the agent (1/2) (#28) → kraatz #17 (open)
- `041a095` AG-UI chat: model-written titles, resizable sidebar, theme toggle (#29) → kraatz #17 (open)
- `41eb5f4` AG-UI chat: tool-call cards after Open WebUI's ToolCallDisplay (#31) → kraatz #17 (open)
- `8ac8da2` AG-UI /compact: the chat (2/2) (#30) → kraatz #17 (open)
- `4c768b9` AG-UI chat: /compact in the slash menu, input marked as a command (#32) → kraatz #17 (open)
- `174062e` AG-UI agent: title.max_tokens 64 -> 1024 for reasoning models (#33) → kraatz #17 (open)
- `a25ce09` Merge upstream/main (2026-11-04): clone-on-VM layout, threat format, site → kraatz #17 (open)
- `9cf1f09` Review #35 (methodology): stale spec, README and plan references after the merge → kraatz #17 (open)
- `d6586f9` Review #35 (correctness): ui-dev archive refused clearly, our agent vars re-applied, fork repo URL → kraatz #17 (open)
- `0e00677` AG-UI chat: tool cards worded as Open WebUI, theme toggle top right (#34) → kraatz #17 (open)
- `49a2c58` Merge remote-tracking branch 'origin/main' into change/merge-upstream-2026-11-04 → kraatz #17 (open)
- `52cdc2c` repo role: don't clone the fork's private submodule on the instance (#37) → kraatz #17 (open)
- `36bb78c` Merge upstream/main: both chat frontends on every instance (kraatz #15, #16) → kraatz #17 (open)
- `d0b9742` Archive export test: pass spe_frontends, the variable's current name → kraatz #17 (open)
- `bf458b7` Address #39's methodology review: stale docs after the both-frontends merge → kraatz #17 (open)
- `27076fd` Address #39's correctness review: re-rendering a both-frontends run → kraatz #17 (open)
- `d03751c` Reset an existing host's frontend through its compose link (#41) → kraatz #17 (open)
- `9abdbb9` Contributing guide: the package port path; spec's latest clarification is 23 → kraatz #17 (open)
- `d1daa75` TM-007: AG-UI's client-held history as a known protocol weakness (#43) → kraatz #17 (open)
- `338eb8e` AG-UI archive Markdown: Compacted wording, autolinks, refusal reason, bad timestamps (#44) → kraatz (not opened yet: `contrib/agui-archive-markdown` pushed, title and body in fork issue #45)
