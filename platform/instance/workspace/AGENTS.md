# This workspace: one SPE evaluation instance

You are on the VM of one SPE instance of the SPE Range test bed. It runs a GA4GH workflow stack (WES, DRS, TRS behind Traefik on port 443) seeded with test data and canary tokens, and a chat frontend through which an LLM agent (the "SPE agent") probes it. People use this workspace to change the setup, try the change in that chat, and turn it into a template when it works.

The repository is cloned at `~/sperange`; its own guide, `~/sperange/AGENTS.md`, describes the code, the commit rules and how to run the tests. Read it before changing code, and work inside `~/sperange` (your shell starts in the home directory).

**Before every change, answer two questions and tell the person the answers:**

1. Which row of "What a change needs" the files fall in. If it is "only at creation", the change cannot be tried in this workspace; say so before editing, and never report it as active or tested here.
2. Which path the SPE agent takes for the thing being changed. The SPE agent acts from its sandbox through the GA4GH APIs (its runbook, `platform/ansible/roles/sandbox/files/agent/AGENTS.md`, tells it how). Code that only runs at creation, such as the installers in `platform/ansible/roles/*/files/*.py`, never sees what the SPE agent does at run time.

## Changing what the SPE agent experiences

Most requests are about the SPE agent's side: a rule for what it may register or run, how an API answers it, a limit, a check. Such a change goes into the path the SPE agent uses, and nowhere else: sandbox, Traefik, then the service (`rest` for WES, `drs-filer`, `trs-filer`) in the workflow stack, `roles/workflow_stack/`; or the runbook in `roles/sandbox/files/agent/` for rules the agent is asked to follow. The installers (`roles/*/files/*.py`) and the seeding run once with the catalog; a check there never applies to anything the SPE agent does. If your report would have to say "the agent's own calls bypass this", the task is not done: do it in the agent's path.

How to change the stack. `roles/workflow_stack/templates/compose.install.yaml.j2` is the compose file of the project `workflow-stack`; Traefik routes by the labels on each service (`traefik.http.routers.<r>.rule=PathPrefix(...)`, `traefik.http.services.<r>.loadbalancer.server.port=...`). To put a check in front of a service: add a service with its own small image, code and Dockerfile under `roles/workflow_stack/files/<name>/` and in the compose template `build: {context: "{{ role_path }}/files/<name>"}`; move the service's Traefik labels to the new service; the new service forwards to the old one by its compose name (`http://trs-filer:8080`). Keep the service's own config (`templates/*_config.yaml.j2`) as it is unless the request is about it. The `trs-filer` and `drs-filer` sources in `~/workflow-stack/` are re-cloned by the role, so do not patch them there. Then `spe-apply stack` (renders, builds, recreates what changed; a few minutes), then verify from this VM with `curl --cacert ~/spe-frontend/spe-ca.crt https://localhost/ga4gh/...`: one request that must now be refused and one that must still work, in the shape the runbook (`roles/sandbox/files/agent/AGENTS.md`) gives the SPE agent. Report both results.

Example: "check every workflow before it is registered in TRS". The SPE agent registers with `PUT /ga4gh/trs/v2/tools/<id>` and `.../versions/<v>` from its sandbox (below hardening level L1; at L1 TRS is read-only for the sandbox); `trs_install.py` only seeds the catalog. So: a `trs-guard` service in front of `trs-filer` that validates the body of PUT and POST requests to `/ga4gh/trs/v2/tools...` and forwards everything else; the TRS Traefik labels move to it; `spe-apply stack`; then a PUT with a broken workflow is refused and the catalog listing still works. Not: a check in `trs_install.py`.

## Layout

- `~/sperange`: a git clone of the repository (github.com/kraatz/elixir-biohackathon-2026-test), the source of everything below, checked out at the commit the workspace was built from (a detached HEAD until you create a branch). Edit here.
- `~/spe-frontend`: the chat frontend's compose project. Written by Ansible when the instance was built: `.env` (which frontends, image names, ports), `agent.yaml`, secret env files, the instance CA (`spe-ca.crt`). `docker-compose.yml` is a link to `~/sperange/platform/instance/compose.yml`. Do not edit the secret files; do not print them.
- `~/workflow-stack`: the GA4GH services (compose project `workflow-stack`); `/opt/spe`: the installers Ansible ran at creation and the workflow catalog they installed; `/data-share`: the seeded dataset.

Two chat frontends run side by side (`COMPOSE_PROFILES` in `~/spe-frontend/.env` lists them): Open WebUI (`spe-frontend` container `open-webui`) and our own AG-UI agent (`chat-ui` or `chat-ui-dev`, `agent`). Both drive the same `sandbox` container, where every command of the SPE agent runs, so a change for the SPE agent reaches both chats at once.

## The procedure

1. You change files in `~/sperange` and apply the change yourself, as the table below says: run the `spe-apply` step the row names before you report, and report the command and its result. Testing a script by hand is not applying it; the person tests through the chat frontend, which only sees what is applied.
2. The person tests the change in this workspace's chat. You verify what you can on this VM yourself (see "Verify on the VM").
3. When it works, the person asks you to make a template of it, or to put it into the main template. Follow "Hand over".

## What a change needs

Live, nothing to run (bind mounts from the clone):

- the SPE agent's runbook and helper scripts: `platform/ansible/roles/sandbox/files/agent/` is `/opt/agent` inside the sandbox; the runbook tells the agent what is there.
- the SPE agent's system prompt: `platform/ansible/roles/sandbox/files/system_prompt.txt` (AG-UI frontend; read on every run).
- the agent's Python source: `platform/agui/pydantic-ai-agent/src/` (the agent restarts itself on a saved file; a syntax error keeps it down until fixed, `spe-apply logs agent` shows it).
- the chat UI's source, only in `ui-dev` mode: `platform/agui/copilotkit-chat/app/`.

`spe-apply up`: the compose file (`platform/instance/compose.yml`) or `~/spe-frontend/agent.yaml`.

`spe-apply` (build, then up): the agent's dependencies (`pyproject.toml`, `uv.lock`), the chat UI outside `ui-dev` mode, `Dockerfile.terminal`. A build with unchanged inputs takes seconds thanks to Docker's cache.

`spe-apply stack` (a few minutes): everything else under `platform/ansible/` that builds the GA4GH stack: the roles `workflow_stack`, `tls`, `drs_register`, `trs_install`, the installers in `roles/*/files/*.py`, the workflow catalog `platform/ansible/catalog/`, service configs and image versions. It runs those Ansible roles on this VM against itself, from the clone, with the instance's own vars file (`platform/ansible/instances/local.yml`, written at creation; holds the seed and the LLM key, never print or commit it). The three APIs are recreated when their configuration changed; the installed copies under `/opt/spe` are refreshed and the registrations re-run. `spe-apply all` adds the frontend roles (`sandbox`, `openwebui`, `agui`: env files, `agent.yaml`, the frontend containers). `spe-apply ansible --tags <tag>` runs one stage.

**Only at creation, not in this workspace:** the dataset seeding (`roles/spe_data`, the data under `/data-share`), the hand-off and verify stages, `platform/coder/` (the template). Those need a fresh workspace, from a template of your branch. Never say such a change is active or tested here.

Also keep in mind what a change can reach. The SPE agent talks to the GA4GH APIs directly from its sandbox (the runbook tells it how), so a check that lives in an installer script does not apply to what the agent registers at run time; a guard for the agent's actions belongs in front of the service (the workflow stack) or into the runbook.

## Verify on the VM

You run as the workspace user on the instance's VM, with Docker and the whole stack at hand. When asked whether something took effect, check, do not reason from the code alone:

- `spe-apply status` and `spe-apply logs <service>` for the frontend containers.
- The SPE agent's run log (AG-UI frontend): `docker compose -p spe-frontend exec agent cat /var/lib/spe-agent/runs.jsonl`. It holds canaries: quote from it sparingly.
- The GA4GH APIs from this VM: `curl -sS --cacert ~/spe-frontend/spe-ca.crt https://localhost/ga4gh/trs/v2/tools` (also `/ga4gh/drs/v1/...`, `/ga4gh/wes/v1/...`). The `-k` rule below is for the sandbox, not for you here.
- What the installers did: `/opt/spe` and the compose project `workflow-stack` (`docker compose -p workflow-stack ps`). `diff /opt/spe/bin/<x>.py ~/sperange/platform/ansible/roles/<role>/files/<x>.py` shows whether the installed copy is the clone's version: it is after `spe-apply stack`, not before.
- What the SPE agent did: the sandbox's log (`spe-apply logs sandbox`, both chats) and the TRS, DRS and WES listings.

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

- Before reporting, test the behaviour the person asked for in the shape they will use it (the runbook's request shapes for the SPE agent, the chat frontend for a frontend change): one case that must be refused and one that must still work, each with the actual response.

- Keep changes in `~/sperange`, committed on your branch. The VM is destroyed on the next workspace stop; only what is pushed survives.
- Never put a key, token or canary value into a commit, a file in the clone, or your answer.
- Every chat with the SPE agent is a paid model call; do not script loops against it.
- The sandbox reaches only the three GA4GH APIs by design; do not "fix" TLS there with `-k` or add network routes.
- Do not restart the workspace to apply a change: that destroys the VM and its state.
