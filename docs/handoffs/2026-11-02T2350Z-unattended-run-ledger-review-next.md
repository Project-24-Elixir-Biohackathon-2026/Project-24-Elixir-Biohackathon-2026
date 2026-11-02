# 2026-11-02: unattended run, PR #13's review round next

Written 2026-11-02 at the context budget, in the worktree of `change/upstream-ports-ledger` (PR #13). No plan
holds this run of work, so its handoffs live here, in `docs/handoffs/`.

## The user's instruction (2026-11-02, in chat)

"Work unattended … finish the guide, resolve the issues occurred by ag ui chat and implement the compact feature,
don't open PRs on the parent [upstream kraatz] yet, let's have this functional on our fork. You are approved to do
anything that you need including running haiku and wherever you are blocked. Proceed with your recommendations."

So: no upstream PRs; paid Haiku runs (`claude-haiku-5-5`, dev VM) are approved; the spec gate is delegated: add
`approved` to the compaction spec PR yourself, with a comment quoting this instruction. Merge every fork PR
yourself (the user-merges override was dropped in `88fdd62`).

## Done this session

- #11 (AG-UI chat sessions 3/3) merged; track closed. Override "user merges every PR" removed (`88fdd62`).
- #12 merged (`bebd872`): `docs/guides/contributing-upstream.md`.
- #13 open, ready, label `change`: replaces the guide's `Fork-commit:` trailer with the fork-only ledger
  `docs/upstream-ports.md` (the user did not want fork hashes upstream). Body has plan, rule list, what ran.
  Check: step 1's command lists exactly the six chat-sessions commits; `sync-agents.py --check` exits 0.
- Parent `biohackathon` pinned at `bebd872` (`d459fcb`).

## Next, in order

1. **#13: local review round** (correctness + methodology subagents, one PR comment), address, reply, squash-merge
   via `gh api -X PUT …/pulls/13/merge -f merge_method=squash`, clean up, move the parent pin.
   This handoff file rides in #13; delete it in that PR's last commit or leave it (it is history).
2. **AG-UI chat minors**: the `AG-UI chat sessions:` items in `BACKLOG.md` *Unscheduled* (about 14). Change mode,
   `change/agui-chat-minors` (split into two PRs if it passes slice size). Fix what is cheap and safe; each fixed
   item leaves `BACKLOG.md` in the same PR. Tests: chat UI `npm test` + `npm run build`, `platform/dev/e2e/sessions.py`.
3. **Compaction / auto-compaction** (Full mode: spec → plan → slices). Today nothing handles the context limit:
   the CopilotKit chat resends the whole history, the agent passes it to the model untouched (no history
   processor in `platform/agui/pydantic-ai-agent/src/spe_agent/`), tool outputs are only cut at 1 MB
   (`sandbox.py`), a run allows 50 requests. On overflow the provider's error becomes RUN_ERROR in the red bar and
   every later message in that session fails the same way. `total_tokens_limit` is a spend cap, not a size cap.
   Questions for the spec: compact in the agent (pydantic-ai history processor) or the chat; trigger (token
   estimate vs. the model's window, or the provider's overflow error); manual "compact" action in the UI; how the
   summary is stored in the session record and shown; what the archive export renders.
4. Later, lower priority: merge `upstream/main` into our `main` (about 20 commits behind; the guide's last section).

## Not to forget

- `gh pr edit` fails (Projects classic): use `gh api` (`tooling-gotchas.md`). `gh` needs `--repo thodkatz/…`.
- zsh does not split arrays: run the guide's commands in `bash -c`.
