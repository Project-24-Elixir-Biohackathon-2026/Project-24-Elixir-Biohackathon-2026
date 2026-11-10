# The portal (Coder)

<https://sperange.bihealth.org/> is [Coder](https://coder.com) behind Caddy. Coder
gives the login, the dashboard, the parameter form, the presets and the proxy to
each workspace's chats. A workspace is one SPE instance, built by the Ansible
playbooks in `../ansible`; the Coder template only wraps them. Stop or delete
archives the run and tears the instance down.

```
 browser ── https://sperange.<zone>/            landing page, /threats/ (static)
            https://sperange.<zone>/workspaces  Coder
            https://openwebui--main--<ws>--<user>.sperange.<zone>   (chat--… the AG-UI chat)
            ▼
 portal VM: Caddy :443 ─▶ platform/site/dist (/, /threats/)
                      ─▶ Coder :7080 (everything else)
                          workspace start ─▶ ansible create.yml
                          workspace stop  ─▶ ansible destroy.yml (archive.yml first)
            /data-share (Manila): base dataset in, runs/ out
            ▲ coder-agent dials in on :7080 over the private network
 SPE VM per workspace: coder-agent, Open WebUI :8080, chat-ui :3000, agent, sandbox,
                       WES/DRS/TRS stack, seeded data, canaries
```

## What is where

| Path | What | Edited by |
|---|---|---|
| `template/main.tf` | The Coder template: parameters, agent, apps, the Terraform-to-Ansible glue | maintainers |
| `template/testbeds/*.yml` | Testbed presets, one file per entry in "Create workspace" | anyone, by PR |
| `template/run-ansible.sh` | Runs a playbook with the vars Terraform passes | maintainers |
| `deploy/` | Portal VM files: systemd units, env examples, Caddyfiles, the sync script, the Coder Agents setup | maintainers |
| `../ansible/reports/run_report.md.j2` | The run report's starting content, rendered at the first build | anyone, by PR |
| `../report/` | The run report service behind the "Report" button (`../report/README.md`) | maintainers |
| `../ansible/roles/run_archive/` | Exports the chats and writes the run directory | maintainers |

## Deploying the portal

Placeholders: `<zone>` (the domain, with a wildcard record), `<fip>` (the public
floating IP), `<private-ip>` (the VM's address on `AIWFEVAL-network-2`), and the
ACME directory with its EAB key from the Charité PKI. DNS: `<zone>` and `*.<zone>`
point to `<fip>`.

**1. VM and network.** Ubuntu, flavor `de.NBI small` or larger, 40 GB disk or more,
network `AIWFEVAL-network-2`, floating IP `<fip>`. Security group: 443 and 80 from
everywhere, 7080 from `10.0.2.0/24` only (the Coder agents in the SPE VMs), 22 from
admin networks. Caddy is the only public entry.

**2. Shared storage.** The base dataset is read from `/data-share`, runs are written
to `/data-share/runs`. The Manila share admits client IPs with an access rule; check
first which address Manila sees from this VM (`nc -zv 10.57.200.13 2049`), then:

```bash
openstack share access create share-data-1 ip <address> --access-level rw
sudo apt install -y nfs-common
echo 'manila-prod.isi.denbi.bihealth.org:/ifs/denbi/prod/share-12c634e5-44ac-48ce-b886-e6aa7cfc082a /data-share nfs vers=3,hard,proto=tcp,_netdev 0 0' | sudo tee -a /etc/fstab
sudo mkdir -p /data-share && sudo mount /data-share && mkdir -p /data-share/runs
```

Without the share, set `spe_runs_root` to a local directory; the base dataset must
still be readable at `spe_source_data_root`.

**3. Repository, Ansible, OpenStack.** As `ubuntu`:

```bash
sudo apt install -y git rsync python3-venv age
git clone https://github.com/kraatz/elixir-biohackathon-2026-test.git ~/sperange
python3 -m venv ~/.venv-openstack
~/.venv-openstack/bin/pip install ansible-core openstacksdk python-openstackclient python-manilaclient
cd ~/sperange/platform/ansible
~/.venv-openstack/bin/ansible-galaxy collection install -r requirements.yml -p collections
```

`~/clouds.yaml` holds an application credential for project AIWFEVAL, cloud name
`openstack`. Check: `OS_CLIENT_CONFIG_FILE=~/clouds.yaml ~/.venv-openstack/bin/openstack server list`.

**4. Coder.** From `~/sperange`:

```bash
curl -fsSL https://coder.com/install.sh | sh -s -- --method standalone --prefix /usr/local
sudo mkdir -p /etc/sperange
sudo install -m 600 -o ubuntu platform/coder/deploy/coder.env.example /etc/sperange/coder.env
sudo $EDITOR /etc/sperange/coder.env        # zone, LLM key, login method
sudo cp platform/coder/deploy/coder.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now coder
journalctl -u coder -f                      # wait for "View the Web UI"
```

`DENBI_LLM_API_KEY` in `coder.env` is the LLM key the instances use; it reaches
Ansible through the workspace build environment.

**5. Caddy and TLS.**

```bash
sudo apt install -y caddy python3-yaml mkdocs-material
sudo mkdir -p /srv/sperange-site && sudo chown ubuntu:ubuntu /srv/sperange-site
python3 platform/site/build.py --out /srv/sperange-site
sudo cp platform/coder/deploy/Caddyfile.example /etc/caddy/Caddyfile
sudo $EDITOR /etc/caddy/Caddyfile           # zone, ACME directory, EAB
sudo systemctl reload caddy && journalctl -u caddy -f
```

Caddy serves `/` and `/threats/` from `/srv/sperange-site` and proxies the rest to
Coder. If Caddy refuses a wildcard certificate over HTTP-01, use
`Caddyfile.on-demand.example`: each hostname gets its own certificate on first use.

**6. First admin and logins.** The first account created at `https://<zone>` is the
admin, or `coder login https://<zone> --first-user-username admin --first-user-email <you>`.

Participants log in with GitHub and must be members of one GitHub organization
(`CODER_OAUTH2_GITHUB_ALLOWED_ORGS`; `_ALLOWED_TEAMS` narrows it to `<org>/<team-slug>`).
Coder checks membership at every login, so leaving the organization ends access.

1. In the organization: Settings > Developer settings > OAuth Apps > New OAuth App.
   Homepage URL `https://<zone>`, callback URL
   `https://<zone>/api/v2/users/oauth2/github/callback`, no device flow. Generate a
   client secret.
2. In `coder.env`: `CODER_OAUTH2_GITHUB_CLIENT_ID`, `_CLIENT_SECRET`,
   `_ALLOW_SIGNUPS=true`, `_ALLOWED_ORGS=<org>`; `sudo systemctl restart coder`.
   `curl https://<zone>/api/v2/users/authmethods` must then show
   `"default_provider_configured":false`: without a client ID, Coder uses its own
   hosted GitHub app (device flow, any GitHub account), so a missing ID is not "off".
3. Invite a participant to the organization (People > Invite member, or
   `gh api -X POST orgs/<org>/invitations -f email=anna@example.org`). After they
   accept, "GitHub" on the login page creates their Coder account; the username is
   their GitHub login.

Password accounts still work (`coder users create --username anna --email anna@example.org --login-type password`).
A password account whose email is also the GitHub email cannot use the GitHub
button until its owner converts it: log in with the password, Account settings >
Security > Single Sign On > GitHub. Private organization membership is read with the
`read:org` scope the login requests, so participants must grant it.

**7. Template and sync.**

```bash
coder tokens create --name sync --lifetime 8760h
sudo install -m 600 -o ubuntu platform/coder/deploy/sync.env.example /etc/sperange/sync.env
sudo $EDITOR /etc/sperange/sync.env         # token, <private-ip>, SPE_SITE_DIR
sudo cp platform/coder/deploy/sperange-sync.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start sperange-sync.service  # first push
sudo systemctl enable --now sperange-sync.timer
```

Every 5 minutes `sync-template.sh` fast-forwards the checkout to `origin/main`,
rebuilds the site and pushes the template when `HEAD` changed, with two variables:
`spe_ansible_dir` (the checkout's `platform/ansible/`) and `coder_agent_url`
(`http://<private-ip>:7080`, what the agents in the SPE VMs dial). Builds always run
the Ansible code currently checked out, also for stopping older workspaces.

**8. Coder Agents** (optional): Coder's built-in chat agent. `deploy/coder-agents-setup.sh`
configures a provider and a model against an OpenAI-compatible endpoint; one run per
endpoint, variables in the script's header. Qwen chat models reject Coder's
mid-conversation system message; `Qwen3-Coder-Next`, `gemma-4-31b` and
`gpt-oss-120b` work. A model behind a small context window needs the
`max_output_tokens` field.

**9. Run reports.** The report behind each workspace's "Report" button is served by
`../report/` (design: `docs/specs/2026-11-06-run-report-service.md`) as its own user,
from the checkout, on `127.0.0.1:7090`:

```bash
sudo apt install -y python3-markdown
sudo useradd --system --no-create-home --shell /usr/sbin/nologin sperange-report
sudo install -d -m 2775 -o ubuntu -g sperange-report /data-share/reports   # setgid: the provisioner's new reports get the group
sudo install -m 640 -o root -g sperange-report platform/coder/deploy/report.env.example /etc/sperange/report.env
sudo cp platform/coder/deploy/sperange-report.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now sperange-report
curl -s http://127.0.0.1:7090/reports/healthz        # ok
```

Then the `@reports` block of `deploy/Caddyfile.example` in the apex site, before the
Coder catch-all, and `sudo systemctl reload caddy`. Restart the unit after a merge
that changes `../report/`: the sync timer moves the checkout, not the process.

**10. Canary hit watcher.** `../report/canary_watch.py` polls every running workspace's instance
over SSH and scans each stopped run's archive, writing hits to `/data-share/canary-hits` for the
pages the report service reads. It runs as `ubuntu` (the user that already owns each instance's
output directory and SSH key), so it is set up after step 9 creates the `sperange-report` group:

```bash
sudo install -d -m 2750 -o ubuntu -g sperange-report /data-share/canary-hits   # setgid: hits stay group-readable
sudo cp platform/coder/deploy/sperange-canary-watch.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now sperange-canary-watch
journalctl -u sperange-canary-watch -n 20     # watching <reports dir> into <hits dir>
```

Restart the unit after a merge that changes `../report/canary_watch.py`, `canary_hits.py`,
`canary_record.py` or `canary_reader.py`: the sync timer moves the checkout, not the process. A
hand check of one instance's reader and matching, without a report sidecar or any write under
`/data-share` (`canary_watch.py --once --output-dir <output dir> --out <path>.jsonl`): useful while
setting the unit up, never a substitute for it.

**Smoke test.** Create a workspace from "All data"; "Report" opens the report page
(editable, "not filled in" state is the template); Open WebUI opens without a login;
ask the agent to list DRS objects (it runs `curl` in its terminal); the AG-UI chat
shows tool calls as cards and the session gets a title; tag the chat `report`, write
a line in the report, stop; the run directory's `index.md` lists the chat, says the
report is filled in and links `agui/index.md`; the report is still open and editable
after the stop; `openstack server list` shows no `cw-…-api` server left.

Optional: `coder templates edit spe-testbed --default-ttl 12h` stops forgotten
workspaces, which destroys their instances after archiving.

## Branch templates

A pushed branch named `template/<name>` becomes the portal template `spe-<name>`
within 5 minutes, built from that branch's Ansible code, with the clone on the VM at
that branch's commit. A push updates it; deleting the branch deletes it once no
workspace uses it. `<name>`: lowercase letters, digits and hyphens, 28 characters at
most. This is how a change is tried on a fresh workspace before it is merged.

## Working in a workspace

The VM holds a clone of this repository at `~/sperange`, checked out at the
workspace's commit, and the chats run from it. Edit there, over the web terminal or
with Coder Agents (`platform/instance/workspace/AGENTS.md` is its guide):

| Change | Needs |
|---|---|
| the runbook or a helper script (`roles/sandbox/files/agent/`), the system prompt (`roles/sandbox/files/system_prompt.txt`), the agent's Python source | nothing, live |
| the chat UI's source with `spe_agui_ui_dev: true` | nothing, hot reload |
| the compose file or `~/spe-frontend/agent.yaml` | `spe-apply up` |
| the agent's dependencies, the chat UI (built mode), `Dockerfile.terminal` | `spe-apply` (the **Rebuild** button) |
| the GA4GH stack roles, installers, catalog, image versions | `spe-apply stack` (`all` adds the frontends, `ansible --tags <tag>` one stage) |
| the data seeding, hand-off, verify, the Coder template | a fresh workspace from a branch template |

To keep a change: commit on a branch `template/<name>` and push, then open the pull
request. Commits carry the workspace owner's identity; pushes use the owner's Coder
SSH key, which must be added to GitHub (Account settings > SSH keys in the portal).
The VM is destroyed when the workspace stops; only what is pushed survives.

## Testbed presets and the run report

A preset is a file in `template/testbeds/`; copy `all-data.yml`, change it, open a PR:

```yaml
name: Metadata canaries only          # shown in the preset dropdown
description: Two samples, canaries only in API metadata.   # 128 characters at most
default: false
parameters:                           # keys = parameter names in main.tf
  samples: [HG002, HG003]
  tiers: [ref, genomes, registry]
  workflows: [wes-drs-smoke]
  canaries: [drs_metadata, trs_descriptions, workflow_comments, service_info]
  flavor: de.NBI mini
  smoke_test: false
```

A new parameter needs a change in `main.tf` and usually in Ansible. The run report
starts from `../ansible/reports/run_report.md.j2` (Jinja2 and Markdown), rendered on
the portal VM at the workspace's first build into `/data-share/reports/<workspace id>.md`
and edited behind the "Report" button (`../report/`); a restart never overwrites it.
Keep the seed out of it: every portal user can read every report.

Beside "Report" is "Canary hits" (`coder_app.hits`, `main.tf`): the canary hit viewer's
participant page, also served by the portal, but narrower — only the workspace's owner and
portal admins may open it; everyone else gets 403 (`../report/README.md`, *Canary hits pages*).

## The run archive

`/data-share/runs/<UTC time>_<instance>/`:

| File | Content |
|---|---|
| `index.md` | Overview: report state, every chat with its tags, link to `agui/` |
| `report.md`, `report.json` | The run report as it was at this stop, and its sidecar (owner, workspace, parameters) |
| `chats/NN-<title>.md`, `.json` | Each Open WebUI chat, readable and raw |
| `notes/` | Other notes |
| `run.yml` | Participant, parameters, seed, versions |
| `canaries.json`, `canaries.manifest.sha256` | The canary record |
| `openwebui-export.json` | The complete raw export |
| `agui/index.md`, `agui/chats/NN-<title>.md`, `.json` | The AG-UI sessions, rendered like Open WebUI chats, with run statuses, ignored client content and compactions |
| `agui/agui-journals/`, `agui/agent-runs.jsonl` | The session journals as written, and the agent's run log |

Re-render a run: `../ansible/roles/run_archive/files/write_run.py <run>/agui/openwebui-export.json <run>/agui`,
then the same with `<run>/openwebui-export.json <run>`.

## Operating

| Task | How |
|---|---|
| Logs | `journalctl -u coder`, `journalctl -u caddy`, `journalctl -u sperange-report`, `journalctl -u sperange-canary-watch`, build logs in the dashboard |
| Reports | `https://<zone>/reports/` (any login), files in `/data-share/reports/` |
| Canary hits, every workspace | `https://<zone>/reports/hits` (Coder owners only, linked from `/reports/`), files in `/data-share/canary-hits/` |
| Instances | Dashboard, all users; OpenStack servers `cw-<user>-<workspace>-api` |
| Archive without stopping | on the portal VM, in `platform/ansible`: `ansible-playbook playbooks/archive.yml -e spe_instance=cw-<user>-<ws>` |
| Update Coder | install the release binary over `/usr/local/bin/coder`, `sudo systemctl restart coder` |
| Back up Coder | stop Coder, archive `~ubuntu/.config/coderv2/` |

**A stop fails at the archive.** Nothing was deleted. Usually a chat on the instance
is down: `coder ssh <ws>`, `docker ps`, fix, stop again. To give up on the chats:

```bash
coder delete <user>/<ws> --orphan
cd ~/sperange/platform/ansible
OS_CLIENT_CONFIG_FILE=~/clouds.yaml ~/.venv-openstack/bin/ansible-playbook \
  playbooks/destroy.yml -e spe_instance=cw-<user>-<ws> -e spe_archive_skip=true
```

Leftover servers, security groups or keypairs named `cw-*` go the same way.

## Limitations

- Open WebUI has no login; Coder's owner-only app access is the gate. GitHub login
  admits every member of the allowed organization; there is no per-person approval.
- Stop destroys the instance. Chats survive only in the archive; every stop writes
  its own run directory.
- Tags are free text; the vocabulary is not enforced.
- Builds use the checkout on the portal VM, not a copy pinned to the template version.
- Every portal user can read every run report (by design); only its owner and admins
  can edit it, and nobody can delete one from the portal.
