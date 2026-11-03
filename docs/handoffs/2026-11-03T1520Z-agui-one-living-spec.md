# 2026-11-03: AG-UI conversation record — fold it into one living AG-UI spec

Continues [`2026-11-03T1500Z-agui-conversation-record-spec.md`](2026-11-03T1500Z-agui-conversation-record-spec.md)
(named after it so `ls | tail -1` finds this one; written at 10:10Z). Unit: spec PR **#19**
(`spec/agui-conversation-record`, worktree `.claude/worktrees/spec-agui-conversation-record`), still a draft,
no review round yet.

## Done

- The spec is written, self-reviewed and pushed as a single file:
  `docs/specs/2026-11-03-agui-conversation-record-design.md` (18 decisions, early output, sections 1–8). Its
  design is the one agreed in the previous handoff; nothing in it changed.
- Open WebUI's claims were checked in its source (tag `v0.11.3`, `2a960a5`, cloned to a scratchpad; clone it
  again with `git clone --depth 1 --branch v0.11.3 https://github.com/open-webui/open-webui.git`):
  `load_messages_from_db` and `MESSAGE_REPLAY_KEYS` (`backend/open_webui/utils/middleware.py` ~2159), and the
  `output` item shapes now written into the spec's section 7.
- `AGENTS.md`: an *Overrides* line (upstream-bound specs live in `docs/specs/`) and a *Current work* line.

## Decision taken this session (the user, 2026-11-03)

The user asked for upstream to receive **one coherent package**, an updated spec, plan and implementation, not a
new spec superseding the sessions spec. Asked to choose, they picked **one living spec**:

- Upstream's `docs/specs/2026-10-15-agui-frontend-design.md` (577 lines, upstream-clean) becomes the living AG-UI
  spec, **split into a directory** (`.methodology/shared/guides/spec-and-plan-layout.md`, *Spec layout*,
  *Splitting an existing document*): `README.md` with one decisions table, a part per section.
- Its §6 *The chat UI* is rewritten to the current design of the chat sessions and sidebar, taken from
  `docs/superpowers/specs/2026-10-29-agui-chat-sessions-design.md` (its current-design parts only; its storage
  is replaced by the record).
- This spec's content becomes its parts (the record: journal, run route, concurrency, rebuild, session API;
  the archive's Open WebUI export), its decisions in the README's table. The single file
  `docs/specs/2026-11-03-agui-conversation-record-design.md` is then removed (it never merged, so it is not
  history).
- The fork's sessions spec gets status *folded into `docs/specs/2026-10-15-agui-frontend-design/` (#19)* and a
  clarification 8 saying which of its decisions the record replaces (1, 3, 4's "at most one run at a time",
  11, 12) and which carry over.
- **Compaction folds in later**, as its own part, once its last slice merges (its slices 2–3 still cite its
  spec). Landing spot: `BACKLOG.md` (added in this commit).
- The implementation goes upstream as the **final state** of the package, not each fork commit replayed: the
  sessions store would otherwise go up and be replaced in the same PR. `docs/guides/contributing-upstream.md`
  step 3 ports commit by commit; a package port is a change to that guide. Landing spot: `BACKLOG.md` (added in
  this commit).

## Next

1. Split the frontend spec into its directory, mechanical: one commit (`git mv` and cuts, no text changes).
2. Rewrite §6 from the sessions spec, add the record's parts and decisions, drop the single file; fix every
   link to the old path (`grep -rn 2026-10-15-agui-frontend-design`); keep it upstream-clean (the grep in
   `docs/guides/contributing-upstream.md`, step 4).
3. Update the sessions spec's status and clarification 8; the `AGENTS.md` *Overrides* and *Current work* lines
   (the spec's new path); the `BACKLOG.md` history item.
4. PR #19's title and body (it edits instructions: list the rules the *Overrides* line adds), mark it ready, run
   the local review round (correctness, methodology), address it, then the gate: one comment asking the user
   for `approved`, and `next-session.sh --end --blocked 19`.
