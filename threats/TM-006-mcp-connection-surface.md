---
id: TM-006
name: Expanded Attack Surface from User-Connected MCPs
description: >
  The user connects the agent to Model Context Protocol (MCP) servers, each of
  which introduces additional, often unvetted tools and data sources that
  expand the attack surface with new security holes.
assets:
  - external-systems
  - agent-integrity
  - credentials
stride:
  - tampering
  - information-disclosure
  - elevation-of-privilege
---

# TM-006: Expanded Attack Surface from User-Connected MCPs

## Description

The user connects the agent with MCP (Model Context Protocol) servers to give
it additional tools and data sources for building the pipeline. Each connected
MCP is a new, often unvetted, third-party integration that can introduce an
unprecedented number of security holes: untrusted tool descriptions and
outputs, over-broad permissions, exfiltration paths, and confused-deputy
opportunities.

## Affected Assets

Third-party systems the agent can now reach (external-systems), the agent's own
behavioral integrity (agent-integrity), and any secrets exposed to or through
the MCP (credentials).

## Attack Scenarios

1. **Malicious MCP server**: a rogue or compromised MCP returns injected
   instructions or performs unauthorized actions on the agent's behalf.
2. **Tool-description injection**: attacker-controlled tool metadata manipulates
   how the agent selects and invokes tools.
3. **Over-permissioned integration**: a benign-looking MCP is granted more
   access than needed, widening the blast radius of any compromise.

## Preconditions

- The agent can be connected to third-party MCP servers by the user.
- Connected MCPs are not vetted, scoped, or sandboxed before use.
- Tool descriptions and outputs are treated as trusted context.

## Mitigations

### Preventive

- Allow-list and vet MCP servers; scope each to least privilege.
- Treat MCP tool descriptions and outputs as untrusted data.
- Require explicit user approval for sensitive tool invocations.

### Detective

- Inventory connected MCPs and log all tool calls and returned content.
- Monitor for anomalous tool usage or data access via MCP.

### Responsive

- Disconnect the offending MCP and revoke associated credentials.
- Quarantine the session and escalate on detected abuse.
