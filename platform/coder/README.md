# sperange portal (Coder)

A self-service portal for SPE evaluation instances. Participants log in, pick a
testbed (a preset from this repo) or set the parameters themselves, and get
their own SPE instance with a chat frontend (Open WebUI, or our own AG-UI
agent with a CopilotKit chat), opened with one click. When they stop or delete the workspace, the run (chats, report,
parameters, canary record) is archived to shared storage and the instance is
torn down.

It is built on [Coder](https://coder.com) (open source, self-hosted). Coder
gives us the login, the dashboard, the parameter form, the presets and the
proxy to each instance's chat frontend. The instance itself is still built by the
Ansible playbooks in `../ansible`; the Coder template only wraps them.

```
 participant browser
        │ https://sperange.<zone>/           (landing page, static)
        │ https://sperange.<zone>/threats/   (threat catalog, static)
        │ https://sperange.<zone>/workspaces (dashboard, Coder)
        │ https://openwebui--main--<ws>--<user>.sperange.<zone>   (app; chat--… the AG-UI chat)
        ▼
 ┌──────────────── portal VM (public FIP) ────────────────────────────┐
 │ Caddy :443 (TLS, Charité PKI) ──▶ platform/site/dist (/, /threats/) │
 │                               ──▶ Coder :7080 (everything else)    │
 │                                    │  workspace build = Terraform  │
 │                                    ▼                               │
 │                     coder/template/main.tf                         │
 │                       start ─▶ ansible create.yml                  │
 │                       stop  ─▶ ansible destroy.yml                 │
 │                                (archive.yml first)                 │
 │ /data-share (Manila, NFS)   ◀── base dataset in, runs/ out         │
 └───────────────▲────────────────────────────────────────────────────┘
                 │ agent dials out to :7080 (private network)
 ┌───────────────┴──────── SPE VM per workspace ───────────────────────┐
 │ coder-agent ─▶ 127.0.0.1:8080 OpenWebUI  or  :3000 CopilotKit chat   │
 │                       └─▶ open-terminal sandbox (the agent's shell)   │
 │ WES / DRS / TRS stack, seeded data, canaries                        │
 └─────────────────────────────────────────────────────────────────────┘
```

## What lives where in the repo

| Path | What it is | Who edits it |
|---|---|---|
| `platform/coder/template/main.tf` | The Coder template: parameters, agent, the frontend apps, the Terraform→Ansible glue | maintainers |
| `platform/coder/template/testbeds/*.yml` | **Testbed presets.** One file = one entry in "Create workspace" | anyone (via PR) |
| `platform/coder/template/run-ansible.sh` | Runs a playbook with the vars Terraform passes | maintainers |
| `platform/coder/deploy/` | Files for the portal VM: systemd units, env examples, Caddyfiles, template sync script | maintainers |
| `platform/site/` | The landing page and the threat catalog page, built from `threats/` (see `platform/site/README.md`) | maintainers |
| `platform/ansible/` | Builds and tears down one instance (see `platform/ansible/README.md`) | maintainers |
| `platform/agui/` | The AG-UI frontend: `pydantic-ai-agent/` and `copilotkit-chat/`, built into images by the `agui` role | maintainers |
| `platform/ansible/reports/run_report.md.j2` | **Run report template**, becomes the pinned "Run report" note in OpenWebUI | anyone (via PR) |
| `platform/ansible/roles/run_archive/` | Exports the frontend's chats (Open WebUI, or the AG-UI chat sessions and the agent's run log) and writes the run directory | maintainers |

### Working in a workspace

A workspace is for changing the setup, trying the change in its chat right
away, and turning it into a template when it works, with Coder Agents (the
portal's chat agent, Admin settings > AI) or by hand over the web terminal. The
VM holds a clone of this repository at `~/sperange`, checked out at the commit the
workspace was built from, and the chat frontend runs from it:

| Change | What it needs |
|---|---|
| the SPE agent's runbook or a helper script (`platform/ansible/roles/sandbox/files/agent/`, mounted at `/opt/agent` in the sandbox) | nothing: live on the next message |
| the SPE agent's system prompt (`platform/ansible/roles/sandbox/files/system_prompt.txt`, the AG-UI agent) | nothing: read on every run |
| the agent's Python source (`platform/agui/pydantic-ai-agent/src/`) | nothing: the agent restarts itself on a saved file |
| the chat UI's source, with `spe_agui_ui_dev: true` (compose profile `ui-dev`) | nothing: hot reload. The first start installs the packages from the npm registry, about two minutes |
| the compose file (`platform/instance/compose.yml`) or `~/spe-frontend/agent.yaml` | `spe-apply up` |
| the agent's dependencies, the chat UI (built mode), `Dockerfile.terminal` | `spe-apply` (build, then up): the **Rebuild** button on the workspace page runs it once and leaves a shell open |
| the GA4GH stack: roles `workflow_stack`, `tls`, `drs_register`, `trs_install`, the installers in `roles/*/files`, the catalog, service configs, image versions | `spe-apply stack`: runs those roles on the VM against itself, from the clone, with `instances/local.yml` written at creation (minutes). `spe-apply all` adds the frontend roles, `spe-apply ansible --tags <tag>` one stage |
| the dataset seeding, hand-off and verify, the Coder template | a fresh workspace from a branch template (below) |

The loop, as the Coder agent is instructed to follow it (`platform/instance/workspace/AGENTS.md`,
reached from the repository's `AGENTS.md`, which it reads at the start of every chat):

1. The agent edits the clone and applies the change as the table says, or says
   that the change only applies at creation. The VM carries `ansible-core`, the
   collections in the clone and the instance's vars file for that (role `repo`;
   the vars file holds the seed and the LLM key, 0600, git-ignored).
2. The person tests the change in the workspace's chat; the agent verifies what
   it can on the VM (container logs, the GA4GH APIs, the SPE agent's run log).
3. On "make a template of it": the agent commits on a branch `template/<name>`
   and pushes it. The sync timer (step 7) turns every such branch into the
   template `spe-<name>` within five minutes, built from that branch's Ansible
   code with the clone on the VM at that branch's commit. A later push updates
   the template; deleting the branch deletes the template once no workspace uses
   it. Workspaces from the main template are not affected.
4. On "put it into the main template": the person opens the pull request from
   that branch (the agent gives the link; it cannot open one); merging updates
   the main template within minutes, existing workspaces pick it up on their
   next start.

Commits in the clone carry the workspace owner's name and email (set by the
template), and pushes use the owner's Coder git key over SSH: see "GitHub access
from workspaces" under step 7. The VM is destroyed when the workspace stops; only
what is pushed survives.

### Adding a testbed

There is one preset, `all-data.yml`: all samples, all tiers, every canary type.
To add one, copy it in `platform/coder/template/testbeds/`, change it, open a PR.
After merge the portal picks it up within 5 minutes (see "Template sync").

```yaml
name: Metadata canaries only          # shown in the preset dropdown
description: Two samples, canaries only in API metadata.
default: false                        # true = preselected (only one preset)
parameters:                           # keys = parameter names in main.tf
  samples: [HG002, HG003]
  tiers: [ref, genomes, registry]
  workflows: [wes-drs-smoke]
  canaries: [drs_metadata, trs_descriptions, workflow_comments, service_info]
  flavor: de.NBI mini
  smoke_test: false
```

Allowed values are the options defined in `main.tf`. A new parameter (e.g. a
new canary type) needs a change in `main.tf` and usually in Ansible first.

### Changing the run report

Edit `platform/ansible/reports/run_report.md.j2` (Jinja2 + Markdown). It is rendered
when an instance is created, so changes apply to new workspaces only. Keep the
note title "Run report" (`spe_report_title`), the archive looks for it.

## For participants

1. Log in at `https://sperange.<zone>`.
2. **Create workspace** → template `spe-testbed` → pick a preset (or adjust the
   parameters) → **Create**. Building takes about 7 minutes for the Open WebUI
   preset (the slow downloads, builds and the data copy overlap); the build
   log is shown live.
3. Click **OpenWebUI** (or **Chat (AG-UI)** for the `agui` frontend). You are
   logged in directly; the agent has a terminal inside the instance.
4. Document as you go (the run report is Open WebUI only; in the AG-UI chat, tag sessions in the sidebar's
   `⋯` menu):
   - Write in the pinned note **Run report** (sidebar → Notes).
   - Tag the chats that matter, in the chat's `…` menu: `report`, plus one
     outcome tag `leak`, `no-leak` or `partial`.
5. **Stop** or **Delete** the workspace when done. Both save the run first,
   then delete the instance. Starting a stopped workspace builds a fresh,
   identical instance (same seed) with empty chats.

Runs are saved to `/data-share/runs/<UTC time>_<instance>/`:

| File | Content |
|---|---|
| `index.md` | Overview: report status, every chat with its tags |
| `report.md` | The "Run report" note |
| `chats/NN-<title>.md` | Each chat, readable: messages, tool calls, tool results, reasoning |
| `chats/NN-<title>.json` | Each chat, raw OpenWebUI format |
| `notes/` | Any other notes |
| `run.yml` | Participant, parameters, seed, versions |
| `canaries.json`, `canaries.manifest.sha256` | The canary record of this instance |
| `openwebui-export.json` | Complete raw export (re-render with `write_run.py`) |
| `agui/` | The AG-UI chat's part of the run: `index.md` (every session, linked from the top `index.md`), and the three rows below |
| `agui/chats/NN-<title>.md`, `.json` | Each AG-UI session, exported as an Open WebUI chat: every branch in `.json`, the active one readable, with run statuses, the content the client sent that was not used, and compactions |
| `agui/agui-journals/` | Every session's journal as written, hidden and deleted included |
| `agui/agent-runs.jsonl` | The agent's run log: every run, tool calls and results |

## Deploying the portal on a new VM

This is the setup the local test on agent-service-1 used (see the end of this
file), adapted for a public VM. Fill in these values first:

| Placeholder | Meaning | Example |
|---|---|---|
| `<zone>` | Portal domain, wildcard record exists | `sperange.bihealth.org` |
| `<fip>` | Public floating IP the DNS points to | `194.94.4.93` |
| `<private-ip>` | Portal VM address in `AIWFEVAL-network-2` | `10.0.2.50` |
| ACME | Directory URL, EAB key id + HMAC key from the Charité PKI | |

DNS needs both `<zone>` and `*.<zone>` → `<fip>`.

### 1. VM and network

- Ubuntu (same image as the instances is fine), flavor `de.NBI small` or larger,
  ≥ 40 GB disk, network `AIWFEVAL-network-2`, floating IP `<fip>`.
- Security group `sperange-portal`:

  | Port | From | Why |
  |---|---|---|
  | 443/tcp | 0.0.0.0/0 | participants |
  | 80/tcp | 0.0.0.0/0 | ACME HTTP-01 challenge, redirect to https |
  | 7080/tcp | 10.0.2.0/24 | Coder agents in the SPE VMs dial in here |
  | 22/tcp | admin networks only | |

  Do not open 7080 to the internet; Caddy is the only public entry.

### 2. Shared storage

The base dataset is read from `/data-share` and runs are written to
`/data-share/runs`. The Manila share (`share-data-1`) only admits client IPs
that have an access rule, and today those are the VMs' internal floating IPs
(`10.57.x.x`), because NFS traffic to `manila-prod.isi.denbi.bihealth.org`
(`10.57.200.13`) leaves through the router with that address.

**Check before relying on it:** a VM with a *public* floating IP may reach
Manila from a different source address, or not at all. On the portal VM:

```bash
nc -zv 10.57.200.13 2049        # NFS reachable at all?
```

Then add an access rule for the address Manila sees (the portal's FIP, or ask
de.NBI support which one), and mount it:

```bash
openstack share access create share-data-1 ip <address> --access-level rw
sudo apt install -y nfs-common
echo 'manila-prod.isi.denbi.bihealth.org:/ifs/denbi/prod/share-12c634e5-44ac-48ce-b886-e6aa7cfc082a /data-share nfs vers=3,hard,proto=tcp,_netdev 0 0' | sudo tee -a /etc/fstab
sudo mkdir -p /data-share && sudo mount /data-share
mkdir -p /data-share/runs
```

If the share cannot be reached from the portal VM, set `spe_runs_root` to a
local directory and sync it to the share from a VM that has it; the base
dataset must still be readable for `spe_data` (`spe_source_data_root`).

### 3. Repo, Ansible, OpenStack credentials

As user `ubuntu`:

```bash
sudo apt install -y git rsync python3-venv age
git clone https://github.com/kraatz/elixir-biohackathon-2026-test.git ~/sperange
python3 -m venv ~/.venv-openstack
~/.venv-openstack/bin/pip install ansible-core openstacksdk python-openstackclient python-manilaclient
cd ~/sperange/platform/ansible
~/.venv-openstack/bin/ansible-galaxy collection install -r requirements.yml -p collections
```

- `~/clouds.yaml`: application credential for project AIWFEVAL, cloud name
  `openstack` (copy from the current controller).
- Ansible reaches the SPE VMs over the private network (`spe_connect_via:
  private`); no extra SSH config needed.

Quick check that the controller side works:

```bash
OS_CLIENT_CONFIG_FILE=~/clouds.yaml ~/.venv-openstack/bin/openstack server list
```

### 4. Coder

```bash
curl -fsSL https://coder.com/install.sh | sh -s -- --method standalone --prefix /usr/local
sudo mkdir -p /etc/sperange
sudo install -m 600 -o ubuntu platform/coder/deploy/coder.env.example /etc/sperange/coder.env
sudo $EDITOR /etc/sperange/coder.env        # zone, LLM key, login method
sudo cp platform/coder/deploy/coder.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now coder
journalctl -u coder -f                      # wait for "View the Web UI"
```

(run from `~/sperange`). Terraform is downloaded by Coder on first use.

`DENBI_LLM_API_KEY` in `coder.env` is the de.NBI LLM key the instances'
OpenWebUI uses; it reaches Ansible through the workspace build environment.

### 5. Caddy and TLS

```bash
sudo apt install -y caddy        # or the official Caddy apt repo for a current version
sudo apt install -y python3-yaml mkdocs-material          # for the static site
sudo mkdir -p /srv/sperange-site && sudo chown ubuntu:ubuntu /srv/sperange-site
python3 platform/site/build.py --out /srv/sperange-site    # the sync timer repeats this (SPE_SITE_DIR)
sudo cp platform/coder/deploy/Caddyfile.example /etc/caddy/Caddyfile
sudo $EDITOR /etc/caddy/Caddyfile           # zone, ACME directory, EAB
sudo systemctl reload caddy
journalctl -u caddy -f                      # certificate obtained?
```

On the apex, Caddy serves `/` and `/threats/` from `/srv/sperange-site` (the
landing page with the Workspaces and Threats entrances, and the threat catalog)
and proxies every other path to Coder, whose dashboard lives at `/workspaces`.
Coder's access URL stays `https://<zone>`. The sync timer (step 7) rebuilds the
site on every run.

The Charité PKI issues wildcard certificates over HTTP-01 for accounts with
wildcard permission. If Caddy refuses to request `*.<zone>` without a DNS
challenge, use `Caddyfile.on-demand.example` instead: every hostname then gets
its own certificate when first opened (the first click on a new workspace's
app takes a few seconds longer).

### 6. First admin and logins

Open `https://<zone>`; the first account created becomes the owner/admin.
Or on the VM:

```bash
coder login https://<zone> --first-user-username admin --first-user-email you@bih-charite.de
```

Participants, either:

- **Password accounts** (simplest for ~10 people):
  `coder users create --username anna --email anna@example.org --login-type password`
  and hand out the password; or
- **GitHub login:** create a GitHub OAuth app (callback
  `https://<zone>/api/v2/users/oauth2/github/callback`), fill the
  `CODER_OAUTH2_GITHUB_*` lines in `coder.env`, restart Coder. Restrict to an
  org/team with `CODER_OAUTH2_GITHUB_ALLOWED_ORGS` / `_TEAMS`.

### 7. Template and template sync

First push by hand, then let the timer keep it in sync with `main`:

```bash
coder tokens create --name sync --lifetime 8760h       # copy the token
sudo install -m 600 -o ubuntu platform/coder/deploy/sync.env.example /etc/sperange/sync.env
sudo $EDITOR /etc/sperange/sync.env         # token, <private-ip>, SPE_SITE_DIR
sudo cp platform/coder/deploy/sperange-sync.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start sperange-sync.service  # first push
sudo systemctl enable --now sperange-sync.timer
```

`sync-template.sh` fast-forwards the checkout to `origin/main`, rebuilds the
static site (`platform/site/build.py`, every run) and pushes the template when
`HEAD` changed (`--force` pushes anyway). It passes two template variables:

- `spe_ansible_dir`: the checkout's `platform/ansible/` directory.
- `coder_agent_url`: `http://<private-ip>:7080`, the address the agents in the
  SPE VMs use. Set it to `""` to use the public URL instead (only if the SPE
  VMs can reach `https://<zone>`, which needs hairpin routing to the FIP).

Workspace builds always run the Ansible code currently checked out, including
for stopping workspaces that were created from an older version.

**Branch templates.** The same run keeps one template per branch named
`template/<name>`: a worktree of the branch under `SPE_BRANCH_DIR` (default
`sperange-branches` next to the checkout, with the checkout's `collections/` and
`output/` linked in), the template `spe-<name>` (prefix
`SPE_BRANCH_TEMPLATE_PREFIX`) pushed from it with the same two variables, display
name `template/<name>`. A push to the branch updates the template; deleting the
branch deletes the template and the worktree, unless workspaces still use it,
then the script says so and keeps it until they are gone (delete the workspaces,
or delete the template in the dashboard once they are). `<name>` must be lowercase
letters, digits and hyphens, 28 characters at most (template names are limited to
32). This is how a change made in a workspace is tried on a fresh workspace
before it is merged ("Working in a workspace").

**GitHub access from workspaces.** The clone's push URL is the SSH form of
`spe_repo_url` (role `repo`, which also installs GitHub's host keys); fetches stay
anonymous over https. Coder keeps one git SSH key per person and the agent sets
`GIT_SSH_COMMAND` to `coder gitssh`, so a push authenticates as that person once
they have added their key to GitHub: Account settings > SSH keys in the portal
shows it, GitHub's Settings > SSH and GPG keys takes it. They also need push
rights to the repository. Until then a push fails at once with "Permission
denied (publickey)" and prints the key to add; the Coder agent is instructed to
relay that and stop. Nothing is set up on the portal for this. (Coder's external
authentication with a GitHub OAuth app would make https pushes work instead, but
without a linked account such a push waits for a login in the browser rather than
failing, which is worse for an agent.)

### 8. Coder Agents on the de.NBI endpoint (optional)

Coder Agents is Coder's built-in chat agent (Admin settings > AI). It runs in
the control plane and can read templates, create workspaces and run commands
in them on the user's behalf, so the portal VM, not the SPE VMs, needs to reach
the LLM. `coder-agents-setup.sh` configures it against our OpenAI-compatible
endpoint without touching the dashboard:

```bash
platform/coder/deploy/coder-agents-setup.sh      # on the portal VM, as ubuntu
```

It creates (or updates) the provider `denbi` with the base URL and the key from
`coder.env`, and the model `gemma-4-31b` as the organization's default; it is
safe to rerun. Not every model on the endpoint works: Coder Agents sends a
system message in the middle of the conversation, which the chat templates of
`qwen3.8-27b` and `mistral-medium-3.5` reject ("System message must be at the
beginning"); `gpt-oss-120b`, `gemma-4-31b` and `glm-5.3` accept it. Everything is a variable (`SPE_LLM_BASE_URL`, `SPE_LLM_MODELS`
as `model:context_limit:display name` separated by commas, …), see the header
of the script. The API details it relies on, found in Coder 2.38's dashboard
client since the docs only show the UI: `POST /api/v2/ai/providers` with type
`openai-compat` and `api_keys: ["<key>"]`, `PATCH .../providers/<id>` with
`api_keys: [{"api_key": "<key>"}]`, and
`POST /api/v2/organizations/<org>/chats/models`.

Once a model exists, every portal user can open a chat with the agent, and the
agent can build workspaces. To keep it away from the testbed template, block
the template for the agent in the dashboard, or create the model with
`"enabled": false` (edit the script) until it has been tried.

### 9. Template settings (optional)

```bash
coder templates edit spe-testbed --default-ttl 12h     # auto-stop after 12 h idle
```

Auto-stop **destroys** the instance (after archiving it). Leave it off during
the hackathon if participants keep sessions open for long; turn it on to stop
forgotten instances from eating quota.

### 9. Smoke test

1. Log in, create a workspace from the Open WebUI preset, wait for "Running".
2. Click **OpenWebUI**: no login prompt, the pinned "Run report" note exists.
3. Ask the agent to list DRS objects; it should run `curl` in its terminal.
4. Tag that chat `report`, write a line in the report, **Stop** the workspace.
5. `/data-share/runs/<time>_cw-<user>-<ws>/index.md` lists the chat with its
   tags and says the report is filled in.
6. `openstack server list` shows no `cw-…-api` server left.

## Operating

| Task | How |
|---|---|
| Logs | `journalctl -u coder`, `journalctl -u caddy`, build logs in the UI (Workspace → Builds) |
| List instances | Coder dashboard (all users: Workspaces, filter off); OpenStack: servers named `cw-<user>-<workspace>-api` |
| Save a run without stopping | on the VM: `ansible-playbook playbooks/archive.yml -e spe_instance=cw-<user>-<ws>` in `ansible/` (instance vars default to `group_vars`; parameters in `run.yml` are then the defaults, not the workspace's) |
| Re-render an old run | first the AG-UI part, `platform/ansible/roles/run_archive/files/write_run.py <run>/agui/openwebui-export.json <run>/agui "Run report"`, then Open WebUI's, `… <run>/openwebui-export.json <run> "Run report"` (it links `agui/` when that is there) |
| Update Coder | re-run the install script, `sudo systemctl restart coder` |
| Back up Coder | stop Coder, archive `~ubuntu/.config/coderv2/` (built-in PostgreSQL) |

**A stop fails at "Archive the run".** Nothing has been deleted. Usually
OpenWebUI on the instance is down; check with `coder ssh <ws>` and
`docker ps`, fix, and stop again. To give up on that run's chats:

```bash
coder delete <user>/<ws> --orphan            # forget it in Coder, keep cloud resources
cd ~/sperange/platform/ansible
OS_CLIENT_CONFIG_FILE=~/clouds.yaml ~/.venv-openstack/bin/ansible-playbook \
  playbooks/destroy.yml -e spe_instance=cw-<user>-<ws> -e spe_archive_skip=true
```

**Leftover cloud resources** (after `--orphan` or a crashed build): look for
servers, security groups and keypairs named `cw-*` and remove them with
`destroy.yml` as above.

## Known limitations

- **OpenWebUI has no login** (`spe_webui_auth: false`); Coder's owner-only app
  access is the gate. The agent's terminal container shares a Docker network
  with OpenWebUI and can reach its API without credentials. A planned fix
  (OpenWebUI on the host network bound to 127.0.0.1, terminal published on
  127.0.0.1:8000) is not built yet.
- **The `agui` frontend has no run report.** Its sessions (with tags) and the agent's run log are
  archived; there is no "Run report" note as in Open WebUI.
- **Stop = destroy.** A stopped workspace keeps nothing but its parameters;
  start rebuilds from scratch (~7 min). Chats survive only in the archive.
- **One run directory per stop.** Starting and stopping the same workspace
  twice gives two run directories.
- **Tags are free text.** OpenWebUI does not enforce the vocabulary; LLM tag
  generation is off so only participant tags appear.
- **Builds use the checkout on the portal VM**, not a copy pinned to the
  template version.

## The local test setup (agent-service-1)

The portal was first tried on agent-service-1 without public access:

- Coder as a **user** unit `coder-spike` (`~/.config/systemd/user/coder-spike.service`,
  env `~/.config/coder-spike/server.env`), access URL `http://localhost:7080`,
  wildcard `*.localhost:7080` (browsers resolve `*.localhost` themselves).
  Reached with `ssh -L 7080:localhost:7080 ubuntu@agent-service-1`.
- `coder_agent_url = http://10.0.2.245:7080` (the template default), security
  group `coder-spike` (7080 from 10.0.2.0/24) on agent-service-1.
- Template pushed by hand from `coder/template/`, runs in `/data-share/runs`.

Teardown once the real portal runs:

```bash
coder delete admin/spike1                       # archives + destroys the instance
systemctl --user disable --now coder-spike
rm -rf ~/.config/coderv2 ~/.config/coder-spike ~/.config/systemd/user/coder-spike.service
openstack server remove security group agent-service-1 coder-spike
openstack security group delete coder-spike
```
