# Building an experiment arm on an instance without the portal

The portal follows upstream, so a fork branch's `spe-experiments` template can't be tried there. To build an arm
on a controller-side instance (e.g. `denbi.yml`, `spe_provision: existing`):

1. Render the template's `build_vars` for the preset with OpenTofu, as
   `platform/dev/tests/test_experiments_template.py` does (copy the template dir, `assemble.sh`, `tofu init`,
   `tofu plan` with `CODER_PARAMETER_<sha256(name)>` env values, `tofu show -json` →
   `planned_values.outputs.build_vars.value`) and write it as YAML.
2. **Drop the keys the instance file owns**: `spe_instance` and `spe_seed` come out of the render as
   `cw-default-default` and a seed from the fake workspace id, and a later `-e` wins, so they would rename and
   reseed the instance. Drop every key the instance file sets except the experiment's own (`spe_workflows`,
   `spe_frontends`, `spe_agui_smoke`).
3. **Run `create.yml` from the branch's worktree**, not the main checkout: the main checkout runs `main`'s roles
   and `group_vars` (no mitigation checks, no new `hardening.json` keys). Point outputs at the main checkout:

```bash
cd <worktree>/platform/ansible
ansible-playbook playbooks/create.yml -e @<main>/platform/ansible/instances/denbi.yml -e @<rendered>.yml \
  -e spe_output_root=<main>/platform/ansible/output -e spe_repo_ref=<pushed branch> </dev/null
```

`create.yml` stops at `agui : LLM key present` without the instance's provider key in the environment, even when
the build makes no model call (`denbi.yml` uses Anthropic: `set -a; . ~/.config/spe-dev/llm.env; set +a` for that
run only; `denbi-llm-key.md`).

Then read `<main>/platform/ansible/output/<instance>/hardening.json` (`level`, `mitigations`, `experiment`).
First used for slice 2's `ladder-l2` check (fork PR #86).
