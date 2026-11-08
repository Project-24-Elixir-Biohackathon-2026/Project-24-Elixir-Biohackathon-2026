# 2026-11-08: denbi controller setup

Goal (the user's): make this guest (`agentvm-thinkrepos`) a working controller: run every test in *Running
things*, and reach de.NBI end to end. Direct-mode work in the main checkout; no unit, no PR.

## Done

- **SSH**: nixed `00b3ca4` shares the host's `~/.ssh` read-only at `/mnt/host-ssh` (switch run by the user,
  verified: writes refused, timer `agentvm-host-ssh` active). `~/.ssh/denbi` links to the host's key; `ssh -G`
  resolves `denbi-jumphost-01` (user `thodkatz`, `IdentityFile ~/.ssh/denbi`) and `agent-service-1`,
  `spe-ga4gh-api-2`, `wes-service-1` (ProxyJump through it).
- **Tests run here**: `validate.py` ok; agent 239 passed; promptfoo 18 passed; `platform/dev/tests` 81 passed,
  5 failed (`test_make_dummy_dataset`: `samtools not found on PATH`), 10 skipped (`ansible-playbook not
  installed`). The chat UI's `npm ci && npm test` / `npm run build` not run yet.
- Docs cleaned of the submodule era (`5a62e54`, `c8e17c0`).

## Next, in order

1. **SSH check, once, with exactly one key.** The host config's jump-host block has **no `IdentitiesOnly yes`**
   (`ssh -G` says `identitiesonly no`), and the guest also has `~/.ssh/id_ed25519`: offering both risks the jump
   host's ban (`docs/getting-started.md`, step 3). So:
   `ssh -o IdentitiesOnly=yes -o BatchMode=yes -F ~/.ssh/config agent-service-1 'hostname; sudo -n true && echo sudo-ok'`
   and tell the user to add `IdentitiesOnly yes` to both blocks on the host (live in the guest at once).
2. **Ansible**: not on PATH. `uv run --with ansible ansible-playbook --version` works (core 2.21.6, bundled
   collections). Pick a lasting form (`uv tool install ansible` gives `ansible-playbook` on PATH, user-level, no
   root) and rerun `platform/dev/tests` (the 10 skips). The Nix store is read-only: system packages are nixed's
   (`microvms/guest/extras/`), a change there needs the user's switch.
3. **Coder CLI**: `curl -fsSL https://sperange.bihealth.org/bin/coder-linux-amd64 -o ~/.local/bin/coder && chmod
   +x ~/.local/bin/coder` (same version as the portal; `docs/knowledge/denbi-llm-key.md`). The token: the user
   runs `! coder login https://sperange.bihealth.org` (browser), or gives a token for
   `coder login --token <t> https://sperange.bihealth.org`; it lands in `~/.config/coderv2/session`, never in a
   repo. Verify with `coder whoami` and `coder list`.
4. **samtools/bgzip/tabix** for the dummy dataset: the user stopped a micromamba (bioconda) env in `~/.local/share`;
   ask nothing more there: the lasting fix is adding `samtools` and `htslib` to the guest packages in nixed
   (offered, not decided). Without them `~/spe-dummy-data` can't be generated.
5. Chat UI tests (`npm ci && npm test`, `npm run build`).

## Flag for the user (raised, not acted on)

`platform/ansible/instances/test-1.yml` is **tracked** (upstream `9693dc4`, on GitHub) with a real-looking
`spe_denbi_api_key` (`sk-…`, 25 chars) and seed. If live, revoke it; removal is a new commit (upstream first), no
history rewrite.
