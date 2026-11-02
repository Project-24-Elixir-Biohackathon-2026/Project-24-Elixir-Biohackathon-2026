---
id: TM-004
name: Expanded Attack Surface from User-Connected Tool Servers
description: >
  The user connects the agent to additional tool servers (Model Context Protocol or OpenAPI), each an unvetted third-party integration. Their tool descriptions and results feed the model, their permissions add to the agent's, and data can flow from one tool to another. In this stack the sandbox is itself such a server, and the Open WebUI frontend lets a user add more unless the administrator disables it.
status: hypothesised
entry-points:
  - mcp-server
assets:
  - external-systems
  - agent-integrity
  - credentials
  - user-records
stride:
  - tampering
  - information-disclosure
  - elevation-of-privilege
---

# TM-004: Expanded Attack Surface from User-Connected Tool Servers

## Attack Scenarios

1. **Rogue server**: a malicious or compromised server returns injected instructions in its tool descriptions or results, or performs actions of its own when called.
2. **Exfiltration path**: a benign server with write access to the outside (a Git host, an issue tracker, a mailbox) sits next to the sandbox in one context. Data read through WES, DRS or TRS flows out through the other tool, with no network path from the SPE itself.
3. **Tool shadowing**: a server exposes a tool with the same name or a more attractive description than the sandbox's `run_command`, and the model calls it instead.
4. **Over-permissioned integration**: the server is granted broader scopes than the task needs, widening what a single injected instruction can do.

## Preconditions

- Users can add tool servers to the frontend themselves.
- Tool descriptions enter the system prompt and results enter the context unmarked, as the sandbox's do.
- Tools from different servers share one context and one agent identity.
- Nothing blocks outbound traffic from the components that call the servers.

## Mitigations

### Preventive

- Only the administrator configures tool servers (in Open WebUI, disable user-level tool servers); the CopilotKit chat offers none.
- Allow-list servers and scope each to least privilege; never connect a server that can write outside the SPE next to one that can read inside it.
- Treat tool descriptions and results as untrusted data (TM-003) and require user confirmation for sensitive tool calls.

### Detective

- Inventory the connected servers per instance and record every tool call with its server in the run log.
- Alert on data from the SPE's APIs appearing in arguments to another server's tools.

### Responsive

- Disconnect the server, revoke its credentials and rotate any secret it could have seen.
- Destroy and recreate the instance.
