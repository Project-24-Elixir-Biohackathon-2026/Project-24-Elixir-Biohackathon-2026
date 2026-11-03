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