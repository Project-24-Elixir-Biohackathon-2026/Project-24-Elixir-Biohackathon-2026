---
id: TM-NNN
name: Short Name of the Threat
description: >
  One or two sentences: what the agent does, or is made to do, and what the
  consequence is. The same text opens the Description section below.
assets:
  - one-or-more-keys-from-vocabulary.yaml
stride:
  - one-or-more-keys-from-vocabulary.yaml
---

# TM-NNN: Short Name of the Threat

## Description

One paragraph. Start from the frontmatter description and add what it leaves
out: the situation in which the threat arises and the mechanism that turns it
into harm.

## Affected Assets

One or two sentences naming the assets from the frontmatter in plain words and
saying what happens to each.

## Attack Scenarios

1. **Scenario name**: who or what triggers the threat, through which entry
   point, and what the agent then does.
2. **Scenario name**: ...

## Preconditions

- What must be true of the agent, its access, or its environment for the
  scenarios above to work. One condition per bullet.

## Mitigations

### Preventive

- Controls that stop the threat from happening.

### Detective

- Controls that notice it happening.

### Responsive

- What to do once it is detected.
