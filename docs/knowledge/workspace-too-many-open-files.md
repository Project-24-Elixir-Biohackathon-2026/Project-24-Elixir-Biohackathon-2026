# `/workspace`: "Too many open files" on file-heavy git operations

**Symptom.** On the development VM (2026-11-04), `git worktree add` under `/workspace` failed part-way:
`error: unable to create file docs/…: Too many open files`, `unable to open loose object …: Too many open files`.
A plain `sed` on a file under `/workspace` failed the same way (`couldn't close …: Too many open files`). The
half-made worktree directory was gone right after.

**Not the cause.** The guest's limits were fine: `/proc/sys/fs/file-nr` showed about 1400 handles open,
`ulimit -n` was 1048576, and no process held more than 500. The limit is on the side of the `/workspace` mount,
not in the guest.

**Workaround.** Retry, or avoid checkouts. To commit a few files to `main` without a worktree, use git plumbing
with a temporary index:

```bash
export GIT_INDEX_FILE=$(mktemp)
git read-tree origin/main
git update-index --add --cacheinfo 100644,$(git hash-object -w FILE),PATH
git commit-tree $(git write-tree) -p origin/main -m "…"   # then: git push origin <sha>:main
```
