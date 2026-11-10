---
id: TM-008
name: Adversarial Compaction Erodes the Agent's Rules
description: >
  The agent compacts its own history when it nears the context window, replacing the older turns with
  a model-written summary and continuing from that. An attacker who fills the context with large tool
  outputs or many turns can force a compaction whose summary quietly drops the runbook's prohibitions
  or the user's standing instructions, so afterwards the agent does what it earlier refused — with no
  forged marker, unlike TM-005. The summary then persists in the session journal and the archive as a
  faithful record, so the erosion is invisible after the fact.
status: hypothesised
entry-points:
  - tool-output
  - user-prompt
assets:
  - agent-integrity
  - system-prompt
stride:
  - tampering
---

# TM-008: Adversarial Compaction Erodes the Agent's Rules

## Attack Scenarios

1. **Flood to trigger**: the user asks for work that returns very large tool output (read a big file, list everything verbose), repeated until the history crosses the compaction trigger (0.8 of the window). The agent summarises the older turns to stay under the limit.
2. **Rule lost in the summary**: a safety-relevant turn — the runbook's "No" column, or an earlier user instruction such as "never submit a run without asking me" — falls into the summarised region. The summariser, optimising for brevity, omits it. The agent continues believing no such rule was ever set.
3. **Forbidden action after compaction**: a request that the agent refused before compaction now succeeds, because the refusal and its reason are gone from the context. The system prompt survives (it is re-sent), but anything that lived only in the conversation does not.
4. **Durable misrecord**: the summary is written into the journal with an `spe-compaction-` id and archived. A reviewer reading the archive sees a plausible summary, not the rule that was dropped, so the erosion leaves no trace.

## Preconditions

- Compaction is on and summarises older turns with the same model (`spe_agent_compaction_enabled`, default true). This holds in this stack.
- An attacker can drive the history size through tool output or turn count within one run (the per-run caps are 50 requests, 100 tool calls — room to compact up to three times). This holds.
- Some safety-relevant content lives only in the conversation, not in the re-sent system prompt. True for any user-set standing instruction, and for runbook text the agent read as a tool result rather than from the prompt.

## Mitigations

### Preventive

- Keep every hard rule in the system prompt (always re-sent), never only in a tool result or an earlier turn, so compaction cannot drop it.
- Pin safety-relevant user instructions outside the compactible region: carry them forward verbatim into every summary, or exclude them from summarisation.
- Enforce the high-impact rules outside the model (operator approval for runs and new workflow versions, egress blocking), so a summary that forgets a rule cannot act on the omission.

### Detective

- A threat-eval case that fills the context to force a compaction, then issues a request the agent refused earlier in the same run, and asserts it still refuses.
- Compare a run's compaction summaries (recorded in the run log and journal) against the turns they replaced; flag a summary that drops a prohibition.

### Responsive

- Treat a post-compaction action that contradicts an earlier refusal as a reproduced instance; cancel the run and review the summary against the dropped turns.
- Narrow the trigger ratio or raise the window for the affected model so compaction fires less often mid-task.
