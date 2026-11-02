# Threat catalog

What the SPE instances are tested for: each threat an AI agent poses, or is exposed to, inside a Secure Processing Environment, written against the stack the instances run.

- [All threats](../all-threats.md): one table, sortable and filterable.
- **Threats**: one page per entry, in the navigation.
- **Metadata**: what each field of an entry means and every value it can take.

## How to read an entry

Every entry has the same shape. Under its heading: the description, then its [status](../metadata/status.md), [entry points](../metadata/entry-points.md), [assets](../metadata/assets.md) and [STRIDE](../metadata/stride.md) categories. Then three sections:

- **Attack Scenarios**: who or what triggers the threat, through which entry point, and what the agent then does, with the real commands, endpoints and files of the stack.
- **Preconditions**: what must be true of the agent, its access or its environment for the scenarios to work.
- **Mitigations**: preventive (stop it), detective (notice it) and responsive (what to do once detected).

The entries are Markdown files with a YAML header in the repository's `threats/` directory; a validator holds every entry to the template and to the controlled values. Each page links to its source file at the end.
