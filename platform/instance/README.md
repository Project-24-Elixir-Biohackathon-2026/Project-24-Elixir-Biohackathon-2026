# platform/instance

What runs on an SPE instance's VM from the repository clone that Ansible checks out there (`spe_repo_dir`, `/home/ubuntu/sperange`):

| Path | What |
|---|---|
| `compose.yml` | The chat frontend (compose project `spe-frontend`) for both frontends and the sandbox they share, selected by `COMPOSE_PROFILES` in the frontend directory's `.env`. Linked as `spe_frontend_dir/docker-compose.yml`. Mounts the runbook, the prompt and the agent's source from the clone. |
| `spe-apply` | Builds the images the active frontends need from the clone and recreates the containers; `stack`/`all`/`ansible` run the Ansible roles on the VM against itself (with `platform/ansible/instances/local.yml`, written at creation). Linked as `/usr/local/bin/spe-apply`; the workspace's Rebuild button and the Coder agent's skill run it; Ansible runs `spe-apply up` at the end of the frontend roles. |
| `workspace/AGENTS.md` | Instructions for Coder Agents (the repository's `AGENTS.md`, which it reads first, points here on an instance): layout, which change is live, which needs `spe-apply` and which only a new template, how to verify on the VM, how a tested change becomes a branch template, rules. |
| `workspace/skills/` | Skills for Coder Agents, linked as `~/.agents/skills/`. |

The point: a change in the clone is testable in the instance's chat without rebuilding the instance. Runbook, helper scripts, prompt and agent source are live; images need one `spe-apply`; the GA4GH stack and the installers need `spe-apply stack`; the data seeding and the Coder template need a fresh workspace, built from the branch template the portal makes of a pushed `template/<name>` branch. `platform/coder/README.md` ("Working in a workspace") describes the loop.
