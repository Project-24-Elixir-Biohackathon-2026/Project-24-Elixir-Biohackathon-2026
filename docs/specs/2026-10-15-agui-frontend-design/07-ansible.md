## 7. Ansible

### 7.0 Provisioning an existing VM (`spe_provision: existing`)

Today `create.yml`'s first play (`os_provision`, on the controller) creates
keypair, security group, server and floating IP in OpenStack and registers
the new VM with `add_host`; the second play configures it. Nothing else
needs OpenStack. So the change is confined to how the host gets into the
inventory:

```yaml
spe_provision: openstack        # openstack (create the VM, as today) | existing
spe_existing_host: null         # SSH target: an alias from ~/.ssh/config (jump host included) or an address
spe_existing_api_ip: null       # the VM's private IP; becomes spe_api_host (certificate IP SAN, API URLs)
spe_existing_ssh_key: null      # null: let ssh config decide; else a private key path on the controller
```

- **Play 1** in `existing` mode skips `os_provision` and instead asserts the
  three variables, creates `output/<instance>/`, and `add_host`s
  `spe_existing_host` with `spe_api_host: spe_existing_api_ip` and
  `spe_floating_ip: ''`. `spe_api_host` must be an IP: `workflow_stack`
  puts it in the certificate as `IP:` SAN.
- **Ownership marker**: `base` writes `/etc/spe-instance` with the instance
  name; play 2 refuses to run on a host whose marker names a different
  instance, so two instance files cannot overwrite one VM.
- **Host requirements** (asserted at the start of play 2): passwordless
  `sudo`, Ubuntu with `apt`, free disk at `spe_data_root` for the selected
  samples. `base` installs Docker as today.
- **Security group**: not managed in this mode; whoever owns the VM
  controls ports 22 and 443. `summary.md` says so.
- **Handoff and `verify.yml`**: `hosts.yml` records `provision`, the SSH
  target and key, and `verify.yml` connects with those instead of
  assuming `output/<instance>/ssh_key`.
- **`destroy.yml`** never deletes a VM it did not create. In `existing`
  mode it *resets* instead: `docker compose down -v` for `spe-frontend` and
  the workflow stack, then removes `spe_stack_dir`, `spe_frontend_dir`,
  the instance's data under `spe_data_root` and `/etc/spe-instance`. It
  requires `-e spe_confirm_reset=<instance>` and checks the ownership
  marker first. This is also the reset story 0005 asks for.
- **Controller**: wherever `ansible-playbook` runs needs the base dataset
  at `spe_source_data_root` (rsynced to the VM) and SSH to the target
  (through the de.NBI jump host). Correction: `/data-share` on
  `spe-ga4gh-api-2` was found empty when inspected, so no controller is known
  to hold the GIAB base dataset; generate the dummy dataset
  (`dev/make_dummy_dataset.py`) on the controller instead.

### 7.1 First test target: this development VM

The VM this work is developed on (an agentvm microVM: Ubuntu 26.04, 4 vCPU,
11 GB RAM, Docker 29.8, Ansible with the needed collections; Docker data
on `/storage/docker`, 39 GB free after pruning) is the first `existing`
host:

- `spe_existing_host: localhost` with `ansible_connection: local`;
  `spe_existing_api_ip` = the VM's own non-loopback IP (the certificate
  needs an IP SAN and the sandbox container must reach Traefik on it).
- **Passwordless sudo**: needed by `base`, `spe_data`, `workflow_stack`. It
  did not work here because the image's `ubuntu` user and agentvm's
  `agentvm` user share uid 1000 and the sudoers rule matched by name only;
  fixed in the agentvm repo (`4ad5330`, a `#<uid>` rule), effective after
  the VM is re-provisioned from the host (`vmupdate`).
- **Dummy dataset**: `/data-share` with the GIAB genomes is not here and
  would not fit. A generator `dev/make_dummy_dataset.py` writes the layout
  `spe_data` expects under `spe_source_data_root` — a tiny synthetic
  reference and four small samples (CRAMs, truth VCFs) named as in
  `spe_source_samples` — so `spe_seed.py` and canary planting run
  unchanged. The exact layout is read from `spe_data` and `spe_seed.py`
  in the plan. Workflows that need real genomes (`gatk-hc-chr20`) are
  left out of `spe_workflows`; `wes-drs-smoke` is kept.
- **LLM**: the de.NBI endpoint is internal (no DNS here), so
  `spe_agent_model_provider: anthropic`, `spe_agent_model: claude-haiku-5-5`,
  with `ANTHROPIC_API_KEY` exported
  from `~/.config/spe-dev/llm.env` (outside any repository, mode 0600).
- An example instance file `instances/dev-local.example.yml` carries these
  settings with `spe_seed: null`. Correction: real instance files, the
  development one included, are ignored by git and never committed, because
  the seed reproduces every canary.

### Variables (added to `group_vars/all.yml`)

```yaml
spe_frontend: openwebui              # unchanged default; set agui to use this
spe_agui_ui_port: 3000               # 127.0.0.1 on the VM
spe_agui_agent_port: 8100            # 127.0.0.1 on the VM
spe_agui_smoke: false                # true: one LLM-backed AG-UI run in the checks (paid; off by default)
spe_agent_model_provider: openai_compatible   # openai_compatible | anthropic
spe_agent_model: "{{ spe_webui_model_id }}"
spe_agent_llm_key: "{{ spe_denbi_api_key if spe_agent_model_provider == 'openai_compatible' else lookup('ansible.builtin.env', 'ANTHROPIC_API_KEY') }}"
spe_agent_tool_surface: shell
spe_agent_sandbox_operations: all
spe_agent_max_output_bytes: 16384
spe_agent_request_limit: 50
spe_agent_tool_calls_limit: 100
spe_agent_total_tokens_limit: null   # or a number: a per-run token cap
spe_agent_api_key: "{{ (spe_seed | string ~ ':agent-api') | hash('sha256') }}"
spe_agui_source_dir: "{{ playbook_dir }}/../../agui"   # platform/agui on the controller
```

`spe_frontend_terminal_image`, `spe_terminal_api_key`, `spe_llm_base_url`
and `spe_denbi_api_key` are reused as they are.

### Role `agui` (runs where `openwebui` runs in `create.yml`)

1. Assert the LLM key is present (same message as the `openwebui` role).
2. Include role `sandbox` (builds the open-terminal image with CA and
   runbook).
3. Sync `agent/` and `chat-ui/` to `{{ spe_frontend_dir }}/build/` and build
   `spe-agent:<content hash>` and `spe-chat-ui:<content hash>`; rebuild only
   when the content changed.
4. Render `agent.yaml`, `agent.env` (LLM, agent and sandbox keys; mode
   `0600`, `no_log`), `chat-ui.env` (agent URL and key; `0600`),
   `terminal.env` (as today), `docker-compose.yml`.
5. Compose up (`community.docker.docker_compose_v2`), recreating on
   changed config or images — the pattern of the `openwebui` role.
6. Checks (§9). Fail the play on any failure.

If the VM previously ran the Open WebUI stack, step 5 replaces it (same
project name); `open-webui-data` is left in place, not deleted.

### Compose

- Networks: `ui` (chat-ui, agent) and `tools` (agent, sandbox). Neither is
  `internal`: the agent must reach the LLM endpoint and the sandbox must
  reach Traefik on the VM's address, as today.
- Ports: `127.0.0.1:{{ spe_agui_ui_port }}:3000` on chat-ui,
  `127.0.0.1:{{ spe_agui_agent_port }}:8100` on agent. Sandbox publishes
  nothing.
- Sandbox: today's settings unchanged (`cap_drop: ALL` + `SETGID`,
  `no-new-privileges`, 2 CPU, 2 GB, 256 pids, `open-terminal-data` volume).
- Agent and chat-ui: `no-new-privileges`, `cap_drop: ALL`, read-only root
  filesystem where the runtime allows, memory limits, healthchecks.

### Handoff

`hosts.yml` gets `frontend: agui`, `ui_url`, `agent_url`, both tunnel
commands; `summary.md` gets an *Agent frontend (AG-UI)* section with the
tunnel command (`-L 3000:… -L 8100:…`) and how to run promptfoo. The agent
key is written to `output/<instance>/agent_api_key` (mode `0600`, on the
controller only), not into `summary.md`.
