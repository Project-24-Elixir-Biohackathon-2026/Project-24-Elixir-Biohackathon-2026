# 2026-11-03: AG-UI conversation record — living spec, step 3 onwards

Continues [`2026-11-03T1520Z-agui-one-living-spec.md`](2026-11-03T1520Z-agui-one-living-spec.md) (its *Decision*
section still holds; read it only if a choice below is unclear). Unit: spec PR **#19**
(`spec/agui-conversation-record`, worktree `.claude/worktrees/spec-agui-conversation-record`), still a draft, no
review round yet.

## Done this session

1. `8ee4e77` **Split** `docs/specs/2026-10-15-agui-frontend-design.md` into the directory
   `docs/specs/2026-10-15-agui-frontend-design/` (README + `01-…`–`12-…`), verbatim: header + parts reproduce the
   old file byte for byte. Current-design links re-pointed (`AGENTS.md`, `BACKLOG.md`, both platform READMEs,
   the compaction spec's *Texts this work makes stale*). History files (handoffs, done plans, investigations)
   keep the old path on purpose. Rename detection doesn't follow (07 holds only 139 of 577 lines); expected.
2. `ebfb28f` **Fold**: §6 rewritten to the sessions as built; new `13-conversation-record.md` and
   `14-archive.md`; README with decisions table (record **1–18**, numbers unchanged; sessions as built
   **19–30**), early output, glossary, parts map; `clarifications.md` (1), `out-of-scope.md`,
   `inputs-for-plan.md`; §2, §3, §5 *History*, §9 (key check extended, item 6 session API) and §10 (chat UI and
   archive tests) updated; `docs/README.md` row added; the single-file record spec removed. Upstream-clean:
   no `BACKLOG`, `superpowers`, `docs/knowledge|guides|…` mentions in the directory (grep in that commit's
   session), all relative links resolve.

Mapping of the sessions spec's decisions (for clarification 8): carried as **19** (its 1: volume/image part),
**20** (5), **21** (6), **22** (7), **23** (8), **24** (4: detached run, clone), **25** (9), **26** (10), **27** (13),
**28** (14), **29** (15), **30** (11: the barrier part); its 2 is inside 10; replaced: 1 (file format), 3 (atomic
rewrite), 4's "at most one run at a time" (now 9), 11's copy (15), 12 (15, 16).

## Next

1. **Sessions spec** (`docs/superpowers/specs/2026-10-29-agui-chat-sessions-design.md`): status *folded into
   `docs/specs/2026-10-15-agui-frontend-design/` (#19)*, **Latest clarification: 8** (it says 5; it has 7), and
   clarification 8 with the mapping above. *Spec-and-plan-layout*, *Across documents*: cut its sections 1–6,
   *Glossary*, *Early output*, *Out of scope*, *Inputs for the plan* to one pointer each (into the living spec's
   parts) so no competing normative text stays; keep the header, the decisions table marked as history, and
   the clarifications.
   **Conflict to resolve first:** compaction plan slice 2/3 (`docs/superpowers/plans/2026-11-03-agui-compaction/
   slice-2-chat-archive.md` l. 509, 615, 635, and its README l. 187) adds a clarification to the sessions spec
   *for §4* (the archive). After the fold, that clarification belongs in the living spec (§14, its
   `clarifications.md`). Either rewrite those task lines in this PR (plan text that a spec change invalidates
   is updated in the same PR) or, if that oversteps the compaction track, put a line in `BACKLOG.md` *Next*.
   Recommendation: rewrite the task lines here; it is a path change only. Also the compaction spec l. 299
   names the sessions spec as a text to update: re-point it to the living spec.
   Other current-design citations to re-point: `BACKLOG.md` l. 28 (sessions with owners), `docs/README.md`
   l. 21 (mark the sessions spec *folded*), `docs/knowledge/agui-chat-sessions.md` l. 133 (check what it cites).
2. `AGENTS.md`: *Overrides* line (l. 153) "First used by the AG-UI conversation record spec" → the living AG-UI
   spec; *Current work* line (l. 194) → the record is §13–14 of the living spec, in review. `BACKLOG.md` l. 34
   (the history item): its spec is now §13–14 of the living spec (#19), handoff → this file.
3. PR #19: title (e.g. *Spec: one living AG-UI spec, with the conversation record*) and body (it edits
   instructions: list the rule the *Overrides* line adds), mark ready, local review round (correctness,
   methodology; ask the methodology reviewer to check the fold against *Splitting an existing document* and
   *Across documents*), address it, then the gate: one comment asking the user for `approved`, and
   `next-session.sh --end --blocked 19`.

## Environment note

This VM gave intermittent `Too many open files` on `cat` and `git` at session start (system-wide fd count was
low, `ulimit -n` 1048576); retrying after a few seconds worked. Not yet a knowledge note: record one if it
recurs.
