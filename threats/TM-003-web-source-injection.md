---
id: TM-003
name: Prompt Injection via Unreliable Web Sources
description: >
  While constructing the pipeline, the agent fetches content from unreliable
  web sources (e.g. documentation) whose text carries injected instructions
  with malicious intent (indirect prompt injection).
assets:
  - agent-integrity
stride:
  - tampering
---

# TM-003: Prompt Injection via Unreliable Web Sources

## Description

As it attempts to construct the pipeline, the agent fetches content from
unreliable web sources (for example, reading documentation, forum posts, or
package pages). That content can carry instructions crafted with malicious
intent, which the agent ingests into its working context and follows as if
they were legitimate guidance (indirect prompt injection).

## Affected Assets

The correctness of the agent's own behavior and outputs (agent-integrity):
injected instructions steer the pipeline the agent builds.

## Attack Scenarios

1. **Poisoned documentation**: an attacker plants instructions in a web page,
   README, or code snippet the agent is likely to consult while building the
   pipeline.
2. **Search-result manipulation**: the agent follows a link from search or a
   dependency reference to attacker-controlled content that injects commands.
3. **Chained exploitation**: the injected instructions cause the agent to leak
   data, misuse tools, or run harmful steps (see [[TM-001]]).

## Preconditions

- The agent can fetch and read external web content while planning.
- Fetched content is treated as trusted context rather than untrusted data.
- No provenance separation between the user's request and retrieved content.

## Mitigations

### Preventive

- Treat all fetched web content as untrusted data, not instructions; isolate
  it from the instruction channel.
- Restrict fetches to allow-listed, reputable sources.
- Strip or neutralize instruction-like patterns from retrieved content.

### Detective

- Log fetched URLs and flag content that resembles embedded instructions.
- Monitor for pipeline steps that diverge from the user's stated intent.

### Responsive

- Halt the pipeline and require human review when injection is suspected.
- Revoke access to the offending source and quarantine the session.
