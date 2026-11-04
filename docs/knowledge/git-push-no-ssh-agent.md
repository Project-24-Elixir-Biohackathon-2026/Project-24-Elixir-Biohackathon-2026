# `git push` with no SSH agent: push over HTTPS with gh's credentials

**Symptom.** After a session continues on another account (`chain.sh`, "continues on claudeN"), `git push origin`
fails with `git@github.com: Permission denied (publickey)`; `ssh-add -l` says "Could not open a connection to your
authentication agent". The earlier push in the same conversation had worked.

**Fix.** `gh` is still logged in (`gh auth status`), so push over HTTPS with it, without changing the remote:

```bash
git -c credential.helper='!gh auth git-credential' \
  push https://github.com/thodkatz/elixir-biohackathon-2026-test.git HEAD:<branch>
```

The first try answered `! [remote rejected] … (Internal Server Error)` (2026-11-04); the same command again
succeeded. No `--force`, as always.
