# `/workspace`: "Too many open files" on file-heavy git operations

**Symptom.** On the development VM (2026-11-04), `git worktree add` under `/workspace` failed part-way:
`error: unable to create file docs/…: Too many open files`, `unable to open loose object …: Too many open files`.
A plain `sed` on a file under `/workspace` failed the same way (`couldn't close …: Too many open files`). The
half-made worktree directory was gone right after.

**Not the cause.** The guest's limits were fine: `/proc/sys/fs/file-nr` showed about 1400 handles open,
`ulimit -n` was 1048576, and no process held more than 500. The limit is on the side of the `/workspace` mount,
not in the guest.

**Fix.** Drop the guest's inode cache, then retry: `sync; echo 2 | sudo tee /proc/sys/vm/drop_caches`. The host's
virtiofs daemon holds a descriptor per cached inode (`dev-vm-converge.md`). Seen again on 2026-11-04 at 09:25: it
stopped `next-session.sh` from making `change/agui-coder-e2e-2026-11-04`'s worktree (PR #38), with
`fatal: cannot create directory at 'platform/agui/copilotkit-chat/app/api/sessions/[id]/title': Too many open
files`. A later attempt made the worktree complete (`git ls-files -d` empty), and dropping the cache left `file-nr`
at about 1400. The lasting fix is on the host: raise the virtiofs daemon's `LimitNOFILE`.

**Workaround** when the fix is not at hand: retry, or avoid checkouts. To commit a few files to `main` without a worktree, use git plumbing
with a temporary index:

```bash
export GIT_INDEX_FILE=$(mktemp)
git read-tree origin/main
git update-index --add --cacheinfo 100644,$(git hash-object -w FILE),PATH
git commit-tree $(git write-tree) -p origin/main -m "…"   # then: git push origin <sha>:main
```
