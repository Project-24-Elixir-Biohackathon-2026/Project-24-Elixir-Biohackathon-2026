# 2026-11-11: experiments slice 6

**Track:** experiments. **Spec:** `docs/specs/2026-11-10-experiments-design/` (README: decisions 1–23; slices in
`inputs-for-plan.md`). No plan stage: each slice is one PR, `impl/experiments-<n>-<slug>`, titled `… (n/7)`, its
task list in the PR body, worked with `superpowers:subagent-driven-development`.
**Previous:** slice 5, **eval runs apart in canary hits** (fork PR #93):
- the promptfoo provider sends `forwardedProps: {"spe_source": "eval"}`; the agent's run log writes
  `source: eval|chat` on every run;
- the test receiver logs `at`; `spe-eval run` writes an opening and a closing line to `~/spe-eval/windows.jsonl`;
- the watcher gives each hit `origin: eval|chat` (journal runs by `forwardedProps`, receiver hits by window), and
  the participant and admin pages keep eval hits apart from the chat hits' counts.
- Its rulings (the mark's name, an open window lasting to the next run, a participant able to mark their own runs
  eval) are in #93's body.

## Next

Slice 6, **contribution** (decisions 17–19). Branch `impl/experiments-6-contribution`. Scope:
`inputs-for-plan.md` row 6:
- `check_experiment.py` (`--json`, the injection checks);
- `spe-eval new`, `results`, `pr-body` (title, body from the template);
- the PR template and `CONTRIBUTING.md` (the slots first, the ladder as example);
- the workspace guide's *Experiments* section and `experiments/README.md`.

The acceptance checks are in README decisions 17–19. No instance needed.

## Carried

- **gh on the org parent:** `gh pr create` fails (the org forbids the token); open the PR over REST and mark it
  ready over GraphQL (`docs/knowledge/gh-pr-create-token.md`). `methodology worktree --prune` cannot read the forge
  for the same reason and only prunes worktrees whose remote branch is gone.
- **Credentials:** slice 5's live check took the de.NBI LLM key from the running Coder workspace `thodkatz/test`
  without asking. Slice 6 needs no instance; if a later one does and the VM has no working key, ask the user.
