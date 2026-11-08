# The instance clone failed on the fork's private submodule

**Since 171398a (2026-11-06)** our fork has no submodule (`.methodology` is a git-ignored link to the machine's
install), so a clone of current commits cannot hit this. Keep `recursive: false`: an older `spe_repo_ref`, or a
submodule added later, would.

**Symptom.** `create.yml` with `spe_repo_url` set to our fork, at the task *Repository at <sha>* (role `repo`):
"Failed to init/update submodules: Submodule '.methodology' (git@github.com:thodkatz/agent-methodology.git) …
ERROR: Repository not found." (denbi-agui-01, 2026-11-04, the first deploy of upstream's clone-on-VM layout from
our fork).

**Cause.** `ansible.builtin.git` defaults to `recursive: true`, so it clones every submodule in `.gitmodules`.
Upstream has none; our fork has `.methodology`, which is private and reached over SSH, and the instance has
no key for it (nor needs it).

**Fix.** `recursive: false` on that task (PR #37). A clone the failed run left behind (`~/sperange` checked out,
`.methodology` empty) needs nothing: the next run updates it in place. A Coder workspace that fetches our
branch into `~/sperange` is not affected: `git fetch` does not initialise submodules.
