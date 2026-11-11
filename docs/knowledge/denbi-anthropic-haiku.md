# de.NBI instance on Anthropic Haiku

Since 2026-11-08 `denbi-agui-01` (agent-service-1) runs the AG-UI agent on Anthropic `claude-haiku-5-5` with our
key, because the de.NBI LLM key there is blocked (`denbi-llm-key.md`) and this NixOS guest cannot host a dev-local
instance (`machines/nixed-microvm.md`). The private `instances/denbi.yml` sets:

    spe_frontends: [agui]
    spe_agent_model_provider: anthropic
    spe_agent_model: claude-haiku-5-5
    spe_agent_allowed_models: [claude-haiku-5-5]   # spend guard
    spe_agui_smoke: false                           # true = one paid call per run

Converge and check, from the main checkout's `platform/ansible` (the key from `~/.config/spe-dev/llm.env`, 0600):

    set -a; . ~/.config/spe-dev/llm.env; set +a
    ansible-playbook playbooks/create.yml -e @instances/denbi.yml </dev/null
    ansible-playbook playbooks/verify.yml -e @instances/denbi.yml -e spe_agui_smoke=true </dev/null   # paid

First run at `e858c09`: create `ok=156 failed=0`; the verify smoke used `run_command` and `get_process_status`,
ended `RUN_FINISHED` with a 218-character answer (75 events). It needed the disk freed first
(`denbi-disk-full.md`, 2026-11-08).

**Destroying it from this guest** (`spe_provision: existing`, 2026-11-11): `destroy.yml` archives the run on the
controller first and failed there, before any reset, with `There was an issue creating /data-share as requested:
[Errno 13] Permission denied: b'/data-share'` (`spe_runs_root` defaults to `/data-share/runs`, which this guest
lacks). Point it into the main checkout's git-ignored output:

    ansible-playbook playbooks/destroy.yml -e @instances/denbi.yml -e spe_confirm_reset=denbi-agui-01 \
      -e spe_runs_root=$PWD/output/runs </dev/null
