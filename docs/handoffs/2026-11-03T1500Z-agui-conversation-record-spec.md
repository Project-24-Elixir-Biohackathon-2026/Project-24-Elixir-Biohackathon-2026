# 2026-11-03: AG-UI conversation record — write the spec

A brainstorming session (`superpowers:brainstorming`, architectural path) ended at the context budget after the
design was agreed with the user in two parts. **Next: write the spec**, self-review it, open the `spec/` PR and
ask the user to approve it (the `approved` label). No spec file exists yet.

Read first: [`docs/investigations/2026-11-03-history-editing-threat.md`](../investigations/2026-11-03-history-editing-threat.md)
(*Synthesis*, *Why two records*) and the proposal
[`docs/proposals/2026-11-03-agui-history-integrity.md`](../proposals/2026-11-03-agui-history-integrity.md) (injection
cases 1–6, Open WebUI v0.11.3's behaviour). The user asked earlier not to edit the proposal.

## What the user asked for

Redesign from scratch how AG-UI stores conversations: save every participant conversation as it goes, for later
analysis, following Open WebUI, but protected against the naive history edits Open WebUI allows (treated here as a
vulnerability). One consistent way to save and export conversations across both frontends (Open WebUI and
AG-UI). Ultimately one upstream PR to `kraatz` with the spec, plan and implementation: upstream has only the
2026-10-15 AG-UI spec ("no persistence", §6) and the agent's run log; our chat sessions (fork #7) never went up.

## Decisions (agreed with the user)

1. **The server owns the history** (Open WebUI's model, the proposal's option A), not record-and-flag. A client's
   history cannot change what the model sees; ignored client content is recorded, not blocked silently.
2. **`chat-ui` owns it; the agent stays stateless** (option 2). Why, as the user argued and the session
   confirmed: `chat-ui` is a backend (its server route already adds the agent key); Open WebUI fronting an
   *external* agent is exactly this shape (its backend owns the history, the agent is stateless); infra teams may
   swap the AG-UI agent, and the record should not depend on the system under evaluation; promptfoo keeps sending
   any history straight to the agent, which makes a baseline (agent trusts a fabricated history) vs mitigated
   (same attack through `chat-ui`) experiment possible. MCP extends one agent's tools; swapping replaces the loop.
   Option 1 (the agent owns it) was the session's first recommendation and was dropped for these reasons.
3. **Boundary, stated in the spec**: protects against edits through the chat (browser, devtools, requests to
   `chat-ui`). Assumes participants hold neither the agent key nor root on the VM. Participants very likely have
   root on the portal (Coder `web_terminal`/`ssh_helper`/`port_forwarding_helper`, agent as `ubuntu` with
   passwordless sudo): recorded in `BACKLOG.md` as its own item, out of this spec. The sandbox shares the `tools`
   network with the agent (it must, to be reached), so the sandbox path is closed by the key alone: a check that
   `terminal.env` and the sandbox's environment never hold the agent key.
4. **Concurrent runs on one conversation are allowed** (the user: "why not allow concurrency?"), as in Open
   WebUI: every journal event carries its `run_id`; two runs from the same anchor become sibling branches; restore
   shows the tip of the run that ended last. No 409.
5. **Compaction PR #17 is unaffected**: the agent still trusts the history it receives, which now only comes from
   `chat-ui`'s journal, so a forged marker (case 5) never reaches it through the chat.
6. **The spec lives in `docs/specs/`** (upstream's layout), written upstream-clean (no links to handoffs,
   investigations, proposals, `BACKLOG.md`, `docs/superpowers/`), so it ports unchanged. This needs one line in
   `AGENTS.md` *Overrides* (instead of `docs/superpowers/specs/`). It supersedes upstream's
   `docs/specs/2026-10-15-agui-frontend-design.md` §6 ("no persistence"), with a pointer there, and in the fork the
   storage parts of `docs/superpowers/specs/2026-10-29-agui-chat-sessions-design.md` (sidebar behaviour carries
   over; status/clarification there). The plan stays fork-only in `docs/superpowers/plans/`; the upstream PR later
   gets a single-file plan and progress record in `docs/plans/` (like `2026-10-15-agui-frontend-progress.md`).

## The design

**Run route** (`/api/copilotkit`, server side), per run:
1. Load the conversation's journal; the **anchor** is the latest client message whose id the journal holds.
   Messages after it other than new user messages, stored ids with different content, missing middle turns and
   compaction markers are **ignored** and recorded in full with their kind (fabricated, edited, deleted).
2. Write `run_start` (parent, new user message(s), ignored content, source) **before** calling the agent.
3. Replace `messages` with the journal's root→anchor path plus the new message(s); forward with the key.
4. Append each AG-UI event as it arrives; write `run_end` (status, usage, error).
5. Write failure: `run_start` unwritable → run refused (503); failure mid-run → run aborted and marked. Replaces
   today's `spe.session_save_failed` warning.

**Journal**: `/data/sessions/<id>.jsonl` on the `chat-sessions` volume, append-only, events `created`,
`run_start`, raw AG-UI events, `run_end`, `meta` (title, tags, pinned, hidden, deleted). Messages rebuilt by
applying events with `@ag-ui/client` (the browser's code); every message has `parentId`; branches are siblings.

**Sidebar API**: unchanged for the browser; `/api/sessions` list/get/patch read the journals with a small index
rebuilt at startup; restore loads the current branch into `setMessages()`; patch only appends `meta`; no route
changes message content; delete stays soft.

**Agent**: unchanged, stateless; its run log stays as the operational log and the only server record of direct
runs (promptfoo, operators).

**Export**: the archive copies journals raw; a converter writes each as an **Open WebUI chat** (`history` tree,
`currentId`, title, tags, timestamps, each run's tool calls as Open WebUI `output` items) in an Open WebUI-shaped
export bundle that `write_run.py` renders like any Open WebUI run; ignored client content shows as a marked block
("sent by the client, not used"). `write_agui_run.py` and the session JSON format go; no migration (only the dev
VM has old files).

**Early output and first acceptance check** (feasibility, unverified): with `fake_agent.py`, a request to
`chat-ui` carrying a fabricated assistant turn reaches the agent *without* it, and the journal records it as
ignored. If CopilotKit's runtime cannot replace `messages`, stop and revisit option 1 with the user.

## Still to settle in the spec (propose, don't ask unless it changes intent)

- Index of sessions at startup vs per-file metadata cache; fsync granularity per event vs per batch.
- Exact mapping of a run's AG-UI messages (several assistant and tool messages) onto Open WebUI's one assistant
  message with `output` items — verify against Open WebUI v0.11.3's `MESSAGE_REPLAY_KEYS` and `write_run.py`.
- Whether to add a threat entry in `threats/` for client history fabrication (the proposal's open question).
- Branch navigation UI: out of scope (CopilotKit's page passes no edit or regenerate handlers).

## Workflow

Full mode, spec stage: `.methodology/shared/claude/worktree.sh spec/agui-conversation-record`, draft PR with
`gh pr create --repo thodkatz/elixir-biohackathon-2026-test --base main`, label `spec`, local review round, then
the user's `approved`. Add a *Current work* line in `AGENTS.md`. Commits signed off (`git commit -s`).
