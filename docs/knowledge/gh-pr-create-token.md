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

**`gh pr create` on the fork fails since upstream moved into an organization** (seen 2026-11-08). Upstream
`kraatz/elixir-biohackathon-2026-test` now redirects to
`Project-24-Elixir-Biohackathon-2026/Project-24-Elixir-Biohackathon-2026`, and `gh pr create --repo
thodkatz/elixir-biohackathon-2026-test` stops with:

```
GraphQL: The 'Project-24-Elixir-Biohackathon-2026' organization forbids access via a fine-grained personal access tokens if the token's lifetime is greater than 366 days. ... (repository.parent)
```

Its GraphQL query reads the fork's parent, which lives in that organization. The REST call touches only the fork
and works: `gh api repos/thodkatz/elixir-biohackathon-2026-test/pulls -f title=… -f head=<branch> -f base=main
-F draft=true -f body=… --jq .number`, then add the label with `gh api …/issues/<n>/labels -f "labels[]=<label>"`.

`gh pr ready <n>` fails the same way. REST cannot mark a draft ready either: `gh api -X PATCH …/pulls/<n> -F
draft=false` answers 200 and leaves `"draft": true`. The GraphQL mutation alone, which does not read the parent,
works (#46, 2026-11-08):

```bash
ID=$(gh api repos/thodkatz/elixir-biohackathon-2026-test/pulls/<n> --jq .node_id)
gh api graphql -f query="mutation { markPullRequestReadyForReview(input:{pullRequestId:\"$ID\"}) { pullRequest { isDraft } } }"
```

**`methodology gate approve` fails the same way** (seen 2026-11-08, #55): `methodology gate: could not read #55's
labels; nothing is done.` Its `forge_labels` runs `gh pr view <n>` without `--repo`, which resolves the fork's parent
in the organization. `gh repo set-default thodkatz/elixir-biohackathon-2026-test` (`gh-default-repo.md`) does not
help: tried 2026-11-08, `gh pr view 55` still fails on `repo_001.parent`; only `--repo` avoids it. A shared-tool bug
(`.methodology/shared/claude/forge.sh`'s `forge_labels`), to carry to agent-methodology; keep this until a
`methodology update` brings the fix. Do its two steps by hand, in its order (the comment first):

```bash
R=repos/thodkatz/elixir-biohackathon-2026-test
B=$(mktemp)
printf 'The user approved this spec in this session, at %s:\n\n> <their words>\n' "$(date -u +%Y-%m-%dT%H:%MZ)" > "$B"
gh api $R/issues/<n>/comments -F body=@"$B" && gh api $R/issues/<n>/labels -f "labels[]=approved"
```
