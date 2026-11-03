---
id: TM-005
name: Untrusted Pasted Text as Supplementary Context
description: >
  The user copy-pastes a large piece of text as context for building the
  pipeline; the text may originate from untrusted sources and carry injected
  instructions with malicious intent (prompt injection).
assets:
  - agent-integrity
stride:
  - tampering
agent-capabilities:
  - context-ingestion
related:
  - TM-003
  - TM-004
  - TM-007
references:
  - "OWASP LLM01: Prompt Injection"
last_reviewed: 2026-07-15
---

# TM-005: Untrusted Pasted Text as Supplementary Context

## Description

The user copy-pastes a large piece of text as supplementary context for
building the pipeline. This can happen precisely because file uploads are
prohibited, so the user routes the same untrusted content through the chat
channel instead. The pasted text may originate from untrusted sources and
carry embedded instructions with malicious intent that the agent ingests and
acts upon (prompt injection).

## Affected Assets

The correctness of the agent's own behavior and outputs (agent-integrity):
injected instructions in the pasted text steer the pipeline the agent builds.

## Threat Categories (STRIDE)

- **Tampering**: manipulated pasted content alters the agent's reasoning and
  the resulting pipeline.

## Attack Scenarios

1. **Copied from untrusted origin**: the user pastes text (docs, snippets,
   logs) copied from a source an attacker controls, carrying hidden commands.
2. **Upload-restriction bypass**: because uploads are blocked, the same
   untrusted content enters through copy-paste, evading file-level controls.
3. **Chained exploitation**: injected instructions cause data leakage or tool
   misuse (see [[TM-001]]).

## Preconditions

- The agent ingests large pasted text into its working context.
- Pasted content is treated as trusted context rather than untrusted data.
- Controls applied to uploads are not applied to pasted input.

## Mitigations

### Preventive

- Treat pasted context as untrusted data isolated from the instruction
  channel, with the same rigor as uploaded files.
- Neutralize instruction-like patterns in supplied context.

### Detective

- Flag large pasted blocks that resemble embedded instructions.
- Monitor for pipeline steps that diverge from the user's stated intent.

### Responsive

- Halt the pipeline and require human review when injection is suspected.
- Quarantine the session on detection.
