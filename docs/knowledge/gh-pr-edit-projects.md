# `gh pr edit` fails on Projects (classic)

**Symptom.** `gh pr edit <n> --body-file F` prints `GraphQL: Projects (classic) is being deprecated in favor of
the new Projects experience … (repository.pullRequest.projectCards)` and leaves the body unchanged (a label in
the same call may still be applied).

**Fix.** Edit the body through REST:
`gh api -X PATCH repos/thodkatz/elixir-biohackathon-2026-test/pulls/<n> -F body=@F -q '.body|length'`.
Labels: `gh pr edit <n> --repo thodkatz/elixir-biohackathon-2026-test --add-label X` still works, or
`gh api repos/…/issues/<n>/labels -f 'labels[]=X'`.
