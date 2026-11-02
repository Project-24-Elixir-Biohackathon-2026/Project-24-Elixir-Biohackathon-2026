# 2026-11-02: AG-UI chat minors next

Written 2026-11-02 on `main`, after PR #13 (`44a7649`, the upstream ports ledger) merged and the parent
`biohackathon` was pinned at it (`e9ff4ab`). No plan holds this run of work; its handoffs live here.

## The user's instruction (2026-11-02, in chat)

"Work unattended … finish the guide, resolve the issues occurred by ag ui chat and implement the compact feature,
don't open PRs on the parent [upstream kraatz] yet, let's have this functional on our fork. You are approved to do
anything that you need including running haiku and wherever you are blocked. Proceed with your recommendations."

So: no upstream PRs; paid Haiku runs (`claude-haiku-5-5`, dev VM) are approved; the spec gate is delegated: add
`approved` to the compaction spec PR yourself, with a comment quoting this instruction. Merge every fork PR
yourself. The guide part is done (#12, #13).

## Next, in order

1. **AG-UI chat minors** (this unit): the 14 `AG-UI chat sessions:` items in `BACKLOG.md` *Unscheduled*. Change
   mode, `change/agui-chat-minors`, split into two PRs if it passes slice size. Fix what is cheap and safe; each
   fixed item leaves `BACKLOG.md` in the same PR, the rest stay with a line on why. Tests: chat UI `npm test` +
   `npm run build`, `platform/dev/e2e/sessions.py`. Local review round, merge, move the parent pin.
2. **Compaction / auto-compaction** (Full mode: spec → plan → slices). Today nothing handles the context limit:
   the CopilotKit chat resends the whole history, the agent passes it to the model untouched (no history
   processor in `platform/agui/pydantic-ai-agent/src/spe_agent/`), tool outputs are only cut at 1 MB
   (`sandbox.py`), a run allows 50 requests. On overflow the provider's error becomes RUN_ERROR in the red bar and
   every later message in that session fails the same way. `total_tokens_limit` is a spend cap, not a size cap.
   Questions for the spec: compact in the agent (pydantic-ai history processor) or the chat; trigger (token
   estimate vs. the model's window, or the provider's overflow error); manual "compact" action in the UI; how the
   summary is stored in the session record and shown; what the archive export renders.
3. Later, lower priority: merge `upstream/main` into our `main` (about 20 commits behind; the guide's last section).

## Not to forget

- `gh pr edit` fails (Projects classic): use `gh api -X PATCH …/pulls/<n> -F body=@file`. `gh` needs
  `--repo thodkatz/…`.
- zsh does not split arrays: run the guide's commands in `bash -c`.
- In `bash -c`, `a || b | c` pipes only `b`: a test of step 1 once fed the whole ledger to `grep -v -f`.
