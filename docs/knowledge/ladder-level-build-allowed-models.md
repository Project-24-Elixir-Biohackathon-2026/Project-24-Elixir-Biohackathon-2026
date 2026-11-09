# Building a ladder level on denbi-agui-01: `spe_agent_allowed_models` and `-e key='[]'`

**Symptom.** `create.yml -e @instances/denbi.yml -e @instances/L0.example.yml` fails at
`agui : AG-UI frontend settings are valid`, before any model call (seen 2026-11-09, slice 4's L0 build).
`instances/denbi.yml` pins the dev VM's Anthropic model with a spend guard
(`spe_agent_allowed_models: [claude-haiku-5-5]`, `denbi-anthropic-haiku.md`), and every level file switches the
agent back to de.NBI's `qwen3.8-27b`, which the guard rejects.

**The trap.** `-e spe_agent_allowed_models='[]'` fails the same way: the `key=value` form of `-e` makes `[]` the
two-character *string* `"[]"`, not an empty list (`"qwen3.8-27b" in "[]"` is a substring check, false), and a
`debug` of it prints `[]` like a list. Pass typed values as JSON:

```bash
SPE_LLM_API_KEY=… ansible-playbook playbooks/create.yml -e @$PRIVATE/instances/denbi.yml \
  -e @instances/L0.example.yml -e '{"spe_agent_allowed_models": []}' -e spe_output_root=$PRIVATE/output </dev/null
```

The guard stays in the private file for every other use of the VM; only that command widens it. With no working
de.NBI key (`denbi-llm-key.md`), slice 4 built with a placeholder `SPE_LLM_API_KEY` (no model call:
`spe_agui_smoke: false`); a level that runs the agent suite needs a real one.
