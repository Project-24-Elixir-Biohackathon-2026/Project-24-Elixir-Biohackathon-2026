# This workspace: one SPE evaluation instance

You are on the VM of one SPE instance of the SPE Range test bed. It runs a GA4GH workflow stack (WES, DRS, TRS behind Traefik on port 443) seeded with test data and canary tokens, and a chat frontend through which an LLM agent (the "SPE agent") probes it. People use this workspace to change the setup, try the change in that chat, and turn it into a template when it works.

## Layout

- `~/sperange`: a git clone of the repository (github.com/kraatz/elixir-biohackathon-2026-test), the source of everything below, checked out at the commit the workspace was built from (a detached HEAD until you create a branch). Edit here.
- `~/spe-frontend`: the chat frontend's compose project. Written by Ansible when the instance was built: `.env` (which frontend, image names, ports), `agent.yaml`, secret env files, the instance CA (`spe-ca.crt`). `docker-compose.yml` is a link to `~/sperange/platform/instance/compose.yml`. Do not edit the secret files; do not print them.
- `~/workflow-stack`: the GA4GH services (compose project `workflow-stack`); `/opt/spe`: the installers Ansible ran at creation and the workflow catalog they installed; `/data-share`: the seeded dataset.

The frontend is either Open WebUI (`spe-frontend` containers `open-webui`, `open-terminal`) or our own AG-UI agent (`chat-ui` or `chat-ui-dev`, `agent`, `sandbox`); `COMPOSE_PROFILES` in `~/spe-frontend/.env` says which.

## The procedure

1. You change files in `~/sperange` and apply the change as the table below says.
2. The person tests the change in this workspace's chat. You verify what you can on this VM yourself (see "Verify on the VM").
3. When it works, the person asks you to make a template of it, or to put it into the main template. Follow "Hand over".

Before you start a change, say which row of the table it falls in, so the person knows whether it can be tried here at all.

## What a change needs

Live, nothing to run (bind mounts from the clone):

- the SPE agent's runbook and helper scripts: `platform/ansible/roles/sandbox/files/agent/` is `/opt/agent` inside the sandbox; the runbook tells the agent what is there.
- the SPE agent's system prompt: `platform/ansible/roles/sandbox/files/system_prompt.txt` (AG-UI frontend; read on every run).
- the agent's Python source: `platform/agui/pydantic-ai-agent/src/` (the agent restarts itself on a saved file; a syntax error keeps it down until fixed, `spe-apply logs agent` shows it).
- the chat UI's source, only in `ui-dev` mode: `platform/agui/copilotkit-chat/app/`.

`spe-apply up`: the compose file (`platform/instance/compose.yml`) or `~/spe-frontend/agent.yaml`.

`spe-apply` (build, then up): the agent's dependencies (`pyproject.toml`, `uv.lock`), the chat UI outside `ui-dev` mode, `Dockerfile.terminal`. A build with unchanged inputs takes seconds thanks to Docker's cache.

**Only at creation, not in this workspace:** everything else under `platform/ansible/` (the roles that build the workflow stack, seed the data, install the catalog workflows with `/opt/spe/bin/*.py`, write `~/spe-frontend`), `platform/coder/`, and the GA4GH images. Ansible ran once from the portal when the workspace was built; nothing on this VM runs it again, and the copies it installed (for example `/opt/spe/bin/trs_install.py`) do not follow the clone. Such a change is tried on a fresh workspace built from a template of your branch: do the edit, commit, and hand over as below. Never say such a change is active or tested here.

Also keep in mind what a change can reach. The SPE agent talks to the GA4GH APIs directly from its sandbox (the runbook tells it how), so a check that lives in an installer script does not apply to what the agent registers at run time; a guard for the agent's actions belongs in front of the service (the workflow stack) or into the runbook.

## Verify on the VM

You run as the workspace user on the instance's VM, with Docker and the whole stack at hand. Use that instead of reasoning from the code alone:

- `spe-apply status` and `spe-apply logs <service>` for the frontend containers.
- The SPE agent's run log (AG-UI frontend): `docker compose -p spe-frontend exec agent cat /var/lib/spe-agent/runs.jsonl`. It holds canaries: quote from it sparingly.
- The GA4GH APIs from this VM: `curl -sS --cacert ~/spe-frontend/spe-ca.crt https://localhost/ga4gh/trs/v2/tools` (also `/ga4gh/drs/v1/...`, `/ga4gh/wes/v1/...`). The `-k` rule below is for the sandbox, not for you here.
- What the installers did at creation: `/opt/spe` and the compose project `workflow-stack` (`docker compose -p workflow-stack ps`).

## Hand over

A change worth keeping is committed on a branch named `template/<name>` and pushed. The portal turns every such branch into its own template within five minutes, `spe-<name>`, and the person can build a fresh workspace from it; a later push to the branch updates the template. Pick `<name>` lowercase, letters, digits and hyphens, at most 28 characters, after the change (`trs-check`, not `my-branch`).

```bash
cd ~/sperange
git switch -c template/<name>            # once; later pushes stay on this branch
git add <the files you changed>          # by name, never -A
git commit -m "<what and why, imperative>"
git push -u origin template/<name>
```

If this workspace was itself built from a branch template, continue on that branch instead of creating one: `git branch -r --contains HEAD` shows it, then `git switch template/<name>`.

Then tell the person: the template `spe-<name>` appears in "Create workspace" within five minutes; a workspace from it has the change built in from the start. When the person wants the change in the main template, give them the pull request link, `https://github.com/kraatz/elixir-biohackathon-2026-test/pull/new/template/<name>`; merging updates the main template within minutes, and existing workspaces pick it up on their next start. You cannot open the pull request yourself.

Pushes go over SSH with the git key the portal holds for the person (origin's push URL; fetches stay anonymous over https). If the push is refused with "Permission denied (publickey)", the message shows that public key and the link to add it: tell the person to add exactly that key to their GitHub account (Settings, SSH and GPG keys) and to make sure they may push to the repository, then push again when they say so. The key is public, quoting it is fine. Do not try tokens, other remotes, or pushing through the SPE agent.

## Rules

- Keep changes in `~/sperange`, committed on your branch. The VM is destroyed on the next workspace stop; only what is pushed survives.
- Never put a key, token or canary value into a commit, a file in the clone, or your answer.
- Every chat with the SPE agent is a paid model call; do not script loops against it.
- The sandbox reaches only the three GA4GH APIs by design; do not "fix" TLS there with `-k` or add network routes.
- Do not restart the workspace to apply a change: that destroys the VM and its state.
