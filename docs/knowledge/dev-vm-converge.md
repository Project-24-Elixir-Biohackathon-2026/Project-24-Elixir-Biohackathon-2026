# Re-converging the development VM (`dev-local`)

Found 2026-11-02, deploying slice 2 of the AG-UI chat sessions with `create.yml -e spe_agui_source_dir=…`.

**"only 3 GB free on the filesystem of /storage/docker, need 15".** The preflight checks free space on every
run, and the VM's disk is ~95 % used (images, other projects' containers, `/var/tmp`). `docker builder prune -f`
reclaimed only ~5 GB (to 8 GB free). A re-converge, whose images are already present, runs with
`-e spe_min_free_gb=5` (`platform/ansible/README.md` says the same for de.NBI). Images, volumes and other
projects' containers on the VM are not ours to prune.

**"The agent's LLM key is empty. Export SPE_LLM_API_KEY …".** The dev VM's key (Anthropic) is in
`~/.config/spe-dev/llm.env` (0600, `ANTHROPIC_API_KEY=`), outside every repository. Export it for the run only;
with `spe_agui_smoke: false` in `dev-local.yml` a converge makes no model call:

```bash
cd platform/ansible && set -a && . ~/.config/spe-dev/llm.env && set +a \
  && ansible-playbook playbooks/create.yml -e @instances/dev-local.yml -e spe_min_free_gb=5 </dev/null
```

`archive.yml` needs neither.
