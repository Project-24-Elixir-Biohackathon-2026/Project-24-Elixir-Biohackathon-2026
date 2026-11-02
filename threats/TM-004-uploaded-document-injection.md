---
id: TM-004
name: Untrusted Uploaded Documents as Supplementary Context
description: >
  The user uploads documents as supplementary context for building the
  pipeline; those documents are untrusted data that third parties may have
  tampered with to carry malicious intent (prompt injection).
assets:
  - agent-integrity
stride:
  - tampering
---

# TM-004: Untrusted Uploaded Documents as Supplementary Context

## Description

The user provides documents (for example, by uploading files) as supplementary
context for building the pipeline. Even though the upload originates from the
user, the documents themselves are another source of untrusted data: a third
party may have tampered with them, embedding instructions with malicious intent
that the agent then ingests and acts upon (prompt injection).

## Affected Assets

The correctness of the agent's own behavior and outputs (agent-integrity):
tampered document content steers the pipeline the agent builds.

## Attack Scenarios

1. **Tampered upload**: an attacker-modified document (or one the user received
   from an untrusted party) contains hidden instructions the agent follows.
2. **Hidden payloads**: instructions concealed in metadata, comments, white
   text, or non-visible fields of the uploaded file.
3. **Chained exploitation**: injected instructions cause data leakage or tool
   misuse (see [[TM-001]]).

## Preconditions

- The agent ingests uploaded documents into its working context.
- Uploaded content is treated as trusted context rather than untrusted data.
- No sanitization or provenance separation for user-supplied files.

## Mitigations

### Preventive

- Treat uploaded documents as untrusted data isolated from the instruction
  channel.
- Extract only the intended content (strip metadata, hidden text, macros).
- Constrain accepted file types and sizes.

### Detective

- Scan uploads for instruction-like or anomalous embedded content.
- Monitor for pipeline steps that diverge from the user's stated intent.

### Responsive

- Halt the pipeline and require human review when injection is suspected.
- Quarantine the offending document and the session.
