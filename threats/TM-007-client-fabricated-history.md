---
id: TM-007
name: Conversation History Fabricated Through the Client
description: >
  In protocols where the client holds the conversation and sends all of it with every run (AG-UI, OpenAI-style chat completions), an agent that trusts the history it is sent believes whatever the client says happened earlier. A participant can fabricate an assistant turn or a tool call with a result the environment never produced, edit or delete real turns, or forge a marker the agent acts on, such as a compaction marker that makes it drop everything before it. Unlike pasted text (TM-003), the injected content claims to be the agent's own words or the environment's output, so the model gives it more weight, and a record that stores the client's latest history shows the forgery as if it had happened.
status: hypothesised
entry-points:
  - client-history
assets:
  - conversation-history
  - agent-integrity
stride:
  - spoofing
  - tampering
  - repudiation
---

# TM-007: Conversation History Fabricated Through the Client

## Attack Scenarios

1. **Devtools edit**: the participant edits an earlier reply in the browser's copy of the conversation and sends a new message; the edited reply reaches the model.
2. **Direct request**: `curl` against the chat server's run route with a history carrying an invented tool call and its result.
3. **Forged marker**: an assistant message shaped like the agent's compaction marker, so the agent drops the real history before it.
4. **Direct agent access**: whoever holds the agent's bearer key calls the agent itself, bypassing the chat server.

## Preconditions

- The client sends the history and the agent, or the server in front of it, uses it as sent. The AG-UI chat server no longer does (below); Open WebUI's stored chat is editable by design (message edit and history merge).
- The participant can change what the client sends (devtools, a script, a proxy).
- Records are tamper-proof against root on the VM only once shipped off it as they are written; whoever holds the agent key or root can still send or rewrite any history.

## Mitigations

### Preventive

- The chat server owns the history: from each request it takes only the new user message and sends the agent the history from its own append-only journal; everything else the client sent is not used. This closes the chat path (browser, devtools, requests to the chat server) for the AG-UI frontend.
- The agent's key stays out of the sandbox's environment and configuration, so code run there cannot call the agent directly (checked by `verify.yml`).

### Detective

- Whatever the client sent that differs from the journal is recorded with its kind (`fabricated`, `edited`, `deleted`, `system`) and archived with the run, rendered as "sent by the client, not used".
- The agent's run log records every run, including one made directly with the key, which the journals do not have.

### Responsive

- Review the archived ignored content of a run before trusting its outcome; treat a participant who sends it as probing the boundary.
