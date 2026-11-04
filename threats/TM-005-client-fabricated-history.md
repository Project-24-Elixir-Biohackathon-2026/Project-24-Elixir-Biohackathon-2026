---
id: TM-005
name: Conversation History Fabricated Through the Client
description: >
  In protocols where the client holds the conversation and sends all of it with every run (AG-UI, OpenAI-style chat completions), an agent that trusts the history it is sent believes whatever the client says happened earlier. A participant can fabricate an assistant turn or a tool call with a result the environment never produced, edit or delete real turns, or forge a marker the agent acts on, such as a compaction marker that makes it drop everything before it. Unlike pasted text (TM-003), the injected content claims to be the agent's own words or the environment's output, so the model gives it more weight, and a record that stores the client's latest history shows the forgery as if it had happened. This is AG-UI's default, not a slip of one implementation: its client resends the whole history on every run, contributors in the protocol's own discussion name that history untrusted input, and the same run input carries the client's tool definitions, which reach the model too (scenario 5).
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
  - information-disclosure
---

# TM-005: Conversation History Fabricated Through the Client

## Attack Scenarios

1. **Devtools edit**: the participant edits an earlier reply in the browser's copy of the conversation and sends a new message; the edited reply reaches the model.
2. **Direct request**: `curl` against the chat server's run route with a history carrying an invented tool call and its result.
3. **Forged marker**: an assistant message shaped like the agent's compaction marker, so the agent drops the real history before it.
4. **Direct agent access**: whoever holds the agent's bearer key calls the agent itself, bypassing the chat server.
5. **Client-supplied tools**: the same run input carries `tools`, and Pydantic AI's AG-UI adapter turns each one into a tool definition the model sees (the client's name, description and schema; a call ends the run and is left to the client). A request to the chat server's run route can add a tool whose description carries instructions, or that invites the model to call it with what it has read, which the model then sends back in the call's arguments. The chat server records `tools`, `context`, `state` and `forwardedProps` with each run and forwards them unchanged (less any `spe_command` in `forwardedProps`); the agent ignores `state` (its dependencies hold none) and `context`, but not `tools`. The chat UI defines no frontend tools of its own, so a run from the browser sends none.

## Preconditions

- The client sends the history and the agent, or the server in front of it, uses it as sent. AG-UI's client sends it by default on every run ([ag-ui#2186](https://github.com/ag-ui-protocol/ag-ui/issues/2186)); a mode where the server keeps the history and the client sends only what it has not confirmed is a draft ([ag-ui#3135](https://github.com/ag-ui-protocol/ag-ui/pull/3135)), not yet part of the protocol. The AG-UI chat server no longer uses the client's history (below); Open WebUI's stored chat is editable by design (message edit and history merge).
- The participant can change what the client sends (devtools, a script, a proxy).
- For scenario 5: the chat server forwards the client's `tools` (it does, today).
- Records are tamper-proof against root on the VM only once shipped off it as they are written; whoever holds the agent key or root can still send or rewrite any history.

## Mitigations

### Preventive

- The chat server owns the history: from each request it takes only the new user message and sends the agent the history from its own append-only journal; everything else the client sent is not used. This closes the chat path (browser, devtools, requests to the chat server) for the AG-UI frontend. It applies to the message list the trusted-frontend-server pattern that Microsoft's AG-UI security guide recommends against *Message List Injection*, where the untrusted user supplies only message content; the run's other fields are still the client's (scenario 5) ([Security Considerations for AG-UI](https://learn.microsoft.com/en-us/agent-framework/integrations/ag-ui/security-considerations)).
- Not yet in place, for scenario 5: the chat server drops the client's `tools` (the chat UI sends none, so nothing is lost) or keeps an allowlist, as the same guide recommends against *Client-Side Tool Injection*.
- The agent's key stays out of the sandbox's environment and configuration, so code run there cannot call the agent directly (checked by `verify.yml`).

### Detective

- Whatever the client sent that differs from the journal is recorded with its kind (`fabricated`, `edited`, `deleted`, `system`) and archived with the run, rendered as "sent by the client, not used".
- The journal's `run_start` records the run's `tools`, `context`, `state` and `forwardedProps` as the client sent them, so a client-supplied tool shows in the archive's raw journals.
- The agent's run log records every run, including one made directly with the key, which the journals do not have.

### Responsive

- Review the archived ignored content of a run before trusting its outcome; treat a participant who sends it as probing the boundary.
