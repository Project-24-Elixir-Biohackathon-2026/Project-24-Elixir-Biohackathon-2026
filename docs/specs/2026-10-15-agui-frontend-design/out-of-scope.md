# Out of scope

What the chat sessions (§6) and the conversation record (§13, §14) leave out, each deferred.

- **Sessions with owners** (several participants per instance): needs identity in the chat UI; waits, like
  per-user budgets, for multi-participant instances.
- **A run report** in the CopilotKit chat (Open WebUI's "Run report" note); `index.md` states that there is
  none.
- **Branching, editing or regenerating messages in the chat**: CopilotKit's page passes no edit or regenerate
  handlers, and navigating branches is left to the archive. Also export from the UI, full-text search over
  messages, folders: Open WebUI features not asked for.
- **A run with no new user message** (a manual "compact", a regenerate): refused by decision 3 until one is
  needed.
- **Recording runs sent straight to the agent** beyond its run log.
- **Participants' root access on the VM**, and records shipped off the VM as they are written.
- **A promptfoo target that runs through `chat-ui`** (the mitigated variant of §13 *Approach*'s experiment).
- **Recording edits made in Open WebUI** (its event webhook or audit log).
