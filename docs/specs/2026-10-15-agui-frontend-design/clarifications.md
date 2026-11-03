# Clarifications

The decision log: numbered, append-only, never renumbered. History, not design: each entry's change is already
in the parts it amends.

1. **The spec becomes the living AG-UI spec: §6 holds the chat sessions, §13 and §14 the conversation record**
   (2026-11-03; the fork's PR #19). The single file is split into this directory, one part per section; §6 states
   the sessions, session API and sidebar as built, restated for the record (their journal parts wait for it); §13
   (the record) and §14 (the archive) are added, with the README's decisions table, early output and glossary; §2,
   §3, §5 *History*, §9 and §10 are rewritten where they said the chat keeps no conversation, the client's history
   reaches the agent unchanged, or the chat UI has no tests. *Reason:* the chat sessions and the record were
   designed in separate specs; one spec, kept current, lets the AG-UI work be read, reviewed and ported as one
   package. Chat sessions stored the client's history, which a participant can forge; the record replaces that
   storage (decisions 1–18) and carries the rest of the sessions' design over (decisions 19–30). *Amends:* §2, §3,
   §5 *History*, §6, §9, §10; adds §13, §14. *Status:* folded.

2. **The archive copies live; only the final archive stops the services** (2026-11-03, the user, after #19
   merged). `archive.yml` no longer stops `chat-ui` and the agent: it copies the journals and the run log from
   the running containers, so it can run at any time as a backup without interrupting participants. The stop
   (the barrier) stays only in the archive `destroy.yml` runs (`spe_archive_final: true`), and the services are
   not started again there. The bundle records `live` or `final`. *Reason:* the user wants to archive and back
   up without stopping users; a stop per archive cancels every run in progress. The append-only journal (§13)
   makes a live copy safe: it is an earlier state of each file with at most a torn last line, which the
   rebuild already skips, and a run without `run_end` reads as `incomplete`. *Cost if wrong:* a live archive
   can miss the last second of a run and show runs as `incomplete` that complete later; the final archive
   still has them whole. *Amends:* §14 *Export* and *Write*, decision 30. *Status:* folded.

3. **The archive renders the agent's compaction marker as a section, and `index.md` counts them** (2026-11-03;
   AG-UI compaction, slice 2/3, the fork's PR #18). An assistant text message whose id starts with
   `spe-compaction-` is rendered as `## Compacted`, the line "From here the model saw this summary instead of the
   messages above." and the summary in a fence; `index.md`'s columns become `# | Session | Tags | Created | Runs |
   Compactions | State`. *Reason:* the agent compacts a conversation that no longer fits the model's context and
   marks the point in the session's messages (`docs/superpowers/specs/2026-11-03-agui-compaction-design.md`, §7,
   clarification 1). It was written as the chat sessions spec's clarification 8 on that branch, which #19's fold
   took first. *Amends:* §14, the archive as built (`index.md` columns). *Status:* folded.
