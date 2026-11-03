# `gh pr create` fails: "Resource not accessible by personal access token"

Seen 2026-10-22 on the development VM, opening a PR on our fork:

```
pull request create failed: GraphQL: Resource not accessible by personal access token (createPullRequest)
```

The REST call (`gh api -X POST repos/thodkatz/elixir-biohackathon-2026-test/pulls ...`) fails the same way
with HTTP 403, while `gh api repos/thodkatz/elixir-biohackathon-2026-test --jq .permissions` shows `admin: true`.
The account may do it; the token may not: `gh` here uses a fine-grained personal access token whose
repository access or *Pull requests* permission does not cover this repo. `git push` still works, because the
remotes use SSH, not the token.

Fix: give the token *Pull requests: Read and write* (and *Contents: Read*) on
`thodkatz/elixir-biohackathon-2026-test` in GitHub's token settings. Until then, push the branch and open the
PR from the URL `git push` prints (`https://github.com/thodkatz/elixir-biohackathon-2026-test/pull/new/<branch>`).

Granted on 2026-10-22; PR writes through `gh api` work since. `gh pr edit` still fails, for an unrelated reason
(Projects classic): use `gh api -X PATCH repos/<owner>/<repo>/pulls/<n> -F body=@file`
(`.methodology/shared/guides/tooling-gotchas.md`).

**Upstream PRs are opened by hand.** The token covers our fork only, so
`gh pr create --repo kraatz/elixir-biohackathon-2026-test` fails with the same error (seen 2026-10-29; re-probed
2026-11-03 with `gh api -X POST …/pulls -f head=thodkatz:__probe__ …`, HTTP 403). Push the branch to `origin` and
open the compare page with the base set to upstream explicitly:
`https://github.com/kraatz/elixir-biohackathon-2026-test/compare/main...thodkatz:elixir-biohackathon-2026-test:<branch>?expand=1`
— and this is now the standard end of an upstream unit: a session prepares one `contrib/<slug>` branch on the fork
(BACKLOG's *Upstream PR for the AG-UI package* item) and leaves the PR creation to the user. An old upstream PR
needs no write on kraatz either way: `gh pr merge --repo kraatz/…` is out of reach (403), so a merged upstream PR
is merged by the user, or by reauth as the kraatz owner..
