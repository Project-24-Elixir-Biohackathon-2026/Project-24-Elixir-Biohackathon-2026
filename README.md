# SPE Range: threat models for agents in Secure Processing Environments

LLM agents that run workflows and read data inside a Secure Processing Environment
(SPE) open new ways to leak or damage what the SPE protects. This repository holds a
catalog of those threats and the source of the platform that lets you try them.

Use the platform at **<https://sperange.bihealth.org/>**:

- **Threats**: the catalog, browsable and filterable.
- **Workspaces**: your own SPE instance with an agent to attack it.

## Using the platform

1. Log in and click **Workspaces**.
2. **Create workspace**, preset **All data**, **Create**. The instance is ready in
   about 8 minutes: a GA4GH stack (WES, DRS, TRS) with synthetic data and planted
   canaries, and an agent that has a terminal inside it.
3. Open a chat: **Open WebUI** or **AG-UI chat**. Both drive the same agent sandbox.
   Ask the agent to do things and watch its tool calls.
4. Record what you found. In Open WebUI, write in the pinned note **Run report** and
   tag the chats that matter (`report`, plus `leak`, `no-leak` or `partial`). In the
   AG-UI chat, tag sessions in the sidebar.
5. **Stop** or **Delete** the workspace. Both archive the chats and the canary record
   first. A restart builds a fresh instance with the same canaries and empty chats.

The canary record of your instance (what a leak looks like) is kept by the operators
and can be checked against your archived chats.

## The threats

One file per entry in `threats/`, `TM-NNN-short-name.md`:

- **Metadata block** (YAML between `---` lines at the top of the file): id, name, a description of 3 to 5 sentences, status, and the
  entry points, assets and STRIDE categories it touches. Values come from
  `vocabulary.yaml`.
- **Attack scenarios**: who triggers it, through which entry point, what the agent
  then does, with the real commands and endpoints of the stack.
- **Preconditions**: what must hold for the scenarios to work, and whether it holds
  here.
- **Mitigations**: preventive, detective, responsive.

Status: `hypothesised` (written down), `reproduced` (shown on an instance),
`mitigated` (a control blocks it, confirmed by a test).

To add one: copy `threats/TEMPLATE.md` to the next free number, fill it in with
vocabulary keys (extend `vocabulary.yaml` if none fits), run
`uv run --with pyyaml python validate.py`, open a pull request. The site rebuilds
from `main` within minutes.

Beside the threats, `paths/` holds the routes a canary can leave by (`P<n>-*.md`, from
`paths/TEMPLATE.md`) and `mitigations/` the switches that close them (`<id>.yml`: the ladder
levels `L<n>` and contributed ones, each with the Ansible values it sets `on` and `off`).
`experiments/` measures one threat and path against one mitigation (`<name>.yml`; `experiments/README.md`
indexes them), each offered as a preset of the `spe-experiments` workspace template beside the plain `spe`
one. `validate.py` checks all four kinds, including that a mitigation's `off` values are the defaults, that
no two mitigations set the same Ansible key, and that an experiment names real threats, paths and
mitigations.

## The platform

`platform/` is the source of the service: the Ansible playbooks that build an
instance, the portal, the agent with its chat, and evaluations that drive the agent
and assert on its tool calls. Deploying and operating it: [`platform/README.md`](platform/README.md).

`AGENTS.md` has the working rules for contributors and coding agents.
