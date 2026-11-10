---
id: TM-016
name: Model exposes training cutoff when queried.
description: >
  The model quite liberally answers questions about the training cutoff date. This aids a potential attacker when verifying the awareness of the model of certain attacks and malicious patterns that have only surfaced after the initial training period.
status: reproduced
entry-points:
  - user-prompt
assets:
  - agent-integrity
stride:
  - information-disclosure
---

# TM-016: Model exposes training cutoff when queried.

## Attack Scenarios

1. **Discovery of model training cutoff**: User prompts the agent to provide information on training cutoff, and what information the model is aware of. This allows a potential attacker to validate the currency of information that the model has, allowing a potential attacker to gauge viability of getting certain attacks past the model.

## Preconditions

- Agent does not prevent querying information on the training cutoff date.

## Mitigations

### Preventive

- Try limiting answering prompts about model domain knowledge and its currency via the system prompt.

### Detective

- Possibly match against certain keywords in the prompt, but this is not a reliable method of mitigation.

### Responsive

- Similarly to detective measures, there is not really a viable response to be done. Best course of action is to simply try to make it more difficult to abuse.
