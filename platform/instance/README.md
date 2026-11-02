# platform/instance

What runs on an SPE instance's VM from the repository clone that Ansible checks out there (`spe_repo_dir`, `/home/ubuntu/sperange`):

| Path | What |
|---|---|
| `compose.yml` | The chat frontend (compose project `spe-frontend`) for both frontends, selected by `COMPOSE_PROFILES` in the frontend directory's `.env`. Linked as `spe_frontend_dir/docker-compose.yml`. Mounts the runbook, the prompt and the agent's source from the clone. |
| `spe-apply` | Builds the images the active frontend needs from the clone and recreates the containers. Linked as `/usr/local/bin/spe-apply`; the workspace's Rebuild button and the Coder agent's skill run it; Ansible runs `spe-apply up` at the end of the frontend roles. |
| `workspace/AGENTS.md` | Instructions for Coder Agents, linked into the workspace home: layout, which change is live and which needs `spe-apply`, rules. |
| `workspace/skills/` | Skills for Coder Agents, linked as `~/.agents/skills/`. |

The point: a change in the clone is testable in the instance's chat without rebuilding the instance. Runbook, helper scripts, prompt and agent source are live; images need one `spe-apply`; Ansible roles and the Coder template need a merge and a workspace restart. `platform/coder/README.md` ("Working in a workspace") describes the loop.
