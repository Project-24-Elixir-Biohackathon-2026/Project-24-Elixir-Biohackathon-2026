# Getting started: an SPE with the AG-UI agent

This guide takes a new operator from a fresh checkout to a running SPE instance
with the agent frontend on an existing VM, including every private value the
setup needs: what it is, where it comes from, where it lives and who may see it.
Reference material lives elsewhere: `platform/ansible/README.md` (all playbook options),
`platform/agui/pydantic-ai-agent/README.md`, `platform/agui/copilotkit-chat/README.md`,
`platform/promptfoo-evals/README.md`.

An instance is one VM running the GA4GH workflow stack (WES, DRS, TRS behind
Traefik on 443), seeded with test data and canary tokens, plus a frontend:
`agui` (our agent over AG-UI with a CopilotKit chat, the subject of this guide)
or `openwebui`. Everything is driven from a **controller**, the machine where you
run `ansible-playbook`; the controller and the VM may be the same machine.

This is the by-hand path. Participants normally get instances from the Coder
portal instead (`platform/coder/README.md`), which runs the same playbooks with
`spe_provision: openstack` and archives each run when it is stopped.

## 1. What you need

**On the controller**

- This repository (`git clone git@github.com:kraatz/elixir-biohackathon-2026-test.git`).
- `ansible-core` with the collections in `platform/ansible/requirements.yml` (a system
  Ansible package usually ships them; otherwise
  `ansible-galaxy collection install -r platform/ansible/requirements.yml -p platform/ansible/collections`).
- `git`, `rsync`, `ssh`, and `samtools`, `bgzip`, `tabix` to generate the dummy dataset.
- Optional, for evaluations: Node.js 24 and `uv`.
- Not needed in existing-VM mode: `clouds.yaml`, `openstacksdk`, `/data-share`.
  Those belong to `spe_provision: openstack`, which creates VMs (see `platform/ansible/README.md`).

**On the target VM**

- Ubuntu with `apt`, passwordless `sudo` for the SSH user (`ubuntu` by default), and
  Docker with the compose plugin (or let the playbook install it, below).
- Ports 443, 3000 and 8100 free (3000 and 8100 are bound to `127.0.0.1` only).
- About 15 GB free: the images (WESkit, open-terminal, agent, chat UI) take ~12 GB.
- Outbound HTTPS to the LLM endpoint and to the image registries.

The playbook checks the VM before changing anything and refuses it if another
instance owns it, if the stack, frontend or data directory already exists, if a
needed port is taken, or if disk is short. Nothing on a refused VM is changed.

## 2. Private configuration

| What | What it is for | Where it comes from | Where it lives | Share? |
|---|---|---|---|---|
| **Seed** (`spe_seed`) | Derives every canary token, the agent's bearer key, the sandbox key and the Open WebUI admin password. Anyone with it can reproduce all canaries | You generate it (step 4) | Your instance file `platform/ansible/instances/<name>.yml` (git-ignored, mode 0600) | **No.** Never commit it |
| **LLM key** | Lets the agent call the model | Your LLM provider. For the de.NBI endpoint: the project's key (ask the project; on de.NBI VMs Open WebUI already uses it in `~/agent-stack/webui.env` as `OPENAI_API_KEY`). For another OpenAI-compatible API or Anthropic: your own key | Exported in your shell at run time: `SPE_LLM_API_KEY` (or `DENBI_LLM_API_KEY` / `ANTHROPIC_API_KEY`). On the VM only in `spe-frontend/agent.env` (0600), read by the agent container alone | **No** |
| **SSH key and config** for de.NBI | Reaching VMs on the private network through the jump host | Your de.NBI account (key registered with de.NBI and on the VMs) | `~/.ssh/config` and your key, outside any repository | **No** |
| **Agent bearer key** | Required by the agent's AG-UI endpoint; the chat UI and promptfoo send it | Derived from the seed by the playbook | `platform/ansible/output/<instance>/agent_api_key` (0600); on the VM in `agent.env` and `chat-ui.env` (0600) | Only with people who may use the agent |
| **Canary record** | The answer key: every planted token and where it is | Written by the playbook | `platform/ansible/output/<instance>/canaries.json` (0600; encrypted to `canaries.json.age` if `spe_age_recipient` is set) | **No.** Never copy it to a VM or to a player. `canaries.manifest.sha256` (hashes only) may go to detection tooling |
| **Hand-off** | Addresses, tunnel command, Open WebUI admin password (`openwebui` frontend) | Written by the playbook | `platform/ansible/output/<instance>/hosts.yml`, `summary.md` | Operators only |
| **Run log** | Every agent run: player input, tool calls and results, answers, usage | Written by the agent | On the VM, volume `spe-frontend_agent-runs` | **No**: contains canaries |
| **Chat sessions** | Every AG-UI conversation: messages, tool calls and results, titles and tags | Written by the chat UI | On the VM, volume `spe-frontend_chat-sessions` (one journal per session); in the run directory `agui-journals/`, `chats/` and `agent-runs.jsonl` | **No**: contain canaries |
| **Evaluation reports** | promptfoo results | `npm run eval` | `platform/promptfoo-evals/reports/`, `.promptfoo/` (git-ignored) | **No**: contain canaries. Delete after use |

Everything in `platform/ansible/output/` and every real instance file is git-ignored.
**Back up `platform/ansible/output/<instance>/` and your instance file** somewhere private:
they are the only record of that instance's canaries (the seed can regenerate them,
the canary record is the readable list).

## 3. Reach the VM

Skip this if the controller is the VM (`spe_existing_host: localhost`).

For de.NBI, VMs sit on a private network behind `denbi-jumphost-01.bihealth.org`.
A working `~/.ssh/config` (replace the user, key path and addresses with yours):

```
Host denbi-jumphost-01
  Hostname denbi-jumphost-01.bihealth.org
  User <your de.NBI user>
  IdentityFile ~/.ssh/<your de.NBI key>
  IdentitiesOnly yes

Host agent-service-1
  HostName 10.57.204.214
  User ubuntu
  IdentityFile ~/.ssh/<your de.NBI key>
  IdentitiesOnly yes
  ProxyJump denbi-jumphost-01
```

`IdentitiesOnly yes` matters: the jump host bans clients after a few failed keys,
so offer exactly one. Connect once by hand to check the key and accept the host
key, then confirm the VM is usable:

```bash
ssh -F ~/.ssh/config agent-service-1 'sudo -n true && echo sudo-ok; hostname -I; df -h /; ss -tln'
```

Note the VM's own address from `hostname -I` (on de.NBI the `10.0.2.x` address,
not the `10.57.204.x` one you SSH to): it goes into `spe_existing_api_ip`.
Knowledge record 0005 in the biohackathon repository lists the de.NBI hosts and
what already runs on them.

## 4. Configure an instance

In the commands from here on, replace `NAME` with your instance name (`spe_instance`)
and `VM` with the VM's SSH host.

1. **Dummy dataset** on the controller (stands in for the GIAB genomes):

   ```bash
   python3 platform/dev/make_dummy_dataset.py --out ~/spe-dummy-data --seed 1
   ```

2. **Instance file** from a template, private from the start:

   ```bash
   cd platform/ansible
   umask 077
   cp instances/denbi.example.yml instances/NAME.yml        # a remote VM
   # or: cp instances/dev-local.example.yml instances/NAME.yml   # the controller itself
   python3 -c "import secrets; print(secrets.randbelow(10**12))"   # the seed
   ```

3. **Fill in** `instances/<name>.yml`:

   | Setting | Value |
   |---|---|
   | `spe_instance` | a unique name, e.g. `denbi-agui-02` (one instance per VM) |
   | `spe_seed` | the number generated above |
   | `spe_existing_host` | the SSH alias from step 3, or `localhost` |
   | `spe_existing_api_ip` | the VM's own address from `hostname -I` |
   | `spe_existing_ssh_args` | `"-F /home/<you>/.ssh/config"` for the jump host; `""` otherwise |
   | `spe_source_data_root` | the dummy dataset's path on the controller |
   | `spe_manage_docker` | `false` if Docker on the VM already runs other things (the playbook then leaves its packages, config and service alone); `true` to let it install and configure Docker |
   | `spe_data_root` | leave the default `/data-share` only if that path does not exist on the VM. On de.NBI VMs `/data-share` may be the mounted shared dataset: use e.g. `/srv/spe-data` |
   | `spe_agent_model_provider`, `spe_agent_model`, `spe_agent_base_url` | your LLM. `openai_compatible` works with any OpenAI-compatible API: set `spe_agent_base_url` (default: the de.NBI endpoint) and the model name, e.g. `qwen3.8-27b` on de.NBI. `anthropic` uses Anthropic's API. Optional `spe_agent_allowed_models: [<name>]` refuses any other model, a guard against typos selecting a pricier one. Other vendors: `agent/README.md` |
   | `spe_agui_smoke` | `false`; set `true` on a run to add one model-backed check |

   `git status` must not list the file: if it does, stop and check `platform/ansible/.gitignore`.

## 5. Deploy

```bash
cd platform/ansible
export SPE_LLM_API_KEY=...          # your provider's key (DENBI_LLM_API_KEY / ANTHROPIC_API_KEY also work)
ansible-playbook playbooks/create.yml -e @instances/NAME.yml </dev/null
```

The first run builds images on the VM and takes a while. It ends with checks that
make no model call: agent health, the chat UI, 401 without the bearer key, and the
key boundary (commands in the sandbox see neither the agent key nor the LLM key).
Re-running converges and changes nothing in the frontend.

```bash
ansible-playbook playbooks/verify.yml -e @instances/NAME.yml </dev/null                         # no model call
ansible-playbook playbooks/verify.yml -e @instances/NAME.yml -e spe_agui_smoke=true </dev/null  # + one agent run
```

If a later run is refused for disk only because the images now occupy the VM, pass
`-e spe_min_free_gb=5`.

## 6. Use it

`platform/ansible/output/<instance>/hosts.yml` has the tunnel command (`agui_tunnel`):

```bash
ssh -F ~/.ssh/config ubuntu@VM -N -L 3000:127.0.0.1:3000 -L 8100:127.0.0.1:8100
```

Then open `http://localhost:3000`. Every tool call the agent makes is shown as a
card. Conversations are kept as sessions in the left sidebar (rename, pin, tag, hide, delete) and
archived with the run. If 3000 or 8100 is taken on your machine,
change only the first number of each `-L` (e.g. `-L 13000:127.0.0.1:3000`).

To call the agent directly, as promptfoo does:
`POST http://localhost:8100/agent` with `Authorization: Bearer $(cat platform/ansible/output/<instance>/agent_api_key)`.

Evaluations: see `platform/promptfoo-evals/README.md` (every test is a model-backed agent run).

On the VM (`ssh …` then):

```bash
docker compose -p spe-frontend ps                    # chat-ui, agent, sandbox
docker compose -p spe-frontend logs agent
docker compose -p spe-frontend restart
docker compose -p spe-frontend exec agent cat /var/lib/spe-agent/runs.jsonl   # private
```

## 7. Reset and clean up

```bash
ansible-playbook playbooks/destroy.yml -e @instances/NAME.yml -e spe_confirm_reset=NAME </dev/null
```

On an existing VM this never deletes the VM: it takes this instance's compose
stacks down with their volumes (including the run log) and removes its directories,
CA anchor, marker and manifest, after checking they belong to this instance. Built
images and `platform/ansible/output/<instance>/` are kept. Then:

- keep or archive `platform/ansible/output/<instance>/` and the instance file privately, or
  delete them when the instance's canaries no longer matter;
- delete `platform/promptfoo-evals/reports/` and `platform/promptfoo-evals/.promptfoo/`;
- unset the LLM key in your shell.

## 8. Rules worth repeating

- Never commit a real instance file, anything under `platform/ansible/output/`, keys,
  `clouds.yaml` or `.env` files. Check `git status` and `git diff --staged` before
  every commit.
- Never pass a key on a command line or put it in a prompt, test variable or config
  file in the repository; use the environment or a 0600 file.
- Model-backed runs cost money (commercial APIs) or shared capacity (de.NBI); the agent
  caps each run at 50 model requests and 100 tool calls. A per-run token cap
  (`spe_agent_total_tokens_limit`) is off by default, as Open WebUI has none; set a
  number to turn it on.
- One instance per VM; do not replace another stack to make the preflight pass.
