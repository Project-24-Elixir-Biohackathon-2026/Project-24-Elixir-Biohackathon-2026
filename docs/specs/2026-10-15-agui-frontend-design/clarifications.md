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

4. **The feasibility sample comes from the built server once the journal is wired; the first slice shows the
   verdict at the runtime level** (2026-11-03; the fork's PR #20, the conversation record's plan). *Early output*'s
   first sample (the built server, a `curl` with a fabricated turn and a forged marker, `fake_agent.py`'s echo, the
   journal lines) is shown when the journal is wired into the run route, not in the first slice; the first slice
   shows the verdict through CopilotKit's runtime handler and a real `HttpAgent`, a middleware that replaces the
   history deciding what the agent receives, and stops the work for the user's decision if it does not. *Reason:*
   the journal lines and `fake_agent.py`'s echo of what it received exist only once the journal and the run route
   are built; the runtime-level test answers the same question (can `chat-ui` replace the history?) before any of
   that is built, which is what the early sample is for. *Cost if wrong:* the user sees the sample with journal
   lines one slice later than the spec said; a negative verdict still stops the work in the first slice.
   *Amends:* README, *Early output*. *Status:* folded.

5. **`spe_agui_source_dir` is `platform/agui`, not the repository root** (2026-11-03; the fork's PR #18 rewrote
   §7, PR #20 records it). §7's default is `{{ playbook_dir }}/../../agui`, the directory holding
   `pydantic-ai-agent/` and `copilotkit-chat/`; a deploy from another checkout passes
   `-e spe_agui_source_dir=<checkout>/platform/agui`. *Reason:* the platform moved under `platform/`, and the
   `agui` role stages `pydantic-ai-agent` and `copilotkit-chat` relative to this directory, so the repository
   root made `create.yml` fail. *Amends:* §7, the `agui` role's variables. *Status:* folded.
