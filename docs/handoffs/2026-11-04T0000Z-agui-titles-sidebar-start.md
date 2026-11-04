# Handoff: AG-UI model titles and resizable sidebar (Change #29), implement

**Unit:** `change/agui-titles-sidebar`, draft PR #29 (label `change`), worktree
`.claude/worktrees/change-agui-titles-sidebar`. Claimed; nothing implemented yet. **The plan and the checks are
the PR body** (`gh api repos/thodkatz/elixir-biohackathon-2026-test/pulls/29 -q .body`; `gh pr view`/`edit` fail on
Projects classic, `tooling-gotchas.md`). Asked for by the user 2026-11-03 as a Change, not Full mode.

## Next

1. Implement with `superpowers:subagent-driven-development`, sequentially in this worktree: task A the agent
   (`POST /title`, `title_prompt.md`, config `title`, run-log `type: "title"`, tests), task B the chat UI (route
   `POST /api/sessions/{id}/title`, reading the first user message and answer from the journal, re-check before
   the `meta` append, the browser's one call after the first reconciled run), task C Ansible
   (`spe_agent_title_generation` → `agent.yaml`, like `spe_agent_compaction_*`, `roles/agui/tasks/main.yml:24-48`,
   `checks.yml:48-53`), task D the sidebar (`lib/sidebar-width.ts` + tests, handle in `app/sidebar.tsx`,
   `--sidebar-width` in `app/globals.css:85`), task E the spec (§6 *Sessions*, session API table, *Layout*;
   §5 *Configuration*, *Run log*; a clarification) and `BACKLOG.md` (delete the *AG-UI chat minors* item; add
   *nicer tool-call cards*, below).
   Task F, asked for by the user after the plan was written: a light/dark theme toggle. Today there is none: the
   theme follows the OS only (`prefers-color-scheme` in `app/globals.css`, `useSystemColorScheme` `app/page.tsx:298`,
   `colorScheme: "light dark"` `app/layout.tsx:8`). Add System / Light / Dark (e.g. in the sidebar's footer, as
   Open WebUI's settings offer), kept per browser in `localStorage` (try/catch), `data-theme` on `<html>` overriding
   the media query, applied before paint (no flash); spec §6 *Layout*. Add it to the PR body's plan first.
2. Check who reads `runs.jsonl` before adding the `type: "title"` line (exporter, `write_run.py`, promptfoo
   provider/scoring): a reader that assumes every line is a run must skip it, with a test.
3. Local review round (correctness + methodology), merge squashed, clean up, move the pin in `biohackathon`.
4. Redeploy `denbi-agui-01` from `main` and try it (approved by the user, `BACKLOG.md`).

## Map (from an Explore pass, line numbers at `a36f8a0`)

- Agent: FastAPI `create_app` `app.py:231-270`, auth `Service.authorized` `:182-184`, the model `Service._model`
  (`agent.py:30-39`); tool-free call pattern `Compaction._summary_request` `compaction.py:318-327`; `RunLog.write`
  `runlog.py:57-71`; config classes `config.py:70-84` (`_Strict`, `extra="forbid"`).
- Chat UI: agent URL/key `app/api/copilotkit/[[...slug]]/route.ts:16-33`; run end `lib/recorder.ts:124-142`; meta
  `Journals.patch` `lib/sessions.ts:359-366`, `parsePatch` `:46-84`, `autoTitle` `:86-92` (never journaled:
  `entry.title === null` means no title set); list refresh `app/use-run-reconcile.ts`, `lib/reconcile.ts`.
- Spec `docs/specs/2026-10-15-agui-frontend-design/06-chat-ui.md`: title rule lines 36-40 (`title_source` was
  dropped, line 57), API table 56-58, layout 79; `13-conversation-record.md` meta row 116.

## Open WebUI reference (0.11.3, in `theo/theo-workspace`'s container)

Title: `DEFAULT_TITLE_GENERATION_PROMPT_TEMPLATE` (`/app/backend/open_webui/config.py:2224`, `{{MESSAGES:END:2}}`),
run in the background after the first reply (`main.py:1448-1469`). Sidebar: `sidebarWidth` store, default 245,
resize handlers. Tool calls (the follow-up Change): `src/lib/components/common/ToolCallDisplay.svelte`, read from
the build's source maps:
`coder ssh theo/theo-workspace "docker exec spe-frontend-open-webui-1 python3 -c '…sourcesContent…'"` — status icon
(spinner + shimmer / check / ✕), "Executing X…" / "View Result from X", input as key/value rows, output in a code
block, grouped calls. BACKLOG line for it: *AG-UI chat: tool-call cards like Open WebUI's `ToolCallDisplay`*,
chat UI only (`ToolCard`, `app/page.tsx:73`, and its CSS), plus a `$ command` line and an error state; next Change
after #29.

## State elsewhere

- `denbi-agui-01` redeploy from `main` `cab5a1d` (conversation record) was started detached
  (`setsid nohup … create.yml -e @instances/denbi-agui-01.yml -e spe_min_free_gb=5`, log in the previous session's
  scratchpad `/var/tmp/claude-1000/-workspace-biohackathon-biohackathon-elixir-biohackathon-2026-test/164063b2-4063-40b9-8f78-4e2e8404b0ae/scratchpad/redeploy.log`, ending in a line `EXIT <code>`); it was at "Agent and chat UI images
  built". Check `ssh -F ~/.ssh/config ubuntu@agent-service-1 'docker compose -p spe-frontend ps'` (new image tags
  mean it landed). The VM's `/` had ~7 GB free; the preflight's 15 needs `-e spe_min_free_gb=5`. The LLM key comes
  from the portal (`docs/knowledge/denbi-llm-key.md`). The user views it through a tunnel to the VM's port 3000.
- PR #28 (`/compact` slice 1/2) is open in another session and also edits the agent (`app.py`, config): expect a
  conflict there when merging; rebase onto `main` if it merges first.
