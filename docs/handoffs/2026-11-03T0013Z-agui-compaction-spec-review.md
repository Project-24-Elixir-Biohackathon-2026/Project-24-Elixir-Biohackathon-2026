# 2026-11-03: AG-UI compaction spec, address the review round

Hop 1 of the compaction spec unit, on branch `spec/agui-compaction` (worktree
`.claude/worktrees/spec-agui-compaction`), PR #15 (ready, label `spec`). Hop 0 hit the context budget right
after the round. The user's instruction still holds: `2026-11-02T2351Z-agui-chat-minors-next.md`, *The
user's instruction*. Paid Haiku runs are approved, there are no upstream PRs, and the spec gate is delegated.

## State

- Spec: `docs/superpowers/specs/2026-11-03-agui-compaction-design.md` (`4770b4c`). Also in the PR: the
  `docs/README.md` row, two `BACKLOG.md` lines and a *Current work* line in `AGENTS.md`.
- The `spec` label did not exist on the fork; hop 0 created it.
- Local review round done: 21 numbered findings posted as one comment
  (https://github.com/thodkatz/elixir-biohackathon-2026-test/pull/15#issuecomment-6591845601). **None
  addressed yet.** Do not run a second round.

## Next

1. Fix every finding in the spec, BACKLOG, README row and AGENTS line (one or a few commits, `git commit -s`).
   Then reply in **one PR comment**, one line per finding number, naming the commit.
2. Add `approved` (`gh api repos/{owner}/{repo}/issues/15/labels -f "labels[]=approved"`) with a PR comment
   quoting the user's instruction. In the same PR, mark the README row "(approved, #15)" and set the spec's
   status line to approved.
3. Merge squashed (sign-off: `docs/knowledge/gh-squash-signoff.md`), clean up, move the parent pin, write
   the plan's handoff, then `next-session.sh --next plan/agui-compaction <handoff>`.

## Facts already checked (do not re-derive)

- #1: `COMPACTION_ACTIVITY_TYPE = 'pydantic_ai_compaction'` (`pydantic_ai/ui/ag_ui/_utils.py:71`); use
  that string everywhere `"compaction"` appears (§5, §6, §7, decisions 7, 8, 10).
- #2: `_agent_graph.py:1488`: "`on_model_request_error` cannot recover an error after streaming has
  begun"; the reactive path is in `wrap_model_request`: catch the overflow the handler raises, compact,
  then `model.request` directly and return that response. Test through `AGUIAdapter.run_stream`.
- #4: `models/anthropic.py:1490`: any `CompactionPart` in the request turns on the `compact-2026-01-12`
  beta, so strip every `CompactionPart` from what is sent.
- #9: the de.NBI model is `spe_webui_model_id: qwen3.8-27b` (`inventory/group_vars/all.yml:171`), and
  `spe_agent_model` derives from it (l. 183). Set `spe_agent_context_window_tokens` beside it, not in the
  Coder presets, which can only set existing `coder_parameter`s. The portal follows upstream, so
  participants get it only through a later upstream port: say so; no upstream PR now. `verify.yml` checks
  live in `roles/agui/tasks/checks.yml`: add a task there that shows the rendered `compaction` block.
- #21: stale texts to name in *Inputs for the plan*:
  - `platform/agui/pydantic-ai-agent/README.md:59` (*Runs*: "builds its history from the request alone");
  - `docs/specs/2026-10-15-agui-frontend-design.md:243` (*History*; upstream's spec, so a slice changes it
    only if it is ported, or the fork notes it);
  - a clarification on the chat sessions spec for its §4 archive layout and `index.md` columns;
  - a canary-ladder item in `BACKLOG.md` (runs may be compacted; scoring reads `compactions`).
- #15: let slice 1 also render `compaction.*` in Ansible, or let slice 2 pass `-e` for the window. For an
  early summary sample, run the package prompt on Haiku over one long session before the run-log work.
- #19: BACKLOG house form is ", waits because …".

## Lessons

- The context budget went on library reading (pydantic-ai 2.56 internals). Hand that reading to Explore
  subagents next time: hop 0 read `_agent_graph.py` and `anthropic.py` itself.
