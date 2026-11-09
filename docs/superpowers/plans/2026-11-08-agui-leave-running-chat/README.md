# AG-UI: leave a running chat — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` (`AGENTS.md`,
> *Working Conventions*) to implement one slice per session and PR. Steps use checkbox (`- [ ]`) syntax.

**Goal:** a participant can switch session or start a New chat while a run is in progress: the run goes on in its
session's own CopilotKit agent, going back shows it still streaming, a session running elsewhere (a reload,
another tab) is rejoined live, and the sidebar marks every running session.

**Spec:** the living AG-UI spec [`docs/specs/2026-10-15-agui-frontend-design/`](../../../specs/2026-10-15-agui-frontend-design/README.md):
§6 ([`06-chat-ui.md`](../../../specs/2026-10-15-agui-frontend-design/06-chat-ui.md): *Session API*, *Layout*,
*A session's agent*, *Opening a session*, *Leaving a running chat*, *Refresh*, *Errors*), decisions 26 and 40–44
in its README, *Early output* (leaving a running chat), clarification 27, and
[`inputs-for-plan.md`](../../../specs/2026-10-15-agui-frontend-design/inputs-for-plan.md), *Leaving a running
chat*. Latest clarification when this plan was written: 27. Each slice file names the decisions it implements.

**Architecture.** The server already detaches a run from the browser's request and journals it to its end
(decision 24), and `Shared.running` (`lib/sessions.ts`) holds every run in progress. So:

- **Server** (slice 1): `toMeta` answers `running` from `Shared.running`, a lookup by session id (`isRunning`).
- **Page** (slice 2): one owner of the page's *live* sessions (`lib/live-sessions.ts`: the open one, and each one
  with a run this page streams). For each live session the page mounts a holder component
  (`app/session-agent.tsx`) with a private thread-scoped agent (`useAgent({ agentId: "spe-<id>", runtimeAgentId:
  "spe", threadId: <id> })`); the holder owns that agent's end-of-run reconcile, title trigger and error
  subscription. `CopilotChat` is on the open session's agent, keyed by its id, never explicit. The sidebar's
  mark, the Delete rule and (slice 3) the polling read one set of running ids.
- **Rejoin** (slice 3): a session answered `running` that no holder streams is rejoined by its holder calling
  `copilotkit.connectAgent({ agent })`, with replayed messages matched by id against the journal's history
  (`lib/rejoin.ts`), or, if slice 1's check says so, decision 42's fallback.

**Tech stack:** Next.js 16.4.5, React 19.3.1, CopilotKit 1.84.1 (`@copilotkit/react-core/v2`,
`@copilotkit/runtime/v2`), `@ag-ui/client` 1.0.2, Node `node --test` (chat); Python Playwright
(`platform/dev/e2e/`) against `platform/dev/fake_agent.py`.

## Rulings

Each is *decision, why, cost if wrong*; a slice that departs from this plan adds one to [`progress.md`](progress.md)
and rewrites the task text it changes.

1. **CopilotKit 1.84.1, not 1.79, is the version built on.** The spec names 1.79's thread-scoped `useAgent`;
   `package.json` pins 1.84.1, whose `UseAgentThreadScopedProps` (`agentId`, `runtimeAgentId`, `threadId`, all
   required) and `CopilotKitCore.connectAgent({ agent })` were read in its type declarations for this plan
   (2026-11-08). *Cost if wrong:* none expected; slice 1's check runs on 1.84.1 either way.
2. **The rejoin check's page and script are throwaway**: built and run in slice 1, the page removed before the PR
   merges; the script, its output and the verdict stay under `evidence/slice-1/` and in `progress.md`. *Cost if
   wrong:* re-running the check after a CopilotKit upgrade means restoring the page from
   `658ba7b:platform/agui/copilotkit-chat/app/rejoin-check/page.tsx` (the squash merge keeps only the PR's ref).
3. **`running` is part of `SessionMeta`**, so the list, `GET` one, `PATCH` and `POST …/title` all answer it (§6:
   "the metadata … `running` included"); `SessionView` keeps it. *Cost if wrong:* none: one boolean per item.
4. **A session gone from the list is "gone" only if this page saw it listed before** (`LiveSessions.listed`): a
   New chat whose first run has not reached the list yet is never dropped for its absence. *Cost if wrong:* a
   session deleted before it was ever listed keeps its holder to its run's end, which is §6's rule anyway.
5. **The verdict lives in `progress.md`, one entry per verdict**, not in a handoff, so slices 2 and 3 read it
   without reading slice 1's handoffs. *Cost if wrong:* none.

## Global Constraints

Every task's requirements include these.

- **Tests, before every commit**, in `platform/agui/copilotkit-chat`: `npm ci && npm test && npm run build`;
  Playwright: `python3 platform/dev/e2e/sessions.py` (the scenarios a task names, then `--scenario all` before
  the PR) after `npm run build`.
- **No new dependencies**, no CopilotKit upgrade. Sidebar UI stays plain React and CSS (§6 *The sidebar*).
- **Names fixed by the spec:** the private agent's id `spe-<session id>`, routed to runtime agent `spe`, thread
  the session id; the list key `running`; the screen-reader text "Running"; the error text `“<title>”: <message>`
  ("New chat" for no title); the polling interval 2 s; the reconcile retries 5 at 500 ms; the fallback's message
  "this session could not be saved".
- **`CopilotChat` is never explicit** (`hasExplicitThreadId={false}`), remounted per session (`key={id}`); a
  rejoin calls `connectAgent` from the holder, never through `CopilotChat` (§6 *A session's agent*).
- **No model calls.** Every check uses `lib/test-agent.ts` or `platform/dev/fake_agent.py`; no paid run in this
  plan.
- **The stop point is a gate** (spec *inputs-for-plan*): if slice 1's check finds that a private agent loses or
  repeats messages on an ordinary open (no run, no `connect`), the track stops there: one comment on slice 1's
  PR, `waiting-on-user`, and `methodology gate wait` (`development-workflow.md`, *Gates*). Nothing else in this
  plan is a gate; the early-output screenshot (slice 2) asks with no gate.
- **Upstream-clean:** code, the chat's README and `platform/` comments name nothing fork-only; this feature goes
  upstream as AG-UI work does (`docs/guides/contributing-upstream.md`).
- **Rulings:** a departure from this plan is recorded in `progress.md` as *decision, why, cost if wrong*, and the
  same commit rewrites the plan task text (and, through a clarification, the spec text) it changes.

## File structure

`CHAT` is `platform/agui/copilotkit-chat`.

| Path | Slice | What |
|---|---|---|
| `CHAT/lib/sessions.ts`, `lib/recorder.ts`, `lib/api.test.ts`, `lib/recorder.test.ts`, `lib/sessions.test.ts` | 1 | `running` (43): `runKey` and `isRunning` move into `sessions.ts` |
| `CHAT/app/rejoin-check/page.tsx` (removed before merge), `evidence/slice-1/` | 1 | the rejoin check (42), its script and output |
| `progress.md`; spec `clarifications.md`, `06-chat-ui.md`, README decision 42 | 1 | the verdict; clarification 28 if it changes the spec |
| `CHAT/lib/live-sessions.ts`, `lib/live-sessions.test.ts` | 2 | the owner of the page's live sessions (40) |
| `CHAT/app/session-agent.tsx`, `app/page.tsx`, `app/use-run-reconcile.ts` | 2 | one holder and agent per live session; switching enabled (26, 40, 41) |
| `CHAT/app/sidebar.tsx`, `app/chat-header.tsx`, `app/row-menu.tsx`, `app/icons.tsx`, `app/globals.css`, `lib/sidebar-view.ts` | 2 | the running mark, Delete disabled per running session (44) |
| `platform/dev/e2e/sessions.py`, `evidence/slice-2/` | 2, 3 | Playwright for 26, 40–44; the early-output screenshot |
| `CHAT/lib/reconcile.ts`, `lib/refresh.ts`, `lib/rejoin.ts` and their tests | 3 | refresh and polling (44), rejoin (42) |
| `platform/dev/fake_agent.py` | 3 | `slow-fail`: a slow run that then fails (44's error check) |
| `CHAT/README.md`, `docs/getting-started.md`, spec `README.md` (status), `12-implementation-findings.md` | 2, 3 | docs follow each behaviour change; the spec marked built |

## PR slices

N = 3, sequential: each starts from `main` after the previous merged. The session merges each PR itself once the
checks in `AGENTS.md`, *Overrides*, pass. Each slice's PR also sets its row's status (`merged #<n>`, written in
its after-merge state), adds its handoff to [`handoffs/`](handoffs/) and moves `AGENTS.md`'s *Current work* line
to the next slice; slice 3 closes the track (its task 4).

| n/N | Branch | Tasks | Delivers | Est. LOC | Reviewer checks | File | Status |
|---|---|---|---|---|---|---|---|
| 1/3 | `impl/agui-leave-running-chat-1-rejoin-check` | 3 | `running` in the API (43); the **rejoin check** (42, early output, first part) and its verdict; the stop point | ~250 kept (+~200 throwaway) | `npm test`; the check's output in `evidence/slice-1/`; the verdict in `progress.md` | [slice-1-rejoin-check.md](slice-1-rejoin-check.md) | merged #57 |
| 2/3 | `impl/agui-leave-running-chat-2-agents` | 4 | an agent per session; switching and New chat enabled (26, 40, 41); the running mark and the Delete rule (44, part); the **screenshot** (early output, second part) | ~750 | `npm test`; `npm run build`; e2e `--scenario leave-running`, `stop`, `all`; the screenshot | [slice-2-agents.md](slice-2-agents.md) | planned |
| 3/3 | `impl/agui-leave-running-chat-3-rejoin` | 4 | rejoin through `connect`, or the fallback, as slice 1 ruled (42); refresh on focus and polling (44); run errors with their title (44); docs; spec built | ~650 | `npm test`; `npm run build`; e2e `--scenario rejoin`, `running-marks`, `all` | [slice-3-rejoin.md](slice-3-rejoin.md) | planned |

**What the user sees, and when.** Slice 1 posts the rejoin check's verdict on its PR (the message ids the chat
showed against the journal's) and merges; only the stop point waits for the user. Slice 2 posts the screenshot of
two sessions marked running with the left one still streaming, and asks one question with no gate: does a reply
that finished while away need a mark of its own? A "yes" is a new task in slice 3 (spec *inputs-for-plan*), added
with a clarification.

## Review Focus

Inputs the spec implies that no acceptance check exercises; each line's test is in the named task.

1. **Switching back and forth faster than a `GET` answers** (A → B → A during a run, B not held): a late `GET` for
   B never replaces what A's agent shows, and A opens with no fetch. Slice 2, task 2
   (`check_leave_running`: the quick toggle step).
2. **A New chat started while another New chat, not yet listed, runs**: the first's holder stays although the
   list lacks it (ruling 4). Slice 2, task 1 (`a streaming session never listed is not dropped by a list
   without it`).
3. **A holder dropped and the same session opened again**: `spe-<id>` registers again without "already
   registered", and the session opens from the journal. Slice 1, task 2 (check B), and slice 2, task 2
   (`check_leave_running`: reopen after the run ended).
4. **Two sessions running when the page reloads**: both marked, the list polled while either runs unstreamed;
   opening one rejoins it and the other is still polled. Slice 3, task 1 (`polls while a running session is
   not streamed, stops when every running one is`).
5. **A run error in a left session whose row was deleted or never titled**: the bar says `“New chat”: …`, never
   `“undefined”`. Slice 3, task 3 (`runErrorText: a session without a title is New chat`).

## Proposed spec clarifications

Each is added by the slice that verifies it, with the next free number and status `folded`, and the spec text
updated in the same commit.

- **Slice 1, task 3: decision 42's verdict**, only if it changes the spec: the fallback chosen, or a rejoin
  mechanism other than §6's (replayed messages matched by id).
- **Slice 3, task 4: leaving a running chat is built**: the spec README's status line and §12's findings, and
  ruling 1: §6's "1.79" thread-scoped `useAgent` reads 1.84.1, the version built on.

## Progress and handoffs

[`progress.md`](progress.md): verdicts and rulings made while building. [`handoffs/`](handoffs/): read only the
newest (`methodology handoff newest docs/superpowers/plans/2026-11-08-agui-leave-running-chat/handoffs`).
