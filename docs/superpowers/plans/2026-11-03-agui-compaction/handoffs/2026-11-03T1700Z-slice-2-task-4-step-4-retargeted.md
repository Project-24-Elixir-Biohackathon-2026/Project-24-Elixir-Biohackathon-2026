# 2026-11-03: slice 2/3's spec clarification moves to the living AG-UI spec (#19)

Contract change from spec PR #19 (`spec/agui-conversation-record`), not progress on this plan. #19 folds the chat
sessions spec (`docs/superpowers/specs/2026-10-29-agui-chat-sessions-design.md`) into the living AG-UI spec
`docs/specs/2026-10-15-agui-frontend-design/`, so the sessions spec's sections are now pointers and its
clarification 8 records the fold.

Rewritten in #19 (`development-workflow.md`, *Contract changes land too*):

- [`slice-2-chat-archive.md`](../slice-2-chat-archive.md), task 4: its *Files* list, **Step 4** (the clarification
  now goes into the living spec's `clarifications.md` and amends §14's paragraph on the archive as built, where
  `write_agui_run.py`'s `index.md` columns are listed) and Step 5's `git add` and message;
- [`README.md`](../README.md), the file table's row for that clarification;
- the compaction spec's *Texts this work makes stale* (the sessions spec's item, now the living spec).

**If #18 reaches Step 4 before #19 merges**, it follows the plan on `main` (sessions spec, clarification 8) and says
so on #19; #19 then renumbers its fold clarification to 9 and moves #18's clarification into the living spec. #18's
session was told (2026-11-03) and acknowledged. Nothing else in the slice changes.
