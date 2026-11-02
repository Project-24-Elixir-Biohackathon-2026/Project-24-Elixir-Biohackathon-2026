# Backlog

Deferred items with no slice yet. One item each, about three lines at most: the item, where it came from (PR, review
thread, spec), and why it waits. An item that needs more points to its proposal in `docs/proposals/`. The PR
that fixes an item deletes its line. See
`.methodology/shared/guides/development-workflow.md`, *Deferred items land somewhere durable*.

## Next

Due soon, on any track: what someone said to do "in the next session", and what waits on the user. Every session
start reads this section; keep it short.

<!-- - <item> — from <investigation / review / handoff>; <waits on the user: what> | <due: why soon>. -->

- Bring `impl/agui-chat-sessions-2-sidebar` (#10) and `impl/canary-eval-ladder-1-scoring` (#3) onto the new
  `.methodology` pin (`172eae3`): each takes `main` at a clean point, by merge (pushed branches aren't rewritten
  here, *Overrides*), then `git submodule update --init .methodology` — from the methodology update of 2026-11-02;
  due: both still run the old scripts (`continue.sh`, no `next-session.sh --resume`).

## Unscheduled

<!-- - <item> — from <PR #n / review thread / spec Inputs for>, waits because <reason>. -->

- Wire the methodology's CI on the fork: copy `.methodology/template-ci/.github/workflows/` (`agent.yml`, `agent-review.yml` with the test command) and `.methodology/template/.github/workflows/pr-checks.yml` (with `exclude` for `platform/**/package-lock.json`, `**/uv.lock`, `platform/agui/pydantic-ai-agent/tests/fixtures/*`), install agent-action's Apps on the fork, add it to the runner's `repos`, create the `agent:` labels (`approved` and `waiting-on-user` exist), turn on auto-delete of head branches; then switch *Reviewers* from `local` to the `agent:` labels and revisit the merge gate in `AGENTS.md`, *Overrides* — from the methodology adoption (`change/adopt-methodology`), waits because `thodkatz/agent-action` is private and the fork has no access to it yet, and the user chose the local side first.
- Fork-only workflows must not run on upstream PRs: when the CI above lands, check that `.github/workflows/` added on the fork stays out of upstream branches (`AGENTS.md`, *Contributing upstream*: add `.github/workflows/agent*.yml` and `pr-checks.yml` to the fork-only list) — from the methodology adoption, waits on the item above.
- Spec for the typed GA4GH tool server (`spe_agent_tool_surface: ga4gh_typed`), the canary ladder's L4 — from `docs/superpowers/specs/2026-10-22-canary-eval-ladder-design/out-of-scope.md`, waits for that spec's plan; its requirements are the L4 row of part 01.
- Per-user and per-session LLM budgets that apply to every frontend we expose an agent through (Open WebUI, the AG-UI agent, the promptfoo provider), not just one of them: the LLM endpoint knows only a key, not users or sessions, and a per-agent cap such as the AG-UI agent's optional `total_tokens_limit` covers one frontend and resets every run. A likely shape is a gateway in the instance that every frontend's model calls go through (e.g. LiteLLM proxy: a virtual key per user or session, budgets and rate limits, frontends passing the user and the chat/thread id). Until it exists, a run's only caps are each frontend's own (AG-UI: requests and tool calls) and the provider account's spend limit. From PR #4 (the AG-UI token cap made optional so the two frontends are comparable) and `docs/specs/2026-10-15-agui-frontend-design.md`, *Limits* ("portal or per-user budgets remain deferred"). Waits because the evaluations so far run one participant per instance, so per-user limits change nothing yet.
- Chat sessions with owners in the AG-UI chat: the sessions of `docs/superpowers/specs/2026-10-29-agui-chat-sessions-design.md` belong to the instance, not a participant, and the session API has no authentication of its own (the SSH tunnel or Coder's owner-only proxy is the gate); several participants per instance would need identity in the chat UI and an owner per session. From that spec's *Out of scope* (review M5 on PR #7). Waits, like the per-user budgets above, for multi-participant instances.
- A run report in the CopilotKit chat, like Open WebUI's pinned "Run report" note (`reports/run_report.md.j2`): the AG-UI frontend has none, and its archive's `index.md` says so. From `AGENTS.md`, *AG-UI agent frontend* ("Not done yet") and the chat sessions spec's *Out of scope* (review M5 on PR #7). Waits because no one has asked for it on the AG-UI path yet; the chat sessions work comes first.
- AG-UI chat sessions: `lib/sessions.ts` `list()` reads and parses every session file in full before applying the 1000 cap; a cheap pass over `updated_at` (or an index) would bound it — from the PR #9 review (slice 1/3, AG-UI chat sessions), waits because an instance holds tens of sessions, not thousands.
- AG-UI chat sessions: `lib/sessions.ts` `write()` fsyncs the file but not the directory after the rename, so a power loss right after a save can lose the rename (the previous file survives, never a torn one) — from the PR #9 review (slice 1/3), waits because the last run of a session lost on a host crash is acceptable for evaluation instances.
- AG-UI chat sessions: `scripts/check-built-server.mjs` has no overall deadline, and its run fetches are unbounded, so a wedged server hangs the check instead of failing it — from the PR #9 review (slice 1/3), waits because the check is run by hand and a hang is visible; bound it when it runs unattended.
- AG-UI chat sessions: per run the recorder's `fetch` parses the whole request body to find the run id, and `runNextWithState` clones the history on every event (about 2 ms per event at a 3 MB history, measured) — from the PR #9 review (slice 1/3), waits because histories that size are rare and the cost is small against model latency.
- AG-UI chat sessions: the recorder keys its per-run abort controllers by the `runId` the client supplies, so two concurrent runs (on different sessions) with the same `runId` share one controller, and ending one aborts the other's agent request — from the PR #9 review (slice 1/3), waits because the CopilotKit client generates a fresh UUID per run; key by an id the recorder creates if clients ever reuse them.
