# Upstream ports

Which fork commits with project changes have been decided for upstream (`Project-24-Elixir-Biohackathon-2026/Project-24-Elixir-Biohackathon-2026`, formerly `kraatz/elixir-biohackathon-2026-test`; `kraatz #<n>` is its PR number):
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
- `bc5d944` AG-UI agent: per-run token cap optional, off by default (#4) → kraatz #17 (merged; first kraatz #9, closed in favour of #17)
- `33774a6` AG-UI chat sessions: the store (1/3) (#9) → kraatz #17 (merged)
- `cf3160c` Ignore __pycache__ under platform/dev → kraatz #17 (merged)
- `b2b328b` Untrack a compiled test module committed by mistake → kraatz #17 (merged)
- `b3ce239` Untrack the remaining compiled test modules → kraatz #17 (merged)
- `bb7eef7` AG-UI chat sessions: sidebar, row menu, archive export (2/3) (#10) → kraatz #17 (merged)
- `e525b0d` AG-UI chat sessions: complete (3/3) (#11) → kraatz #17 (merged)
- `4157add` AG-UI chat minors (#14) → kraatz #17 (merged)
- `050ee0f` Agent compacts the conversation (1/3) (#17) → kraatz #17 (merged)
- `0337a7c` Spec: one living AG-UI spec, with the conversation record (#19) → kraatz #17 (merged)
- `c8d1b46` Spec: the AG-UI archive copies live, only the final archive stops → kraatz #17 (merged)
- `4f306cb` Chat and archive show a compaction (2/3) (#18) → kraatz #17 (merged)
- `2eeb760` Plan: AG-UI conversation record (#20) → kraatz #17 (merged)
- `81a35d0` AG-UI record: feasibility check, journal, rebuild, anchor (1/4) (#22) → kraatz #17 (merged)
- `4c8fb78` AG-UI record: exporter in the image, write_run.py renders AG-UI chats (2/4) (#23) → kraatz #17 (merged)
- `200e07e` The record on journals: store, run route, API and archive (3/4) (#24) → kraatz #17 (merged)
- `ec1fc32` de.NBI window, docs, decision 13 (3/3) (#21) → kraatz #17 (merged)
- `3e44059` Spec: /compact in the AG-UI chat (#26) → kraatz #17 (merged)
- `008fa47` Live archive, final barrier, instance checks, record built (4/4) (#25) → kraatz #17 (merged)
- `7850489` AG-UI /compact: the agent (1/2) (#28) → kraatz #17 (merged)
- `041a095` AG-UI chat: model-written titles, resizable sidebar, theme toggle (#29) → kraatz #17 (merged)
- `41eb5f4` AG-UI chat: tool-call cards after Open WebUI's ToolCallDisplay (#31) → kraatz #17 (merged)
- `8ac8da2` AG-UI /compact: the chat (2/2) (#30) → kraatz #17 (merged)
- `4c768b9` AG-UI chat: /compact in the slash menu, input marked as a command (#32) → kraatz #17 (merged)
- `174062e` AG-UI agent: title.max_tokens 64 -> 1024 for reasoning models (#33) → kraatz #17 (merged)
- `a25ce09` Merge upstream/main (2026-11-04): clone-on-VM layout, threat format, site → kraatz #17 (merged)
- `9cf1f09` Review #35 (methodology): stale spec, README and plan references after the merge → kraatz #17 (merged)
- `d6586f9` Review #35 (correctness): ui-dev archive refused clearly, our agent vars re-applied, fork repo URL → kraatz #17 (merged)
- `0e00677` AG-UI chat: tool cards worded as Open WebUI, theme toggle top right (#34) → kraatz #17 (merged)
- `49a2c58` Merge remote-tracking branch 'origin/main' into change/merge-upstream-2026-11-04 → kraatz #17 (merged)
- `52cdc2c` repo role: don't clone the fork's private submodule on the instance (#37) → kraatz #17 (merged)
- `36bb78c` Merge upstream/main: both chat frontends on every instance (kraatz #15, #16) → kraatz #17 (merged)
- `d0b9742` Archive export test: pass spe_frontends, the variable's current name → kraatz #17 (merged)
- `bf458b7` Address #39's methodology review: stale docs after the both-frontends merge → kraatz #17 (merged)
- `27076fd` Address #39's correctness review: re-rendering a both-frontends run → kraatz #17 (merged)
- `d03751c` Reset an existing host's frontend through its compose link (#41) → kraatz #17 (merged)
- `9abdbb9` Contributing guide: the package port path; spec's latest clarification is 23 → kraatz #17 (merged)
- `d1daa75` TM-007: AG-UI's client-held history as a known protocol weakness (#43) → kraatz #17 (merged)
- `338eb8e` AG-UI archive Markdown: Compacted wording, autolinks, refusal reason, bad timestamps (#44) → kraatz #28 (open)
- `70d6505` AG-UI chat: reopened sessions land on their end; menu focus after a click outside (#46) → kraatz #29 (open)
- `8e0b891` denbi example: set spe_data_root, say where the API IP comes from → kraatz #30 (open)
- `171398a` Migrate the methodology off the submodule (253d08561b5640f4c1227e3e807be466c82a588a) → not for upstream: its shared files (`.gitignore`, `.gitmodules`) only drop the fork's methodology submodule
- `231ba4c` Merge upstream/main (2026-11-08): kraatz #17 merged, report app, dependency bumps, TM-005 → not for upstream: a merge of upstream itself; the fork work it carries has its own lines
- `23a944b` AG-UI chat: group tool calls across model steps (#50) → kraatz #31 (open)
- `9eec3a8` AG-UI chat: title a new session as its first run starts (#52) → kraatz #32 (open)
