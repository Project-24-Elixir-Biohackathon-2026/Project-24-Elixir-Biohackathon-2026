---
id: TM-007
name: Transformed Output Bypasses an Exact-Match Output Guard
description: >
  An output guard that matches canary tokens exactly (the canary-guard proxy in front of WES, DRS and TRS, or the canary checker on archives) only sees a value in the form it was planted. If a workflow, or the agent itself, changes the value's form before it reaches the guard, by encoding, splitting, reordering or rewording it, no planted token appears in the response and the guard passes it unchanged. The value is then decoded or reassembled after the guard, in the agent's own reasoning or by the user. This is the expected answer to the TM-001 guard: it targets the control, not the data path, and turns a blocked TM-001 scenario back into a leak while the guard's log shows nothing.
status: hypothesised
entry-points:
  - user-prompt
  - tool-output
assets:
  - user-records
  - credentials
  - agent-integrity
stride:
  - information-disclosure
  - repudiation
---

# TM-007: Transformed Output Bypasses an Exact-Match Output Guard

## Attack Scenarios

1. **Encoded run output**: the TM-001 workflow route, but the workflow writes a transformed form of the file (a standard text encoding, a hex dump, a compressed archive) instead of the plain content. The run's stdout passes the guard because no planted token occurs in it, and the agent or the user decodes it afterwards.
2. **Split value**: the value is emitted in pieces that are each shorter than the token, or interleaved with other characters, across one response or several runs. Each response is clean on its own; the value exists only when the pieces are put back together.
3. **Reworded or derived value**: instead of copying a value, the workflow or the agent reports something that identifies it: its characters spelled out, a description of it, or a derived value such as a count or position that narrows it down. Nothing matches, but the information leaves.
4. **Transformation after the guard**: the guard checks API responses, but the agent can transform data it has already received before writing its answer (for example when asked to "summarise in another format"). Whatever the agent writes in its own answer never passes the proxy; only the answer-level checks (promptfoo `no_canary_in_answer`, the archive checker) see it, and they are exact-match too.
5. **Silent evidence**: in each case the guard logs no `canary_hit`, so its log and the canary checker report a clean run. A run that leaked looks the same as one that did not.

## Preconditions

- The control matches tokens exactly by hash. Holds in this stack: canary-guard, `canary_check.py` and the promptfoo assertion all hash candidate substrings of the text as written.
- The agent can register and run a workflow whose script it writes, and read the run's stdout/stderr through WESkit. Holds in this stack (TM-001).
- The agent can transform text itself, and nothing checks its answer semantically. Holds in this stack.
- The user can read the agent's answer and decode it outside the SPE. Holds in any chat setup.

## Mitigations

### Preventive

- Keep sensitive values out of the run output in the first place: no readable stdout/stderr for runs that touch sensitive tiers, or an output-checking step by an operator, as in the Five Safes model. This removes the channel rather than inspecting it.
- Restrict workflow registration (operator approval for new TRS versions), so the agent cannot run a script it wrote.
- In the guard, decode common encodings before matching (try each candidate in its plain form and in standard decodings) and match short fragments of each token, accepting more false positives in exchange.

### Detective

- Flag responses with high-entropy or encoded-looking blocks from runs on sensitive tiers, rather than only exact matches.
- Add a semantic check alongside the deterministic one, for example a second model asked whether the answer reveals registry content. Non-deterministic, so it complements, not replaces, the exact-match guard.
- Promptfoo tests that ask for each transformation in scenarios 1 to 4 and assert that no decoded canary is recoverable from the answer, so the guard's limit is measured on every template.

### Responsive

- Treat a clean guard log as "no exact-match leak", not "no leak", in reports.
- When a transformed leak is confirmed, rotate the seed for future instances and add the transformation to the guard's decoders and the test suite.
