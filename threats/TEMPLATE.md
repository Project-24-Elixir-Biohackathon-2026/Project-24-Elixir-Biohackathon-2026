---
id: TM-NNN
name: Short Name of the Threat
description: >
  Three to five sentences, the only description there is: what the agent does or is made to do, the mechanism that turns it into harm, and what in this stack makes it possible.
status: hypothesised
entry-points:
  - one-or-more-keys-from-vocabulary.yaml
assets:
  - one-or-more-keys-from-vocabulary.yaml
stride:
  - one-or-more-keys-from-vocabulary.yaml
---

# TM-NNN: Short Name of the Threat

## Attack Scenarios

1. **Scenario name**: who or what triggers the threat, through which entry point, and what the agent then does. Name the real commands, endpoints and files of the stack where you can.
2. **Scenario name**: ...

## Preconditions

- What must be true of the agent, its access or its environment for the scenarios above to work. One condition per bullet; say whether it holds in this stack.

## Mitigations

### Preventive

- Controls that stop the threat, preferably enforced outside the model.

### Detective

- Controls that notice it happening: canaries, logs, promptfoo assertions.

### Responsive

- What to do once it is detected.
