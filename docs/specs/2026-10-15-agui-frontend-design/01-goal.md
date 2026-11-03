## 1. Goal

Each SPE instance can run a pentest agent that **we own** — a Pydantic AI
agent served over AG-UI — with a minimal CopilotKit chat in front of it,
instead of Open WebUI running the agent loop. The agent is its own HTTP
endpoint, so promptfoo (and later other agents) can test it without a UI.

Selected per instance with `spe_frontend: agui`. `spe_frontend: openwebui`
keeps working unchanged in behaviour.

First deployment target: **one SPE on one VM that already exists** — first
this development VM (§7.1), then a de.NBI VM once SSH access is back. VM
creation by the playbooks is skipped for now (we may not have the
OpenStack rights to create VMs); §7.0 adds the mode that configures an
existing VM. Several SPEs are deferred to sub-project 2.

Success means:

1. `create.yml` with `spe_provision: existing` and `spe_frontend: agui`
   configures an existing VM end to end — SPE stack, sandbox, agent and
   chat — idempotently.
2. Its checks pass: health, the LLM-key boundary, and one smoke run over
   AG-UI.
3. An operator chats with the agent through an SSH tunnel and sees each
   tool call it makes.
4. A promptfoo suite runs from the controller against the agent endpoint
   and can assert on both the answer and the tool calls.
