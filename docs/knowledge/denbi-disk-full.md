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

**2026-11-08: `agent-stack` removed.** Images bumped by the upstream merge (open-terminal 0.16.1, ~5.7 GB new)
failed `spe-apply build sandbox` with "no space left on device" at 5.3 GB free. With the user's go-ahead
`agent-stack` (Open WebUI v0.11.3 and its `open-terminal-ca:0.12.4`, `~/agent-stack`) went: its two volumes and
the compose dir are in `/data-share/backups/agent-stack-2026-11-08/` (root-only, `tar -tzf` checked), then
`docker compose down`, its two images and volumes removed: 14 GB free. After the deploy (sandbox
`spe-open-terminal:0.16.1`, 7.3 GB) 9.3 GB were left; removing the unused 0.12.4 terminal images freed no more
(layers shared with 0.16.1). To restore `agent-stack`:
untar the volumes into new `agent-stack_*` volumes and the dir into `~`, then `docker compose up -d` there.
