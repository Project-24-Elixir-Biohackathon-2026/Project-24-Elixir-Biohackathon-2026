# This repo on a nixed microVM guest

Notes that hold only on a nixed guest (`AGENT_MACHINE=nixed-microvm`), for this repo. The machine-wide notes are
`.methodology/machines/nixed-microvm.md`; the host-ssh items below belong there and stay here until a
`methodology update` brings them in.

## `ansible-playbook` on PATH

The Nix store is read-only and Ansible is not among the guest packages. `uv tool install ansible` installs only
`ansible-community` (`which: no ansible-playbook in …`): the commands come from `ansible-core`, a dependency. Use

    uv tool install --force ansible --with-executables-from ansible-core

which puts `ansible`, `ansible-playbook`, `ansible-galaxy` … in `~/.local/bin`, with the bundled collections
(`openstack.cloud`, `community.general`, `ansible.posix`). Run it with `</dev/null`, or under `script` when stdout
is also non-blocking (`ansible-nonblocking-stdout.md`).

## samtools, bgzip, tabix, bcftools

`platform/dev/tests` needs them (the dummy dataset; `test_spe_seed_accepts_it` also runs `spe_seed.py`, which
wants `bcftools`). No guest rebuild needed: `nix profile add` fails ("experimental Nix feature 'nix-command' is
disabled", then "creating directory \"/nix/store/.links\": Read-only file system"), and PyPI has no package with
the commands, but micromamba is installed:

    micromamba create -y -n spe-bio -c conda-forge -c bioconda samtools htslib bcftools
    for t in samtools bgzip tabix bcftools; do ln -sf ~/.micromamba/envs/spe-bio/bin/$t ~/.local/bin/$t; done

The lasting alternative is adding them to nixed's guest packages (a switch by the user).

## SSH to de.NBI through the host's `~/.ssh` share

The host's `~/.ssh` is shared at `/mnt/host-ssh`, and `/etc/ssh/ssh_config` includes `/mnt/host-ssh/config`.

- **`ssh -F ~/.ssh/config agent-service-1`: "Could not resolve hostname agent-service-1"**: `-F` skips
  `/etc/ssh/ssh_config`, so the host's blocks never load. Leave `-F` out, or use a config that includes it.
- **`-o IdentitiesOnly=yes` / `-o StrictHostKeyChecking=…` don't reach the jump host**: a `ProxyJump` child gets
  `-F` but not `-o`. To pin one key on both hops (the jump host bans clients that offer many keys,
  `docs/getting-started.md`, step 3) without the host's config saying `IdentitiesOnly yes`, use a scratch config:

      printf 'Host *\n  IdentitiesOnly yes\n  Include ~/.ssh/config\n  Include /etc/ssh/ssh_config\n' > "$S/ssh_config"
      ssh -F "$S/ssh_config" -o BatchMode=yes agent-service-1 'hostname; sudo -n true && echo sudo-ok'

  A fresh guest has no de.NBI host keys (the host's `known_hosts` has none either): the first connection gives
  "Host key verification failed"; add `StrictHostKeyChecking accept-new` to that scratch config for it, as
  Task 12 did (`docs/plans/2026-10-15-agui-frontend-progress.md`). Jump host, accepted 2026-11-08:
  `ED25519 SHA256:8ojvA8rKjb3wno5y5jumAmsWdNkHeuH/xKfKu7nQPSI`; agent-service-1 (`10.57.204.214`):
  `ED25519 SHA256:VTe3qymo0Nkk0J5bpKymm8J+iwBuNZANAzmkthsIq7o`. Once the host's config sets `IdentitiesOnly yes`
  (done 2026-11-08), a plain `ssh agent-service-1 …` is enough.
- **Instance files**: set `spe_existing_ssh_args: ""`, not the examples' `"-F /home/agentvm/.ssh/config"`, for
  the same `-F` reason (deployed this way to agent-service-1, 2026-11-08).
- **"Permissions 0644 for '/home/agentvm/.ssh/denbi' are too open … bad permissions", then "Permission denied
  (publickey,…)"**: the share passes the host file's mode through, and the host's `~/.ssh/denbi` was 0644, so ssh
  offers no key at all. Fix on the host: `chmod 600 ~/.ssh/denbi` (the share is read-only from the guest). Don't
  retry against the jump host until it is fixed: each try is a failed login there.

## `create.yml` against this guest itself (`dev-local`, `spe_existing_host: localhost`)

Found 2026-11-08 on `agentvm-thinkrepos`: this guest is NixOS, not the Ubuntu the playbooks target, so it cannot
be its own instance.

- **"timed out waiting for ping module test: 'ping'"** (after 600 s, task *Wait for SSH*): `existing_host` pins
  `ansible_python_interpreter: /usr/bin/python3`, which NixOS lacks (`/run/current-system/sw/bin/python3`). Past
  it with `-e ansible_python_interpreter=/run/current-system/sw/bin/python3`; the user is `agentvm`, not `ubuntu`
  (`spe_ssh_user: agentvm`).
- **"only 5 GB free on the filesystem of /, need 15"**: the root and `/home` are small; only `/var/tmp` (Docker's
  data root, ~29 GB) has room.
- After that, `base` installs packages with `apt` unconditionally: no way through without playbook changes.

Use an Ubuntu VM as the target (e.g. a de.NBI VM, or a local Ubuntu VM), or run the AG-UI agent and chat UI
directly for model-backed feature work.
