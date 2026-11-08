# 2026-11-08: denbi controller setup 2


Continues `2026-11-08T0201Z-denbi-controller-setup.md` (read only this one). Same goal: this guest as a working
controller. Direct mode, main checkout, no unit, no PR. Gotchas found: `docs/knowledge/machines/nixed-microvm.md`.

## Done

- **Ansible**: `uv tool install --force ansible --with-executables-from ansible-core` (core 2.21.6, in
  `~/.local/bin`). `platform/dev/tests`: 91 passed, 0 skipped, 5 failed (`test_make_dummy_dataset`, samtools).
- **Coder CLI**: `~/.local/bin/coder` v2.38.6 from the portal; not logged in.
- **Chat UI**: `npm ci`, `npm test` 248 passed, `npm run build` ok.
- **SSH, not through yet**: the jump host's key was accepted on first use (fingerprint in the note); the login
  failed because the host's `~/.ssh/denbi` is 0644, so ssh offers no key. The handoff's `-F ~/.ssh/config`
  command can't work here (the note says why); use the scratch-config form in the note.

## Next: everything waits on the user

1. Host: `chmod 600 ~/.ssh/denbi`, and add `IdentitiesOnly yes` to the de.NBI blocks of the host's
   `~/.ssh/config`. Then once, with the note's scratch config (with `StrictHostKeyChecking accept-new` for
   `10.57.204.214`'s first use): `ssh -F "$S/ssh_config" -o BatchMode=yes agent-service-1 'hostname; sudo -n true && echo sudo-ok'`.
2. `! coder login https://sperange.bihealth.org`, then `coder whoami`, `coder list`.
3. samtools/htslib for the dummy dataset: add to nixed's guest packages (offered, not decided); then rerun
   `platform/dev/tests`.
4. Still raised: `platform/ansible/instances/test-1.yml` is tracked with a real-looking `spe_denbi_api_key`
   (previous handoff, *Flag for the user*).

## Update, same session

- Items 1 and 3 done: the user fixed the host key's mode and `IdentitiesOnly`; `ssh agent-service-1` gives
  `hostname` and `sudo-ok`. samtools/htslib/bcftools 1.25 from a micromamba env, linked into `~/.local/bin`
  (no rebuild); `platform/dev/tests` 96 passed.
- Item 2 dropped for now: the user has lost access to the Coder portal. End to end runs without Coder, from this
  checkout (`create.yml` against de.NBI: ask before creating or destroying instances).
