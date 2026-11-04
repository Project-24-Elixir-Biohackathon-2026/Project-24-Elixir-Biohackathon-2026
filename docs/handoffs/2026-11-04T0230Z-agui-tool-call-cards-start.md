# Handoff: AG-UI chat tool-call cards (Change), start

**Unit:** `change/agui-tool-call-cards`, a Change (one PR, the plan in its body). Nothing is claimed yet: the first
session claims it (branch pushed, draft PR, its worktree).

## What

The chat UI's tool-call cards, like Open WebUI's `ToolCallDisplay`. `BACKLOG.md`'s *Next* item *AG-UI chat:
tool-call cards* holds the whole request (status icon, "Executing X…" / "View Result from X", arguments as
key/value rows, result in a code block, grouped calls, a `$ <command>` line for `run_command`, an error state).
It touches the chat UI only: `ToolCard` in `platform/agui/copilotkit-chat/app/page.tsx` and its CSS in
`app/globals.css`. The PR deletes that backlog item.

## Context from #29 (merged as `041a095`)

- #29 added the theme toggle. Dark tokens live in two identical blocks in `globals.css`, under
  `@media (prefers-color-scheme: dark) :root:not([data-theme="light"])` and under `:root[data-theme="dark"]`. A new
  colour token goes in **both** blocks and in the light `:root`.
- The living AG-UI spec is `docs/specs/2026-10-15-agui-frontend-design/` (upstream-bound: no links to fork-only
  files). The card's look belongs in §6 (`06-chat-ui.md`), and a clarification goes in `clarifications.md` (latest
  is 16).
- Open PR #30 (`/compact` slice 2/2, another track) also edits the chat UI. Check whether it touches `app/page.tsx`.
  If it merges first, merge `origin/main` into the branch (`git merge --signoff`), don't rebase.
- On this VM, `/workspace` intermittently answers "Too many open files" on file-heavy git operations (worktree
  checkout) while `/proc/sys/fs/file-nr` stays low. If `worktree.sh` fails that way, retry it.

## Not this unit

The `denbi-agui-01` redeploy for #29 waits on the user's OK (`BACKLOG.md` *Next*).
