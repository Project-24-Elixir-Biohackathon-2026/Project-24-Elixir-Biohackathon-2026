# 2026-11-03: chat history integrity — continue the discussion with the user

An interactive discussion, not a unit: no branch, no PR. The user wants to go on discussing it. Start by reading
[`docs/proposals/2026-11-03-agui-history-integrity.md`](../proposals/2026-11-03-agui-history-integrity.md) (the
whole of it: ~160 lines), then ask the user where they want to pick up.

## What was established (all in the proposal, with file references)

- **AG-UI stack**: the client holds the history and resends all of it every run, and the agent trusts it
  (except system messages). The chat UI's session file stores the client's latest version (overwritten per run,
  written once at the run's end); the agent's run log is append-only but partial. Six injection cases, a forged
  compaction marker (case 5) the strongest.
- **Open WebUI v0.11.3** (the deployed image): the server rebuilds the model's history from its database, but the
  stored chat is editable through the API and the UI, tool calls and tool results included (the response edit
  view's JSON editor). A user message's *Save* edits in place and keeps the replies after it; *Send* branches.
  Almost nothing records an edit (`originalContent`, one level, for in-place reply text edits only); the audit log
  and event webhooks are off in our role.
- **Proposal**: keep AG-UI's protocol and add an append-only server-side journal compared with the client's
  history at each run's start (option B); server-owned history (A, which Open WebUI does) and a switch (C) are the
  alternatives. Two cheaper steps: a check against the stored session at a run's start, and marker provenance in
  the run log.

## Open, for the user

The proposal's *Open questions*: record or block edits; journal format; a threat-catalog entry for client history
fabrication; whether the ladder's scoring needs it; an Open WebUI edit record (webhook or audit log). Also whether
to fold `compactions[].marker_id` and `cut_at` into the compaction spec as a clarification (it changes decision
11; slice 1 is in progress, PR #17).

## Done in this session

- Proposal and its `BACKLOG.md` line; three corrections to its Open WebUI section after reading the source
  (8180eb3, 28921d1, 77b0dfb, df68651).
- Compaction plan: a note in slice 1, task 6, and the plan handoff `2026-11-03T0814Z-forged-marker-note-start-slice1.md`
  (1a82d99). Slice 1 had already started before the note: PR #17 has a comment, and its session got a message.
- agent-methodology issue #36: claims about other systems must be checked against their source before they shape
  an argument. This session first stated Open WebUI's behaviour from memory, wrongly. **Check any claim about Open
  WebUI or CopilotKit in the source before making it**: Open WebUI v0.11.3 is checked out at
  `/var/tmp/claude-1000/-workspace-biohackathon-biohackathon/0650b114-801c-4787-854b-bca98e5e53b0/scratchpad/owui`
  (a scratchpad: it may be gone; then clone `open-webui/open-webui` at tag `v0.11.3`), CopilotKit in
  `platform/agui/copilotkit-chat/node_modules`.
- Not done: the `biohackathon` submodule pin was not moved (the user asked to keep this out of the parent repo).
