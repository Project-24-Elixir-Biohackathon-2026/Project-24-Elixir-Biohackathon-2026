# docs/ index

One line per document: what it covers and who reads it. Open the document only when your task needs it.

| Path | What | Read when |
|---|---|---|
| `../.methodology/shared/guides/` | the shared guides: workflow, sessions and context, spec and plan layout (the machine's install, through the `.methodology` link; never edited here) | see `AGENTS.md`, *Read on demand* |
| `guides/` | this repo's own guides (fork-only, `AGENTS.md`, *Contributing upstream*) | see `AGENTS.md`, *Read on demand* |
| `guides/contributing-upstream.md` | guide: porting fork work to upstream, and merging upstream back | you open a PR on upstream or merge `upstream/main` |
| `handoffs/` | handoffs of this repo's sessions outside any plan, one file each (fork-only) | you start a session from one: read only the newest |
| `upstream-ports.md` | ledger: which fork commits went upstream (kraatz PR) or are not for upstream (fork-only) | you choose what to port upstream |
| `knowledge/README.md` | as-you-go gotchas, one line each | before non-trivial work in an area |
| `specs/`, `plans/` | upstream's design specs and plans (the AG-UI frontend, the run report service), shared with upstream | when working on what they built |
| `specs/2026-10-15-agui-frontend-design/` | spec: the living AG-UI spec: agent, chat UI and sessions, Ansible, the conversation record (§13, approved, #19) and its archive (§14); shared with upstream | you change or plan anything in the AG-UI stack |
| `specs/2026-11-10-canary-hit-viewer.md` | spec: the canary hit viewer: a portal-VM watcher matching each workspace's trace against its canary record, the participant's live hits page and the admin page; written for upstream (its ladder parts apply where the ladder exists) | you plan or build canary hit detection for workspaces, or change `canarymatch.py` |
| `superpowers/specs/`, `superpowers/plans/` | our fork's specs and plans (fork-only, `AGENTS.md`, *Contributing upstream*) | when your unit names one |
| `getting-started.md` | deploying and using an instance by hand (upstream's) | before deploying |
| `investigations/` | one file per answered question (`sessions-and-context.md`, *Investigations and audits*) | when the question comes up again |
| `proposals/` | one file per unscheduled idea too big for a `BACKLOG.md` line; its line there points to it (`development-workflow.md`, *Deferred items*) | when its backlog line or your area's brainstorming leads you to it |
| `superpowers/specs/2026-10-22-canary-eval-ladder-design/` | spec: the promptfoo canary evaluation ladder L0–L5 (approved; built by the plan below) | you change, extend (L4/L5) or rerun the evaluation pipeline |
| `superpowers/plans/2026-10-22-canary-eval-ladder/` | plan: the ladder in ten slices, done (all ten merged; the agent runs' counts and matrix in `results/`); shared interfaces in its `README.md`, handoffs in `handoffs/` | you change or rerun the ladder, or look for why it works as it does |
| `superpowers/specs/2026-10-29-agui-chat-sessions-design.md` | spec: AG-UI chat sessions: sidebar, tags, server-side record, archive export (approved, #7; folded into the living AG-UI spec, #19) | you look for the sessions' decisions as approved; the current design is in `specs/2026-10-15-agui-frontend-design/` |
| `superpowers/plans/2026-10-29-agui-chat-sessions/` | plan: AG-UI chat sessions in three slices, done (all three merged); shared interfaces in its `README.md`, handoffs in `handoffs/` | you change the CopilotKit chat's sessions or the agui archive, or look for why they work as they do |
| `superpowers/specs/2026-11-03-agui-compaction-design.md` | spec: AG-UI compaction: the agent summarises the history when it nears the model's window or overflows (approved, #15) | you plan or build compaction in the AG-UI agent, chat or archive |
| `superpowers/plans/2026-11-03-agui-compaction/` | plan: AG-UI compaction in three slices (agent; chat and archive; de.NBI and docs); shared interfaces in its `README.md`, handoffs in `handoffs/` | you implement a slice of compaction |
| `superpowers/plans/2026-11-03-agui-conversation-record/` | plan: the AG-UI conversation record in four slices, done (all four merged); shared interfaces in its `interfaces.md`, handoffs in `handoffs/` | you change how `chat-ui` keeps a conversation or how the agui archive exports it, or look for why they work as they do |
| `superpowers/plans/2026-11-08-agui-leave-running-chat/` | plan: leaving a running AG-UI chat in three slices (rejoin check; an agent per session; rejoin, refresh, errors), done (all three merged); verdicts and rulings in its `progress.md`, handoffs in `handoffs/` | you change how the chat holds, rejoins or marks a running session, or look for why it works as it does |
| `superpowers/plans/2026-11-10-canary-hit-viewer/` | plan: the canary hit viewer in five slices (matching and the archive scan with the early output; the watcher; the participant page; the admin page; the upstream port), done (all five merged; upstream as `contrib/canary-hit-viewer`); rulings in its `README.md` and `progress.md`, handoffs in `handoffs/` | you change the hit viewer, or look for why it works as it does |
| `results/` | committed ladder results, counts only: `canary-ladder-<model>.md` (the matrix) and `<model>/L<n>.json` (one level's counts, its input) | you cite a ladder result or add a level |
<!-- Add one row per spec and plan as they merge, with where its Inputs for / handoffs are. -->
