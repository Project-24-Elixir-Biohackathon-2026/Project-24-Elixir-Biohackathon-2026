# docs/ index

One line per document: what it covers and who reads it. Open the document only when your task needs it.

| Path | What | Read when |
|---|---|---|
| `../.methodology/shared/guides/` | the shared guides: workflow, sessions and context, spec and plan layout (a submodule; never edited here) | see `AGENTS.md`, *Read on demand* |
| `guides/` | this repo's own guides (fork-only, `AGENTS.md`, *Contributing upstream*) | see `AGENTS.md`, *Read on demand* |
| `guides/contributing-upstream.md` | guide: porting fork work to upstream, and merging upstream back | you open a PR on upstream or merge `upstream/main` |
| `handoffs/` | handoffs of this repo's sessions outside any plan, one file each (fork-only) | you start a session from one: read only the newest |
| `upstream-ports.md` | ledger: which fork commits went upstream (kraatz PR) or are not for upstream (fork-only) | you choose what to port upstream |
| `knowledge/README.md` | as-you-go gotchas, one line each | before non-trivial work in an area |
| `specs/`, `plans/` | upstream's design specs and plans (the AG-UI frontend), shared with upstream | when working on what they built |
| `superpowers/specs/`, `superpowers/plans/` | our fork's specs and plans (fork-only, `AGENTS.md`, *Contributing upstream*) | when your unit names one |
| `getting-started.md` | deploying and using an instance by hand (upstream's) | before deploying |
| `investigations/` | one file per answered question (`sessions-and-context.md`, *Investigations and audits*) | when the question comes up again |
| `proposals/` | one file per unscheduled idea too big for a `BACKLOG.md` line; its line there points to it (`development-workflow.md`, *Deferred items*) | when its backlog line or your area's brainstorming leads you to it |
| `superpowers/specs/2026-10-22-canary-eval-ladder-design/` | spec: the promptfoo canary evaluation ladder L0–L5 (approved) | you plan, build or run the evaluation pipeline |
| `superpowers/plans/2026-10-22-canary-eval-ladder/` | plan: the ladder in nine slices; shared interfaces in its `README.md`, handoffs in `handoffs/` | you implement a slice of the ladder |
| `superpowers/specs/2026-10-29-agui-chat-sessions-design.md` | spec: AG-UI chat sessions: sidebar, tags, server-side record, archive export (approved, #7) | you plan or build the CopilotKit chat's sessions or the agui archive |
| `superpowers/plans/2026-10-29-agui-chat-sessions/` | plan: AG-UI chat sessions in three slices, done (all three merged); shared interfaces in its `README.md`, handoffs in `handoffs/` | you change the CopilotKit chat's sessions or the agui archive, or look for why they work as they do |
| `superpowers/specs/2026-11-03-agui-compaction-design.md` | spec: AG-UI compaction: the agent summarises the history when it nears the model's window or overflows (approved, #15) | you plan or build compaction in the AG-UI agent, chat or archive |
<!-- Add one row per spec and plan as they merge, with where its Inputs for / handoffs are. -->
