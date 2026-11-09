# `create.yml` fails with "fatal: unable to read tree (<sha>)" after a commit made during the build

Seen 2026-11-09 (slice 7, L2 rebuild on de.NBI). The build was started from a pushed commit; a doc-only
commit was made in the same worktree while it ran, not yet pushed. The instance's checkout of the repository
clone then failed:

```
fatal: unable to read tree (18f8e902c99fb80a7367a36fd890ac19001e12ef)
```

`spe_repo_ref` defaults to `lookup('pipe', 'git -C <playbook_dir> rev-parse HEAD')`
(`inventory/group_vars/all.yml`). Ansible evaluates it lazily, at each task that reads it, so a commit made
after the build started is the one the VM is asked to check out, and the VM's clone cannot fetch an unpushed
commit.

**Fix:** don't commit in the controller's checkout while a build runs, or push first; or pin the ref for the
run: `-e spe_repo_ref=$(git rev-parse HEAD)` (after the push).
