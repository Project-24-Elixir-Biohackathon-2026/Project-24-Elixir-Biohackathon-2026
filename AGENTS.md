# elixir-biohackathon-2026-test

Threat models for agents in Secure Processing Environments (SPEs) and the
Ansible automation that builds SPE evaluation instances. This file is the
guide for humans and coding agents working in this repository.

**On an SPE instance VM** (a portal workspace: `~/spe-frontend/.env` exists and this
file sits in `~/sperange`), read `platform/instance/workspace/AGENTS.md` first. It says
what a change needs there (nothing, `spe-apply`, or a new template), how the person
tests it, and how a tested change becomes a template.

| Path | What |
|---|---|
| `threats/`, `vocabulary.yaml`, `validate.py` | Threat model catalog (`TM-NNN-*.md`, new entries start from `threats/TEMPLATE.md`), its controlled vocabulary and validator |
| `platform/ansible/` | Playbooks that create, verify, archive and destroy one SPE instance (`platform/ansible/README.md`) |
| `platform/coder/` | The self-service portal (Coder) that runs those playbooks for participants (`platform/coder/README.md`) |
| `platform/site/` | The landing page and the threat catalog page served next to the portal, built from `threats/` (`platform/site/README.md`) |
| `platform/agui/` | The AG-UI frontend: `pydantic-ai-agent/` (Pydantic AI agent served over AG-UI) and `copilotkit-chat/` (Next.js + CopilotKit chat) |
| `platform/instance/` | What runs on an instance from the repository clone there: the frontend's compose file, `spe-apply`, the workspace instructions for Coder Agents (`platform/instance/README.md`) |
| `platform/promptfoo-evals/` | promptfoo provider, assertions and starter suite against an instance's agent |
| `platform/dev/` | Development helpers: dummy dataset generator, scripted agent, tests for host-side scripts |
| `docs/getting-started.md` | Deploying and using an instance by hand, and its private configuration |
| `docs/specs/`, `docs/plans/` | Design specs and implementation plans |

## Working rules

- **Commit each coherent change** with a short imperative subject, and add a body saying why when the subject doesn't. Run `git status` and `git diff --staged` first, and stage files by name rather than with `git add -A`.
- **Never commit secrets**: real instance files (`platform/ansible/instances/*.yml` other than `example.yml` and `*.example.yml`, ignored by git) carry the seed that reproduces every canary. Also never commit `platform/ansible/output/`, `canaries.json`, keys, `clouds.yaml` or `.env` files.
- **Push only as the last step of a unit of work** (below): a fast-forward of the working branch. Never rewrite history or force-push.
- **Paid model calls need the human's OK** before they run. On this repository's development VM the agent uses Anthropic with `claude-haiku-5-5`, pinned by `spe_agent_allowed_models` in that VM's instance file (a spend guard for that VM). Other setups choose their own provider and model.
- **Follow the plan's rulings discipline**: when work departs from a plan, record the decision, why, and its cost if wrong in that plan's progress file.

## Lifecycle of a unit of work

A unit of work is a coherent change: a fix, a feature, a docs update. Each is
done in its own worktree and ends on `main` through a pull request, so the
remote always shows the current state.

1. **Create a worktree** on a topic branch from `main`:
   `git worktree add <path> -b <topic> main`.
2. **Commit** in the worktree, as in the working rules above.
3. **Push the topic branch and open a pull request** against `main`. If `main`
   has moved on, merge or rebase the topic branch; never force-push `main`.
4. **Clean up the worktree** after the merge: `git worktree remove <path>` and
   `git branch -d <topic>`. Check first that it has no uncommitted changes.

The portal VM follows `main` (`platform/coder/deploy/sync-template.sh`): a merge
to `main` changes what participants get within minutes.

Private instance files and `platform/ansible/output/` exist only in the main checkout,
not in a worktree. An instance runs the chat frontend from a clone of this repository
on its VM, checked out at the commit the controller's checkout is at, so that commit
must be pushed. To deploy a topic branch before it is merged, push it and run Ansible
from the main checkout with `-e spe_repo_ref=<branch>`. Inside a workspace, edits to
the clone are live or applied with `spe-apply` (`platform/coder/README.md`, "Working
in a workspace").

When this repository is a submodule (of `biohackathon`), the parent records the
pinned commit; move the pin there after the push.

## Running things

```bash
uv run --with pyyaml python validate.py              # threat catalog
uv run --with pyyaml --with mkdocs-material python platform/site/build.py   # landing page + catalog -> platform/site/dist/
uv run --with pytest --with pyyaml --with mkdocs-material pytest platform/dev/tests -q   # dataset generator, host preflight, site build, archive
(cd platform/agui/pydantic-ai-agent && uv run --group dev pytest -q)   # agent
(cd platform/promptfoo-evals && uv run --group dev pytest -q)          # promptfoo provider and assertions
(cd platform/agui/copilotkit-chat && npm ci && npm run build)          # chat UI (type check)
(cd platform/agui/copilotkit-chat && npm ci && npm test)               # chat UI (sessions, recorder, API)
cd platform/ansible && ansible-playbook playbooks/create.yml -e @instances/NAME.yml </dev/null
```

Ansible needs a blocking stdin here: always run it with `</dev/null`, from
`platform/ansible/`. The collections come from the system Ansible package.

## Coder portal

`platform/coder/` is a self-service portal (Coder) that runs the playbooks for
participants, proxies the chat frontend into the browser and archives each run on
stop (`platform/coder/README.md`). Testbed presets are `platform/coder/template/testbeds/*.yml`.
A pushed branch named `template/<name>` becomes its own portal template `spe-<name>`
within minutes, for trying creation-time changes (Ansible roles, the template) on a
fresh workspace before they are merged.

## AG-UI agent frontend

Built from plan `docs/plans/2026-10-15-agui-frontend.md` and spec
`docs/specs/2026-10-15-agui-frontend-design/` (§12: what implementation verified
and changed) on branch `agent-agui-frontend`. The record of the work, every
deviation from the plan with its cost if wrong, and the acceptance evidence is
[`docs/plans/2026-10-15-agui-frontend-progress.md`](docs/plans/2026-10-15-agui-frontend-progress.md).
How to deploy and use it: [`docs/getting-started.md`](docs/getting-started.md).

All 13 tasks are done, including the model-backed checks on the development VM
(Anthropic `claude-haiku-5-5`) and on de.NBI (`qwen3.8-27b`). Merged into `main`
on 2026-10-19 together with the Coder portal, which runs it on every instance
next to Open WebUI (`spe_frontends`). Since then the spec, now a directory with
one file per section, has grown chat sessions (§6), the conversation record that
`chat-ui` owns (§13, threat TM-005), the archive of AG-UI chats (§14) and
compaction with `/compact` (§15); its `clarifications.md` records each change.
Not done yet: a run-report equivalent in the CopilotKit chat.
