# GitHub over SSH: "Permission denied (publickey)" on some attempts only

**Symptom.** On the development VM (2026-11-04, from about 09:40 UTC), `git fetch origin` failed with
`git@github.com: Permission denied (publickey).` / `fatal: Could not read from remote repository.`, although
pushes over SSH had worked at 08:19 the same day. Plain retries mostly failed too.

**Not the cause.** The key and the VM are fine:

- The VM's key (`~/.ssh/id_ed25519`, comment `smolvm-auto`, `SHA256:aFQagYaT…FBYxBFQ`, set by agentvm through
  `/etc/ssh/ssh_config.d/agentvm.conf`, `IdentitiesOnly yes`) is registered on the account:
  `curl -s https://github.com/thodkatz.keys` lists it.
- `ssh -v -T git@github.com` offers the same key every time. GitHub answers `Server accepts key` …
  `Hi thodkatz!` on some attempts and `Permission denied (publickey)` on others, on both of its addresses
  (`140.82.121.3` and `.4`). In one run of 6 attempts, 3 were rejected; another time 1 of 4 `git ls-remote` attempts
  passed.
- githubstatus.com said "All Systems Operational".

So GitHub's side rejects a valid key on some attempts; nothing in the VM changed.

**Workaround.** Use HTTPS with the `gh` token. `~/.gitconfig` already has `gh auth git-credential` as the
credential helper for `https://github.com`, and `git fetch https://github.com/thodkatz/elixir-biohackathon-2026-test.git
main` worked while SSH failed:

```bash
git -c url."https://github.com/".insteadOf=git@github.com: fetch origin     # per command
git config --local url."https://github.com/".insteadOf git@github.com:     # this repo and all its worktrees
git -C .methodology config --local url."https://github.com/".insteadOf git@github.com:   # the submodule too
```

Set with `--local` on 2026-11-04 (not `--global`), meant to stay only while GitHub rejects the key. Once
`ssh -T git@github.com` passes every time again, undo it in both places:
`git config --local --unset url."https://github.com/".insteadOf` (and the same with `-C .methodology`).

Or retry until one attempt is accepted: `for i in $(seq 10); do git push origin <ref> && break; sleep 3; done`.
To tell this failure apart from a missing key: `ssh -v -T git@github.com 2>&1 | grep -E 'accepts|denied'` a few
times. A mix of `accepts` and `denied` means this case.
