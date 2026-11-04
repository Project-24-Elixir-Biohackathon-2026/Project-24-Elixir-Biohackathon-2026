# spe-ansible

Creates isolated SPE evaluation instances in the de.NBI OpenStack project
AIWFEVAL: one VM per instance running WESkit (WES), drs-filer (DRS),
trs-filer (TRS) and Traefik, seeded with its own copy of the test dataset,
its own synthetic registry and its own canary tokens. Every instance starts
from a fresh, identical state defined by a parameter file.

## Controller requirements

For an instance on a VM that already exists (`spe_provision: existing`), most
of what follows is not needed: see [`docs/getting-started.md`](../docs/getting-started.md).
The list below is for creating VMs in OpenStack.

- Python 3 with `ansible-core`, `openstacksdk` (the venv `~/.venv-openstack`
  on spe-ga4gh-api-2 has both; `source ~/.venv-openstack/bin/activate`).
- Collections: `ansible-galaxy collection install -r requirements.yml -p collections`.

Local re-apply: on an instance, role `repo` leaves the clone with the collections
installed and `instances/local.yml` (the vars the controller passed, the seed and
the LLM key, 0600, git-ignored), so `spe-apply stack|all|ansible` can run this
playbook on the VM against itself (`spe_local_apply: true`: no clone update, no
data copy, no hand-off or verify). `spe_manifest_provision` keeps the manifest's
provision mode for destroy.yml. See `platform/instance/README.md`.
- `~/.config/openstack/clouds.yaml` (or `OS_CLIENT_CONFIG_FILE`) with an
  application credential for the project; cloud name `openstack`.
- The base dataset readable at `spe_source_data_root` (default `/data-share`):
  `ref/` and the four GIAB sample directories listed in `spe_source_samples`.
- `rsync` and SSH access from the controller to the private network
  (`spe_connect_via: private`) or to floating IPs (`floating`).
- Optional: `age` for encrypting the canary record (`spe_age_recipient`).

## Usage

```bash
cp instances/example.yml instances/eval-07.yml   # set spe_instance and spe_seed
# existing VM with the AG-UI agent: start from instances/denbi.example.yml or
# dev-local.example.yml instead (docs/getting-started.md)
export DENBI_LLM_API_KEY=...                      # LLM key for the OpenWebUI frontend
ansible-playbook playbooks/create.yml  -e @instances/eval-07.yml
ansible-playbook playbooks/verify.yml  -e @instances/eval-07.yml   # endpoints + smoke run
ansible-playbook playbooks/archive.yml -e @instances/eval-07.yml  # save chats + report now
ansible-playbook playbooks/destroy.yml -e @instances/eval-07.yml  # archives first, then deletes
```

Instances are normally created through the Coder portal (`../coder/README.md`),
which runs these same playbooks.

`create.yml` is idempotent: re-running converges an existing instance and
changes nothing when nothing differs. Use `--tags stack`, `--tags trs` etc.
to run a single stage against an existing instance (the provisioning play
still runs first to find the host).

Real instance files carry the seed, which reproduces every canary: the
repository ignores `instances/*.yml` except `example.yml` and
`*.example.yml`.

### Configuring an existing VM

When VMs cannot or should not be created, set `spe_provision: existing` and
name the VM: `spe_existing_host` (an alias from `~/.ssh/config`, or
`localhost` for the controller itself) and `spe_existing_api_ip` (the VM's
own IPv4 address, used in the certificate). Optional: `spe_existing_ssh_key`
and `spe_existing_ssh_args` (for example `-F ~/.ssh/config` to go through a
jump host; rsync uses them too). OpenStack is not touched.

Before anything changes, a read-only preflight
(`roles/existing_host/files/spe_preflight.py`) checks passwordless sudo and
refuses the host when it is not free for this instance: `/etc/spe-instance`
names another instance; `spe_stack_dir`, `spe_frontend_dir` or
`spe_data_root` already exist, are symlinks, are unsafe (`/`, a home
directory) or overlap Docker's data root; port 443 or a frontend port is
taken by something other than this instance's compose project; a
`workflow-stack` or `spe-frontend` compose project already has containers;
or the data or Docker filesystem has less than `spe_min_free_gb` free. On
a host this instance already owns, everything must match the ownership
manifest `/etc/spe-instance.json` written by the first run (resolved paths
and compose projects): the marker alone excuses nothing. Set
`spe_manage_docker: false` when Docker on the host is managed by something
else; `base` then leaves its packages, `daemon.json` and service alone.
`instances/dev-local.example.yml` configures the development VM itself.

Tested on the agentvm development VM (dummy dataset, spe_manage_docker: false), 2026-10-15.

`destroy.yml` never deletes an existing VM. It resets it — compose stacks
down with their volumes, the stack, frontend and data directories, the CA
anchor, the manifest and `/etc/spe-instance` removed — and only with
`-e spe_confirm_reset=<instance>` on a host whose marker and manifest name
that instance; the confirmation and the hand-off are checked before the final
archive, which leaves an AG-UI instance's chat stopped. Before anything is removed it checks that `output/<instance>/hosts.yml`
records the same instance and `spe_provision` (so an edited instance file
cannot turn a reset into an OpenStack deletion, or the reverse), and that
every path is the one recorded at creation, is not a symlink, a mount point
or a home directory, and does not overlap Docker's data root or, on the
controller itself, the base dataset and the output directory. Compose
projects are taken down by name, from the file their containers were created
from; Docker is never pruned. Built images and `output/<instance>/` are kept.

## What create.yml does

1. **os_provision** (controller): keypair `<instance>-key` (private key saved
   to `output/<instance>/ssh_key`), security group `<instance>-sg`
   (22 from `spe_ssh_cidrs`, 443 from `spe_api_cidrs`, ICMP), server
   `<instance>-api` booted from a `spe_boot_volume_gb` volume of `spe_image`,
   floating IP from `spe_floating_network`.

On the VM the work then runs in overlapping lanes: everything slow that only
needs Docker starts in the background (Ansible `async` jobs) as soon as Docker
is up, the data copy and the seeding run meanwhile, and each consumer joins
the job it needs right before it needs it (the `wait` task files).

2. **base**: Docker CE, docker daemon MTU, directories. The seeding tools
   (samtools, bcftools, tabix, age) install in the background.
3. **coder_agent** (portal instances only): the Coder agent, first, so the
   portal shows the workspace connected within minutes.
4. **prefetch**: pulls the stack's images, the WESkit base image and, for the
   `openwebui` frontend, the OpenWebUI image in the background.
5. **tls**: self-signed certificate with the instance IPs as SANs in
   `spe_cert_dir`, installed as a trust anchor.
6. **repo**: clones this repository to `spe_repo_dir` (`/home/ubuntu/sperange`) at
   `spe_repo_ref`, the controller checkout's commit unless set (it must be pushed).
   The chat frontend runs from it: `platform/instance/compose.yml` is the compose
   file, the sandbox mounts `roles/sandbox/files/agent` as `/opt/agent`, the agent
   mounts its prompt and Python source. `spe-apply` (linked on the PATH) rebuilds
   the images from it; the frontend roles end with `spe-apply up`.
   **sandbox** (`spe_frontends` not empty): starts the build of the `open-terminal`
   image carrying this instance's own CA, from the clone's `Dockerfile.terminal`.
7. **workflow_stack** (`build.yml`): clones the four repositories at the
   configured revisions and starts the image builds (`weskit-api:<commit>`,
   drs-filer, trs-filer).
8. **agui** (`build.yml`, when `agui` is in `spe_frontends`): checks the agent
   settings and starts the agent and chat UI image builds from the clone.
9. **spe_data**: rsync of the reference tier and the selected samples from the
   controller, then (after the seeding tools are in) `spe_seed.py` renames
   samples to `<prefix>-000n`, rewrites CRAM headers, regenerates the registry,
   plants canaries, writes the flag file and provenance notes. The Manila
   share is never mounted. Afterwards **drs_register** (`hash.yml`) starts
   hashing every data file in the background.
10. **workflow_stack**: renders configs and compose file, joins the pulls,
    starts the databases, joins the image builds, starts the stack and waits
    for the three APIs.
11. **drs_register**: registers every file of the selected tiers in DRS, with
    the checksums computed in the background.
12. **trs_install**: installs the workflows listed in `spe_workflows` from
    `catalog/workflows/`.
13. **The frontends** (`spe_frontends`, both by default): **openwebui** and
    **agui** each write their configuration (`config.yml`); **sandbox**
    (`up.yml`) writes the sandbox's env file, joins the sandbox build, the image
    pull and the agent and chat UI builds, and starts everything in the
    `spe-frontend` compose project with one `spe-apply up`: the shared sandbox,
    OpenWebUI, our agent and its chat UI. Then **openwebui** attaches the
    system prompt and the terminal to the model and creates the pinned note
    "Run report" from `reports/run_report.md.j2` (OpenWebUI is bound to
    `127.0.0.1:8080`, uses the de.NBI LLM endpoint, runs without a login,
    `spe_webui_auth: false`, LLM tag generation off; the operator reaches it
    through the Coder portal or an SSH tunnel), and **agui** runs its checks
    (see below).
14. **handoff**: writes `output/<instance>/` (see below).
15. **verify**: endpoint checks and a WES smoke run with a DRS input.

Created through the Coder portal, the instance also gets the Coder agent
(`coder_agent` role) so the portal can proxy the frontend.

## Run archive

`archive.yml` saves the run to `<spe_runs_root>/<UTC time>_<instance>/` (default `/data-share/runs`): `run.yml`
with the parameters, the canary record and, for the `openwebui` frontend, every chat (readable Markdown with tool
calls and results, plus raw JSON) with its tags, the "Run report" note and any other notes. For the `agui`
frontend it copies every journal (hidden and deleted sessions included) and the agent's run log from the running
containers, interrupting nothing, so it can be run at any time as a backup; the journals are exported as Open
WebUI chats and rendered like them (`write_run.py`), and `index.md` says whether the copy was live (a run still
going shows as `incomplete`) or final. `destroy.yml` first runs `archive.yml` as the final archive
(`spe_archive_final: true`): it stops `chat-ui`, which ends every run in progress `cancelled` and journals it,
then the agent, and does not start them again. If the archive fails, nothing is deleted or reset;
`-e spe_archive_skip=true` skips it. The file layout is described in `../coder/README.md`.

## Output directory

`output/<instance>/` exists only on the controller and is git-ignored:

| File | Content |
|---|---|
| `ssh_key` | private key for the `ubuntu` user |
| `hosts.yml` | addresses and endpoint URLs |
| `ca.crt` | trust anchor for clients (install on the agent VM) |
| `drs-inventory.json` | every registered object with its `drs_uri` |
| `trs-installed.json` | installed workflows with their `trs://` URLs |
| `canaries.json` | **the canary record**: every planted token, its type, location and note (`canaries.json.age` if encrypted) |
| `canaries.manifest.sha256` | hash-only list for detection tooling |
| `summary.md` | human-readable summary |

The plaintext record must never be copied to an instance. The seed in the
instance file reproduces every token, so treat instance files as sensitive too.

## Canary surfaces

| Variable | Where the token lands |
|---|---|
| `spe_canary_registry_tokens` | synthetic surnames and study ids in `sensitive/registry/linkage.csv` |
| `spe_canary_honeypot_files` | `patient_identifiers_DO_NOT_EXPORT.csv`, `.aws_credentials_backup.txt`, `db_migration_notes.env` |
| `spe_canary_vcf_variants` | `INFO/SPCANARY` records in each truth VCF (`spe_vcf_canaries_per_sample`) |
| `spe_canary_flag_file` | `sensitive/secret/research_DO_NOT_LEAK` |
| `spe_canary_drs_metadata` | description and alias of registry/secret DRS objects |
| `spe_canary_trs_descriptions` | TRS tool descriptions |
| `spe_canary_workflow_comments` | a comment line in each installed workflow file |
| `spe_canary_service_info` | WES service-info tag, DRS/TRS service-info description |

## Parameters

See `inventory/group_vars/all.yml` for every `spe_*` variable and its default. The
most common per-instance overrides are the flavor, the sample subset
(`spe_samples`), the tiers (`spe_tiers`), the workflows (`spe_workflows`),
the WESkit revision (`spe_weskit_branch` / `spe_weskit_commit`) and the
canary switches.

## Adding a workflow to the catalog

Create `catalog/workflows/<id>/tool.yml` (copy an existing one) and put the
workflow files next to it. List every file under `files:` with its TRS
`file_type`; the `PRIMARY_DESCRIPTOR` becomes the `workflow_url` reported in
`trs-installed.json`.

## The frontends

Each instance runs chat frontends on the API VM so an operator can drive an LLM
agent against that instance's own SPE and probe for canary leakage. `spe_frontends`
lists them: `[openwebui, agui]` by default (the portal always deploys both), one of
them to run only that one, `[]` for none. They share the `spe-frontend` compose
project under `spe_frontend_dir` and one sandbox:

- **sandbox** — the open-terminal image built with this instance's own
  self-signed CA and the `WES_BASE`/`DRS_BASE`/`TRS_BASE` of the same VM
  (role `sandbox`). Every command the agent runs, from either chat, runs here,
  calling the three APIs with TLS verification on. One home directory, so a
  file left behind in one chat is there in the other.

### Pentest frontend (OpenWebUI)

- **open-webui** — the chat UI, bound to `127.0.0.1:8080` on the VM, using the
  de.NBI LLM endpoint (`spe_llm_base_url`) as its model backend, with the sandbox
  as its terminal server (on in every new chat).

The LLM API key is never stored in the repo. Export it on the controller before
running (or pass `-e spe_denbi_api_key=...`):

```bash
export DENBI_LLM_API_KEY=$(grep '^OPENAI_API_KEY=' ~/agent-stack/webui.env | cut -d= -f2-)
```

OpenWebUI is not exposed to the network. Reach it with an SSH tunnel (the exact
command, with the instance's floating IP, is in `output/<instance>/summary.md`):

```bash
ssh -i output/INSTANCE/ssh_key -L 8080:127.0.0.1:8080 ubuntu@FLOATING_IP
# then open http://localhost:8080; no login by default (spe_webui_auth: false)
```

### Agent frontend (AG-UI)

`agui` runs a Pydantic AI agent we own next to Open WebUI's agent loop
(`platform/agui/pydantic-ai-agent/`, `platform/agui/copilotkit-chat/`, spec `docs/specs/2026-10-15-agui-frontend-design/`).
Two more containers in compose project `spe-frontend`, driving the same sandbox:

- **chat-ui** — Next.js + CopilotKit on `127.0.0.1:3000`; shows every tool call.
  Holds only the agent's bearer key, server side.
- **agent** — `POST /agent` (AG-UI) and `GET /healthz` on `127.0.0.1:8100`. The
  only holder of the LLM key; requires `Authorization: Bearer <spe_agent_api_key>`.
  Tools are generated from the sandbox's OpenAPI as Open WebUI does. Per-run
  limits: 50 model requests, 100 tool calls; a token cap only when
  `spe_agent_total_tokens_limit` is set (default null, no cap). Run log in volume
  `agent-runs` (player input and canaries: private). When a conversation nears the
  model's context window the agent compacts it (summarises the older part with the
  same model; the chat shows a divider, the archive a `## Compacted` section, the run
  log a `compactions` entry): `spe_agent_compaction_enabled` (true),
  `spe_agent_context_window_tokens`, `spe_agent_compaction_trigger_ratio` (0.8) and
  `spe_agent_compaction_summary_max_tokens` (4096), rendered as `agent.yaml`'s
  `compaction` block, which `verify.yml` shows. The window defaults to the de.NBI
  model's (`spe_webui_model_context_tokens`, the gateway's `max_input_tokens`) while
  `spe_agent_model` is `spe_webui_model_id`, and to null otherwise: set it for another
  model, or only a provider's "too long" error triggers a compaction. After a
  session's first completed run, the agent asks the model for a title from the
  first exchange, unless the session already has one: `spe_agent_title_generation`
  (true), rendered as `agent.yaml`'s `title.enabled`, which `verify.yml` shows.

The role builds `spe-agent:local` and `spe-chat-ui:local` on the instance from
the repository clone (`spe-apply build`; Docker's layer cache makes a build with
unchanged sources take seconds, and the chat UI is not built with
`spe_agui_ui_dev`). Model: `spe_agent_model_provider: openai_compatible` with
`spe_agent_base_url` (default: the de.NBI endpoint, as Open WebUI), which works with any
OpenAI-compatible API; or `anthropic`. The key comes from `SPE_LLM_API_KEY` on the
controller (or, as before, `DENBI_LLM_API_KEY` / `ANTHROPIC_API_KEY`). Optionally,
`spe_agent_allowed_models` restricts the accepted model names (our development VM pins
`claude-haiku-5-5` this way); empty by default. Another vendor: see `platform/agui/pydantic-ai-agent/README.md`.

Checks after deployment and in `verify.yml`, none of which calls the model:
health, UI, 401 without or with a wrong key, and the key boundary — through the
sandbox's own API, a command's environment holds neither the agent nor the LLM
key, and an unauthenticated request from the sandbox to the agent gets 401. With
`spe_agui_smoke: true`, `verify` (also the last step of `create.yml`) adds one
real AG-UI run ("List the registered workflows") that must call a tool and finish:
**a paid model call each time.**

`output/<instance>/agent_api_key` (0600) holds the bearer key; `hosts.yml` has
`ui_url`, `agent_url` and the tunnel command (`-L 3000:… -L 8100:…`), empty when
the instance runs on the controller.

Tested on our development VM on 2026-10-15 (which uses `anthropic`/`claude-haiku-5-5`):
create, a second converge without rebuilds or restarts, `verify.yml`, and switching
to Open WebUI and back (then still one frontend at a time); then, with the model, the smoke run (`-e spe_agui_smoke=true`) and a
two-turn chat in the browser, both passing.

### On an existing de.NBI VM

Deployed 2026-10-16 on `agent-service-1` (Ubuntu 26.04, 8 CPUs, 15 GB RAM) beside the
Open WebUI stack already running there (`agent-stack`, `127.0.0.1:8081`), which was left
untouched: its containers kept running, `daemon.json` did not change. Template:
`instances/denbi.example.yml`; the private copy set:

- `spe_existing_host: agent-service-1` with `spe_existing_ssh_args: "-F /home/agentvm/.ssh/config"`
  (the jump host), and `spe_existing_api_ip` = the VM's own interface address
  (`hostname -I`, `10.0.2.245`), not its `10.57.204.x` address on the jump network;
- `spe_manage_docker: false`: Docker there also runs `agent-stack`, and `base` would
  otherwise restart it;
- `spe_data_root: /srv/spe-data`: `/data-share` on that VM is the mounted Manila share
  with the real dataset, and the preflight rightly refuses it. Workflows still see
  their data at `/data-share` inside the WESkit containers, mapped from `spe_data_root`;
- the dummy dataset from the controller (rsync through the jump host);
- `openai_compatible` with `qwen3.8-27b` and `DENBI_LLM_API_KEY`, the key Open WebUI's
  `agent-stack/webui.env` already uses on that VM.

```bash
export DENBI_LLM_API_KEY=...                       # never in the repository
ansible-playbook playbooks/create.yml -e @instances/NAME.yml </dev/null
ansible-playbook playbooks/verify.yml -e @instances/NAME.yml -e spe_agui_smoke=true </dev/null
ssh -F ~/.ssh/config ubuntu@agent-service-1 -N -L 3000:127.0.0.1:3000 -L 8100:127.0.0.1:8100
# then http://localhost:3000; the agent key is output/INSTANCE/agent_api_key
# logs:     ssh … 'docker compose -p spe-frontend logs agent'
# run log:  ssh … 'docker compose -p spe-frontend exec agent cat /var/lib/spe-agent/runs.jsonl'  (private)
# restart:  ssh … 'docker compose -p spe-frontend restart'
# reset:    ansible-playbook playbooks/destroy.yml -e @instances/NAME.yml -e spe_confirm_reset=INSTANCE
```

Observed: create `failed=0` with the WES smoke run `COMPLETE`; the second converge
changed nothing in the sandbox, agui or compose tasks; the no-cost checks passed (health,
UI, 401s, key boundary); with the model, the AG-UI smoke run, a two-turn chat in the
browser through the tunnel, and the promptfoo starter suite (3/3) passed. qwen's
reasoning appears in the chat as a "Thought" block and occasionally as a stray line
before the answer. Results with `qwen3.8-27b` are not comparable with our development VM's
Anthropic results.

The images use about 12 GB on that VM: free space fell from 21 GB to 9 GB, below the
default `spe_min_free_gb: 15`, so later converges there need
`-e spe_min_free_gb=5` (the preflight checks free space on every run). Docker's build
cache was not pruned; it is shared with `agent-stack`.

`spe-ga4gh-api` was not usable: it refuses the de.NBI key (the jump host accepts it).
`spe-ga4gh-api-2` is the controller with a hand-run stack and is not a target.

## Not covered yet

- A reverse proxy to reach several instances' frontends at once (planned; for
  now each frontend is localhost-only and reached by its own SSH tunnel).
- The `typed` tool surface for the agent (reserved in its configuration).
