# de.NBI: `create.yml` fails at `base : Install packages` (apt cache)

**Symptom** (2026-11-11, denbi-agui-01 on agent-service-1): `create.yml` stops at `base : Install packages` with
`Failed to update apt cache after 5 retries:` (empty reason). On the VM, `sudo apt-get update` hangs with no output.
Two sessions running it at once add `E: Could not get lock /var/lib/apt/lists/lock. It is held by process … (apt-get)`.

**Cause:** the VM cannot resolve the Ubuntu archives. `curl -m 10 http://archive.ubuntu.com/ubuntu/` gives
`curl: (28) Resolving timed out after 10000 milliseconds`, and so does `de.archive…`. `download.docker.com` and
`github.com` answer 200. The apt sources are `nova.clouds.archive.ubuntu.com` and `security.ubuntu.com`.

**What to do:**
- Check resolution first:
  `ssh agent-service-1 'curl -sS -o /dev/null -m 10 -w "%{http_code}\n" http://archive.ubuntu.com/ubuntu/'`.
  Retry the build only once that gives 200.
- Never leave an `apt-get update` probe hanging over ssh: it holds the apt lock, and the next build fails on the lock
  instead. Run probes with `timeout`, and kill a leftover one with `sudo kill <pid>` (`pgrep -a apt-get`).
- The failing run changes nothing on the VM (`changed=0` in its recap): `base` runs before any role that rewrites
  the stack.

**Workaround that works** (2026-11-11, still failing hours later): the resolver (10.57.196.4/.5) times out only on
`*.ubuntu.com`, and outside DNS (`@1.1.1.1`) is blocked, but most archive IPs answer over HTTP. Only
`185.125.190.93–95` (the nova mirror's own) time out. Pin the names in `/etc/hosts` with a marked block, then remove
it once the build is done:
```bash
ssh agent-service-1 'printf "%s\n" "# spe-dns-workaround begin" \
  "91.189.91.81 nova.clouds.archive.ubuntu.com archive.ubuntu.com" "91.189.91.82 security.ubuntu.com" \
  "# spe-dns-workaround end" | sudo tee -a /etc/hosts'
# afterwards:
ssh agent-service-1 "sudo sed -i '/# spe-dns-workaround begin/,/# spe-dns-workaround end/d' /etc/hosts"
```
Check a pinned IP first: `curl -m 10 --resolve nova.clouds.archive.ubuntu.com:80:<ip> http://nova.clouds.archive.ubuntu.com/ubuntu/dists/noble/InRelease`.
