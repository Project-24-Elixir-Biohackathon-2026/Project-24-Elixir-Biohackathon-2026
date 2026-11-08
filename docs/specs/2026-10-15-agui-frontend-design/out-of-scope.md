# Out of scope

What the chat sessions (§6), the conversation record (§13, §14) and `/compact` (§15) leave out, each deferred.

- **Sessions with owners** (several participants per instance): needs identity in the chat UI; waits, like
  per-user budgets, for multi-participant instances.
- **A run report** inside the CopilotKit chat. Since 2026-11-06 the report is neither frontend's: it lives on
  the portal VM behind the workspace's "Report" button (`docs/specs/2026-11-06-run-report-service.md`), and the
  archive's `agui/index.md` links it one level up.
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
- **A mark for a reply that finished while away** (ChatGPT's dot on the row): the running mark goes when the run
  ends, and nothing says the reply is unread; the early output's screenshot is where the user decides whether it
  is needed (clarification 27).
- **A limit on runs in progress at once**: one participant per instance, and each run's model calls are already
  capped by the agent (§5); a participant can start as many as they leave (clarification 27).
- **Navigating to a running session from a notification**, or any notification when a background run ends.

