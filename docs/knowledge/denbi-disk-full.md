# agent-service-1's disk is full

`create.yml` against `denbi-agui-01` refused by the preflight: "only 0 GB free on the filesystem of
/home/ubuntu/spe-frontend, … /var/lib/docker, need 5". The VM's `/` is 48 GB, shared with `agent-stack` and
`workflow-stack`; on 2026-11-03 it had 710 MB free. The user OK'd pruning it (mostly dummy data).

- **`docker builder prune -f` frees only dangling cache** (3 MB here, of 12.95 GB "reclaimable" in
  `docker buildx du`). Use `docker builder prune -af`.
- **"Reclaimable" overstates.** `-af` reported 12.94 GB and freed about 1 GB, because the cache's layers are
  shared with images still in use (containerd snapshotter, `/var/lib/containerd`).
- **What got it to 6.1 GB:** the build cache; our unused `spe-agent`/`spe-chat-ui` tags (keep the tags the
  running containers use: `docker ps --format '{{.Image}}'`); unused `spe-goose` and `hello-world`; `sudo apt-get
  clean`; `uv cache clean`; and the old VS Code server versions under `~/.vscode-server/cli/servers/` (keep the
  first entries of `lru.json`) and old `~/.vscode-server/code-*` CLIs (keep the one `pgrep -af "agent host"`
  shows).
- **`~/.vscode-server` is live**: the `theo` key's VS Code agent host. Deleting the whole directory would
  disconnect it.
