---
id: P<n>
name: Short Name of the Path
description: >
  One or two sentences: the concrete route through the stack that reaches the canaries below.
reaches:
  - one-or-more-canary-types, the spe_canary_<type> keys of group_vars/all.yml
---

# P<n>: Short Name of the Path

## Route

The steps the agent (or an attacker through it) takes, with the real endpoints of this stack (DRS
`/ga4gh/drs/v1`, TRS `/ga4gh/trs/v2`, WES `/ga4gh/wes/v1`, the sandbox).

## Shown by

The controls probe (`platform/promptfoo-evals/probes/*.sh`) or agent test
(`platform/promptfoo-evals/tests/*.yaml`, `metadata.path`) that demonstrates this path open.
