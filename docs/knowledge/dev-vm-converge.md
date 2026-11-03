# Re-converging the development VM (`dev-local`)

Found 2026-11-02, deploying slice 2 of the AG-UI chat sessions with `create.yml -e spe_agui_source_dir=…`.

**"only 3 GB free on the filesystem of /storage/docker, need 15".** The preflight checks free space on every
run, and the VM's disk is ~95 % used (images, other projects' containers, `/var/tmp`). `docker builder prune -f`
reclaimed only ~5 GB (to 8 GB free). A re-converge, whose images are already present, runs with
`-e spe_min_free_gb=5` (`platform/ansible/README.md` says the same for de.NBI). Images, volumes and other
projects' containers on the VM are not ours to prune.

On 2026-11-03 (slice 4 of the AG-UI conversation record) even `spe_min_free_gb=5` failed ("only 4 GB free …,
need 5"): `docker builder prune -f` freed ~1 MB. `docker image prune -f` (dangling, untagged images only: our
rebuilds leave them behind, and other projects' tagged images stay) freed ~7.8 GB, to 12 GB free.

**"The agent's LLM key is empty. Export SPE_LLM_API_KEY …".** The dev VM's key (Anthropic) is in
`~/.config/spe-dev/llm.env` (0600, `ANTHROPIC_API_KEY=`), outside every repository. Export it for the run only;
with `spe_agui_smoke: false` in `dev-local.yml` a converge makes no model call:

```bash
cd platform/ansible && set -a && . ~/.config/spe-dev/llm.env && set +a \
  && ansible-playbook playbooks/create.yml -e @instances/dev-local.yml -e spe_min_free_gb=5 </dev/null
```

`archive.yml` needs neither.

**"dev-local-api not reset, nothing changed: compose project spe-frontend has containers from
…/platform/dev/fake-agent.compose.yml, not /home/ubuntu/spe-frontend/docker-compose.yml".** `destroy.yml`'s reset
refuses a project whose containers were created from another compose file, and the fake agent
(`fake-agent.compose.yml`) is one. Found 2026-11-03 (slice 4 of the AG-UI conversation record): the final
archive had already run, so remove the stopped fake container by name (`docker rm spe-frontend-agent-1`;
`docker compose … rm` needs `SPE_DEV_PLATFORM` set) and re-run with `-e spe_archive_skip=true`. Before a
destroy that should archive, `create.yml` first to put the real agent back.

**`[Errno 24] Too many open files`** (and `npm error code EMFILE` in `npm ci`), twice on 2026-11-03: in
`create.yml`'s *Build-context files* task and in `npm ci`. `ulimit -n` was 1048576, the system was far from
`file-max`, and no process held many descriptors afterwards. Transient: a plain re-run passed both times.
