# Contributing upstream

How fork work reaches upstream (`Project-24-Elixir-Biohackathon-2026/Project-24-Elixir-Biohackathon-2026`, formerly `kraatz/elixir-biohackathon-2026-test`, remote `upstream`; PR numbers carried over, written `kraatz #<n>` in the ledger), and how upstream's
work comes back into our `main`. The rules (which files are fork-only, the check every upstream branch passes)
are in `AGENTS.md`, *Contributing upstream*; this guide is the procedure.

Upstream matters beyond the code review: the portal VM's checkout is cloned from upstream
(`platform/coder/README.md`, the `git clone` in its setup) and follows its `main`, and each new workspace builds
the AG-UI images from that checkout. Fork work reaches participants only once upstream has merged it.

Run everything below in bash: zsh does not split the `X` array the same way.

## Port fork work to upstream

### 1. Choose what goes

One upstream PR per coherent feature. It may carry several fork PRs (a track's slices) when upstream needs them
together. Each fork PR is one squash commit on our `main`.

`X` holds the fork-only paths as git pathspec excludes. It mirrors the fork-only list in `AGENTS.md`, *Contributing
upstream*, plus `AGENTS.md` itself, and changes with it:

```bash
X=(":(exclude).methodology" ":(exclude).claude" ":(exclude)AGENTS.md"
   ":(exclude)BACKLOG.md" ":(exclude)docs/README.md" ":(exclude)docs/guides" ":(exclude)docs/knowledge"
   ":(exclude)docs/investigations" ":(exclude)docs/proposals" ":(exclude)docs/superpowers" ":(exclude)docs/handoffs"
   ":(exclude)docs/upstream-ports.md")
```

A ported commit never leaves `upstream/main..main` (upstream gets a rewritten commit, not ours), so the fork keeps
a ledger, `docs/upstream-ports.md`: one line per fork commit already ported or ruled out. The candidates are the
fork commits with project changes that have no line there yet, oldest first:

```bash
git fetch upstream && git fetch origin
git log --abbrev=7 --format='%h %s' --reverse upstream/main..origin/main -- . "${X[@]}" \
  | grep -v -f <(git show origin/main:docs/upstream-ports.md | sed -n 's/^- `\([0-9a-f]*\)`.*/^\1 /p')
```

The ledger is read from `origin/main`, so its lines are committed and pushed to `main` directly. A candidate
upstream should not get (a fork-only change to a shared file) gets a `not for upstream` line there, so it stops
showing up.

If the work builds on an upstream PR that is still open, wait for it to merge, as with stacked PRs on the fork
(`development-workflow.md`, *Review and merge*, step 1). Work that only touches the same area can go in
parallel: step 3 says when a port actually needs the other one.

### 2. A worktree from `upstream/main`

`worktree.sh` starts from `origin/main`, which carries the fork-only files, so an upstream branch gets its own
worktree. Name the branch `contrib/<slug>`:

```bash
# from the main checkout
git worktree add -b contrib/<slug> .claude/worktrees/contrib-<slug> upstream/main
cd .claude/worktrees/contrib-<slug>
```

Upstream has neither `.methodology/` nor `.claude/settings.json`, so a session started in this worktree runs no
hooks (no context budget): work on it from a session started in the main checkout.
To chain such a unit's sessions, write the handoff in `docs/handoffs/` on `main`, push it, and run
`methodology next docs/handoffs/<file>` from the main checkout on `main` (`docs/knowledge/contrib-unit-chaining.md`).

Never open an upstream PR from `main` or from a `change/`, `spec/`, `plan/` or `impl/` branch: they carry the
fork-only files. Upstream once merged our methodology adoption PR that way (kraatz #8) and had to revert it
(`baa5d54`).

### 3. Port each fork commit as a filtered patch

A plain `git cherry-pick` stops on every fork-only file the commit touches (`CONFLICT (modify/delete):
BACKLOG.md deleted in HEAD`), since upstream does not have them. Take the commit's diff without those paths and
apply it three-way instead, with `X` from step 1:

```bash
git diff --binary <sha>^ <sha> -- . "${X[@]}" | git apply --3way --index
```

Exit code 0 means it applied. A conflict (`Applied patch to '<file>' with conflicts`) leaves markers to resolve
by hand, then `git add <file>`. Any `error: <file>: does not exist in index` means **nothing** was applied, not
even the files listed as applied: the commit depends on another fork commit that is not upstream yet; port that
one first (in this PR, or wait for its own upstream PR). `No valid patches in input` (exit 128) means the commit
touched only fork-only files: skip it.

Commit each fork PR as one upstream commit, signed off:

```bash
git commit -s -F <message file>
```

The message is the fork commit's, rewritten for a reader who has never seen the fork: drop the `(#n)` suffix
(fork PR numbers mean nothing upstream) and any plan, slice, handoff or review reference; keep the *why*. The
fork commit's subject `AG-UI chat sessions: the store (1/3) (#9)` becomes `AG-UI chat sessions: the store`. No
fork hash goes upstream: the link from fork commit to upstream PR lives in the ledger (step 6).

#### Or port a package: the final state of an area

When upstream should get a feature as its final state rather than commit by commit (the user's choice for the
AG-UI package, 2026-11-03), and `upstream/main` is an ancestor of `origin/main` (merged in, below), take the
files instead of the commits. The branch is then `origin/main`'s project files as they are now:

```bash
git merge-base --is-ancestor upstream/main origin/main && echo ancestor   # else merge upstream in first
git diff --name-only --no-renames upstream/main origin/main -- . "${X[@]}" > /tmp/package-paths
# keep only the paths of the package; deleted ones go with `git rm`
git checkout origin/main -- $(git ls-tree -r --name-only origin/main | grep -Fxf /tmp/package-paths)
git commit -s -F <message file>
```

Then edit by hand, one commit each: fork-only references the grep in step 4 finds, and upstream's own
`AGENTS.md`, whose project rules (paths, test commands, features) are written in on this branch, never copied
from ours. A package's code is `origin/main`'s byte for byte, so live checks that ran on that commit hold for
it; say which commit they ran on in the PR body. `contrib/agui-package` (2026-11-04) was cut this way.

### 4. Clean the text and check

Docs and code upstream also reads must not point at fork-only files. Grep what was added:

```bash
git diff -U0 upstream/main...HEAD | grep -E '^\+[^+]' \
  | grep -E 'superpowers|BACKLOG|upstream-ports|docs/(knowledge|guides|investigations|proposals)|\.methodology|\.claude/|handoff|slice [0-9]|\(#[0-9]+\)'
```

Each hit is rewritten or removed. Then run, in this worktree:

- the fork-only check in `AGENTS.md`, *Contributing upstream* (it must print `ok`);
- the test commands of `AGENTS.md`, *Running things*, for every area the PR touches. Upstream's code differs
  from ours, so tests that passed on the fork prove nothing here.

Live checks against an instance (browser runs, Ansible) are worth repeating only when upstream's side of the
change differs from what the fork tested; say which ran in the PR body.

### 5. Push and open the PR

The branch goes to our fork, never to `upstream`:

```bash
git push -u origin contrib/<slug>
```

`gh` cannot open the PR: its token covers the fork only (`docs/knowledge/gh-pr-create-token.md`). The user opens
it from the compare page, with the base set to upstream explicitly:

```
https://github.com/Project-24-Elixir-Biohackathon-2026/Project-24-Elixir-Biohackathon-2026/compare/main...thodkatz:elixir-biohackathon-2026-test:contrib/<slug>?expand=1
```

Post the title and body for them as an issue on our fork (`gh issue create --repo thodkatz/elixir-biohackathon-2026-test`,
the compare link at its top), so they copy from GitHub rather than from a file on the VM (the user, 2026-11-04);
close it once the PR is open. The body: what changes and why, how to try it, what ran (step 4), and for a UI
change screenshots embedded inline (the user, 2026-11-04). The API cannot attach images: commit them to the
fork's orphan branch `pr-assets` (`<slug>/<name>.png`) and embed
`https://raw.githubusercontent.com/thodkatz/elixir-biohackathon-2026-test/pr-assets/<slug>/<name>.png`. Take them
on prompts that show no canary value or seed: the PR is public. Nothing fork-only:
no plan, slice, backlog or fork PR links.

### 6. Track it on the fork

Once the PR has a number, record it on the fork, committed and pushed to `main` directly:

- `docs/upstream-ports.md` gets one line per fork commit the PR carries: `` - `<short sha>` <fork subject> →
  kraatz #<n> (open)``.
- Upstream PRs don't show in the fork's PR list, so `AGENTS.md`, *Current work*, gets a line while one is open:

  ```
  - **Upstream PR kraatz #<n>** (`contrib/<slug>`): <what>; waits on upstream's review.
  ```

Review comments upstream are fixed on the same branch, in new commits, pushed without force.

### 7. After upstream merges

Merge `upstream/main` back into our `main` (below), then clean up from the main checkout: `git worktree remove
.claude/worktrees/contrib-<slug>`, `git branch -D contrib/<slug>`, `git push origin --delete contrib/<slug>`,
drop the *Current work* line, and mark its ledger lines `(merged)`. If upstream closes the PR without merging,
mark them `(closed: <why>)`, record where the work goes instead (`development-workflow.md`, *Deferred items land
somewhere durable*), then clean up the same way. A closed line keeps its commit off the candidate list; delete the
line instead to offer the commit again later.

## Merge upstream into our `main`

Due after each upstream merge of our work, and whenever upstream's `main` has moved on. A Change-mode PR on the
fork:

```bash
cd "$(.methodology/shared/claude/worktree.sh change/merge-upstream-<yyyy-mm-dd>)"
git fetch upstream
git merge --signoff upstream/main
```

Resolving conflicts:

- **Fork-only files** (`AGENTS.md`, *Contributing upstream*): ours.
- **`AGENTS.md`**: ours, the fork's rewrite. Read upstream's diff to it (`git diff <merge base> upstream/main --
  AGENTS.md`) and carry each project rule it adds or changes into ours by hand, in the merge commit.
- **Files we ported upstream**: upstream's version holds our change plus its review fixes; take theirs unless
  the fork has moved on since the port, then combine.
- **Anything else**: a real conflict between two lines of work; resolve it and say how in the PR body.

Run the test commands for every area the merge touched, then the review round as for any PR; the methodology
focus checks the `AGENTS.md` resolution.

DCO stays red on such a PR: upstream does not sign off, and its commits are not ours to rewrite. Merge anyway
when every commit DCO flags is upstream's (`git merge-base --is-ancestor <sha> upstream/main`), and say so in the
PR body (the user, 2026-11-04, #35).

Merge it with a merge commit, not a squash (`AGENTS.md`, *Overrides*):

```bash
gh api -X PUT repos/thodkatz/elixir-biohackathon-2026-test/pulls/<n>/merge -f merge_method=merge
```

A squash would drop `upstream/main` as a parent, so the next merge from upstream would re-merge every upstream
commit since the old base, and conflict wherever the fork has changed those lines since. `c1b1f24` is such a merge commit.
