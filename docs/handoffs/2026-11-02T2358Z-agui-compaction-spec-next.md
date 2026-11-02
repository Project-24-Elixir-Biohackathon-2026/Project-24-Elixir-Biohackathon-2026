# 2026-11-02: AG-UI compaction spec, next

Written on `main` after PR #14 (AG-UI chat minors, squash `4157add`) merged. The user's instruction for this
run of work is quoted in `2026-11-02T2351Z-agui-chat-minors-next.md` (*The user's instruction*): it still holds.
Read that section, not the rest of that file.

## State

- `main` at the merge of #14 plus this handoff and two knowledge notes. The parent `biohackathon` pin moved to
  it in the same step (see `git -C .. log -1` in the parent).
- `BACKLOG.md`: of the AG-UI chat sessions items, four stay on purpose (`list()` parse cost, recorder body
  parse/clone cost, the stop-before-POST window, the click-outside refocus); each line says why.
- Chat sessions spec (`docs/superpowers/specs/2026-10-29-agui-chat-sessions-design.md`) has clarifications 6 and
  7 from #14, both folded.

## Next unit: the compaction spec (Full mode, stage 1)

Branch `spec/agui-compaction`, written with `superpowers:brainstorming` into `docs/superpowers/specs/`. The
user delegated the spec gate: once the review round is addressed, add `approved` yourself, with a PR comment
quoting the instruction. Then plan, then slices, as the workflow says.

The problem and the questions the spec must answer are in `2026-11-02T2351Z-agui-chat-minors-next.md`,
*Next, in order*, item 2 (no history processor in `platform/agui/pydantic-ai-agent/src/spe_agent/`; tool
outputs cut only at 1 MB in `sandbox.py`; 50 requests per run; overflow becomes a RUN_ERROR that repeats on
every later message; `total_tokens_limit` is a spend cap). Paid Haiku runs on the dev VM are approved.

Constraints from the chat sessions spec that compaction must keep: the session record stores the full
messages the browser sends (§1), the recorder writes what the run ends with (§2), and the archive renders every
message (§4); a compacted history has to say how each of those changes.

## Lessons (notes)

- `docs/knowledge/gh-pr-edit-projects.md`: `gh pr edit` fails, use `gh api -X PATCH`.
- `docs/knowledge/gh-squash-signoff.md`: sign a squash body off as the GitHub account, or omit `--body`.
- zsh does not split arrays: run multi-word variable commands in `bash -c`.

## Resume

```bash
.methodology/shared/claude/worktree.sh spec/agui-compaction   # if next-session.sh did not make it
git log --oneline -3; sed -n '/^## Next/,/^## /p' BACKLOG.md
```
