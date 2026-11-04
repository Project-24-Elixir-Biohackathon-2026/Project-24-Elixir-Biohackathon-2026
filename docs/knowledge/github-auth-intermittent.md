# GitHub refuses a valid key on and off: retry, don't reconfigure

**Symptom** (2026-11-04, afternoon). `git push origin` and `next-session.sh` fail with
`git@github.com: Permission denied (publickey)`; HTTPS pushes with gh's token answer
`! [remote rejected] … (Internal Server Error)`. The same morning the same key pushed fine.

**Cause: on GitHub's side, intermittent.** Three `ssh -o BatchMode=yes -T git@github.com` in a row: one "Hi
thodkatz! You've successfully authenticated", two refused, same key each time. The key is the VM's
`~/.ssh/id_ed25519` (`smolvm-auto`), which `/etc/ssh/ssh_config.d/agentvm.conf` sets for every host
(`IdentitiesOnly yes`); no SSH agent is involved, so `ssh-add -l` saying "Could not open a connection to your
authentication agent" is normal and not the cause. Check that the key is still on the account with
`curl -s https://github.com/thodkatz.keys` (`gh api user/keys` is 403 for this token). githubstatus.com showed
nothing for git operations at the time.

**What to do.** Retry the same command. Each failed push here passed on its first or second retry. Over HTTPS
with gh's credentials, the remote stays unchanged:

```bash
git -c credential.helper='!gh auth git-credential' \
  push https://github.com/thodkatz/elixir-biohackathon-2026-test.git HEAD:<branch>
```

Never `--force`, and no new keys or remotes.
