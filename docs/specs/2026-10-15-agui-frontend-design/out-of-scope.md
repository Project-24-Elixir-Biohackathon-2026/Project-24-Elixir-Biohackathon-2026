# Out of scope

What the chat sessions (§6), the conversation record (§13, §14) and `/compact` (§15) leave out, each deferred.

- **Sessions with owners** (several participants per instance): needs identity in the chat UI; waits, like
  per-user budgets, for multi-participant instances.
- **A run report** in the CopilotKit chat (Open WebUI's "Run report" note); `index.md` states that there is
  none.
- **Branching, editing or regenerating messages in the chat**: CopilotKit's page passes no edit or regenerate
  handlers, and navigating branches is left to the archive. Also export from the UI, full-text search over
  messages, folders: Open WebUI features not asked for.
- **A run with no new user message** (a regenerate): refused by decision 3 until one is needed. A manual
  compaction is a command run instead (§15), which carries a `/compact` message.
- For `/compact` (§15): other slash commands, a compact button, an escape for sending the
  literal text to the model, and manual compaction while automatic compaction is off. Open WebUI's own
  `/compact` is its own and unchanged.
- **Recording runs sent straight to the agent** beyond its run log.
- **Participants' root access on the VM**, and records shipped off the VM as they are written.
- **A promptfoo target that runs through `chat-ui`** (the mitigated variant of §13 *Approach*'s experiment).
- **Recording edits made in Open WebUI** (its event webhook or audit log).
