# 2026-11-08: agui notes brainstorm


Read only this one. The controller setup (previous handoff `2026-11-08T0211Z-denbi-controller-setup-2.md`) is
done except the model: `denbi-agui-01` is deployed on agent-service-1 with the blocked key; de.NBI model testing
is off the table (no working key without Coder, `docs/knowledge/denbi-llm-key.md`). The user moved on to
model-free backlog work. **Every piece also goes upstream to kraatz** (user, 2026-11-08): after the fork PR
merges, a `contrib/<slug>` branch per `docs/guides/contributing-upstream.md`; the user opens the upstream PR.

## Running when this was written (subagents of the previous session)

- `change/agui-archive-markdown`: compaction-line wording (+ spec clarification), GFM autolinks in `md_inline`,
  refused-run status repeat, `when()` on non-numeric timestamps; then `contrib/agui-archive-markdown`.
- `change/agui-chat-ui-polish`: scroll to newest on session reopen, `⋯` focus after outside click; then
  `contrib/agui-chat-ui-polish`.
Check their PRs (`gh pr list --repo thodkatz/elixir-biohackathon-2026-test --state all --limit 5`) and the
contrib branches; finish whatever a cut-off agent left (merge, cleanup, contrib push, `docs/upstream-ports.md`).
Give the user the compare URLs. Not to do: CI wiring and the client-`tools` drop (user: "except the ci and the tools").

## Next: the notes feature (brainstorming, full mode, spec in `docs/specs/` since it goes upstream)

The user: "let's do the feature of having notes … wired in our storing scheme", "we should follow openwebui
approach we want a similar feature". Last open question to the user: how per-person ownership maps, given the
AG-UI chat has no users. Continue `superpowers:brainstorming` from their answer.

Recon done (Open WebUI 0.11.3, `/app/backend/open_webui/models/notes.py` in `agent-stack-open-webui-1` on
agent-service-1):
- table `note`: `id` uuid, `user_id`, `title`, `data` JSON (`content.md` canonical, plus `html`/`json` from the
  rich editor), `meta` JSON, `created_at`/`updated_at` (ns); sharing by access grants (read/write, user or
  group); pinning per user in `pinned_note` (user_id, note_id). API `/api/v1/notes/`, `/create`, `/{id}/pin`.
- Our run report: `platform/ansible/reports/run_report.md.j2`, created once as pinned note "Run report" by
  `roles/openwebui/tasks/main.yml` (~74–138, rendered to HTML), exported by `roles/run_archive` (`export.yml`,
  `write.yml` ~105 "Chats, notes and report"). The AG-UI archive's `index.md` says it has no report.
- AG-UI chat storage: `platform/agui/copilotkit-chat/lib/sessions.ts`, `journal.ts`, `export.ts`, API
  `app/api/sessions/`; sessions belong to the instance (no auth; BACKLOG "Chat sessions with owners").
- Proposal put to the user: instance-owned notes as Markdown alongside session journals, pinnable, the run
  report as a pinned note created at deploy, archived with the sessions; per-person needs chat identity first.
- Backlog item it closes: "A run report in the CopilotKit chat" (`BACKLOG.md`).

**Answered after writing (user, 2026-11-08):** "each user is meant to has its own openwebui and agui instance".
Open WebUI here has one seed-derived admin account per instance, so its per-user notes are per-instance in
practice. Settled: AG-UI notes are owned by the instance; no identity work. Next in the brainstorm: lay out the
approaches (storage beside the session journals, editor, pinning, run report at deploy, archive), then the spec.
**Also settled (user, 2026-11-08):** aligned with Open WebUI as above: standalone notes (not per session),
Markdown canonical, per-instance pin, run report as a pinned note, archived; no sharing/access grants. **No AI
"enhance" button** ("definitely not"). **A rich-text editor if it is not a large piece of code**: Open WebUI uses
TipTap; size `@tiptap/react` (+ markdown round-trip) against a lighter Markdown editor and propose one with its
bundle and code cost.
