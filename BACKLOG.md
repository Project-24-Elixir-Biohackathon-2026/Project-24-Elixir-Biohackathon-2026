# Backlog

Deferred items with no slice yet. One item each, about three lines at most: the item, where it came from (PR, review
thread, spec), and why it waits. An item that needs more points to its proposal in `docs/proposals/`. The PR
that fixes an item deletes its line. See
`.methodology/shared/guides/development-workflow.md`, *Deferred items land somewhere durable*.

## Next

Due soon, on any track: what someone said to do "in the next session", and what waits on the user. Every session
start reads this section; keep it short.

<!-- - <item> — from <investigation / review / handoff>; <waits on the user: what> | <due: why soon>. -->

- AG-UI chat: does a reply that finished while away need a mark of its own, and should the open row show its running
  spinner? Two no-gate questions on #58's early output (issuecomment-6730913819), nothing built — waits on the user:
  an answer; a *yes* is a change with a spec §6 clarification.
- Turn on GitHub's *Automatically delete head branches* (`deleteBranchOnMerge`, now `false`) on this fork: the
  start routine's prune removes only worktrees whose remote branch is gone, so a merging session that skips
  cleanup leaves its worktree for good (#58's, 2026-11-09; agent-methodology #153) — waits on the user: an OK to
  change the repo setting.
- Canary ladder upstream: once slice 5 merges, port slices 1–5 to kraatz as one `contrib/` branch (scoring,
  isolation, controls, injections, agent suite), then one port per hardening level as slices 6–9 merge. Before it:
  a short `docs/specs/` version of the spec (the design lives fork-only in `docs/superpowers/specs/`), and the
  L1–L3 switches checked off by default (the portal follows upstream `main`) — from the user, 2026-11-09; due: at
  slice 5's merge.

## Unscheduled

<!-- - <item> — from <PR #n / review thread / spec Inputs for>, waits because <reason>. -->

- AG-UI chat, minor polish from #58's review (finding 5): opening a session no holder keeps shows *Loading…* for
  one render; no unit test drives `SessionAgent` with the page (only e2e `leave-running` does); while a chat
  reopened mid-run streams, the whole chat re-renders per message change (`page.tsx`, `midRun`); a ms race between
  AG-UI's subscriber copy and the page's streaming state could still freeze one such chat — waits because none
  was seen to fail, and `leave-running` step 3 catches a freeze.
- AG-UI chat: a switch away between a rejoin's start and its connect's `onRunInitialized` drops the holder while the
  connect goes on, and its end reaches no page state (`platform/agui/copilotkit-chat/app/session-agent.tsx`, the rejoin effect) —
  from #62's task 2 review (Minor 4); waits because the window is short and the poll still clears the mark.
- AG-UI chat: between a list showing a session `running` and its connect's `onRunInitialized`, the open chat's
  composer is offered, though §6 says never; a send there is refused by the runtime, and while `rejoining` is set its
  run would end through `waitNotRunning` (`platform/agui/copilotkit-chat/lib/run-watch.ts`) — from #62's review
  (finding 4); waits because the window is short and the send is refused, not lost.
- e2e `--scenario all` failed once in seven local runs on #58's branch (2026-11-09; the traceback was not kept, the
  other six passed 47 ok) — from #58's checks; waits for a second sighting: keep the log (`> file 2>&1`) and note
  the failing step here.
- Canary ladder: `spe_local_vars` lacks the `spe_harden_*` switches (and `spe_agent_tool_surface`), so `spe-apply
  stack|all` on the VM rebuilds L0 controls under a hardened `hardening.json` — from slice 4's pre-flight (F6);
  waits for slice 6, which closes it when L1 first needs re-apply to rebuild the same level.
- Canary ladder: clean runs above L1. The run script and matrix accept a clean run at any level;
  L2–L5 run injected only — from `biohackathon` knowledge 0015 and spec clarification 7 (#59); waits on the L0/L1
  clean and injected results (slices 5 and 6), which show whether a level's clean comparison is worth its runs.
- Canary ladder: one-fixture-at-a-time injection runs (0015, *Review finding*): one `spe_inject_*` on per build,
  only that fixture's injection test (needs `hardening.json` `injections` as the planted ids: the ladder plan's
  *Rulings*) — from spec clarification 7 (#59), deferred by the user (2026-11-09) because
  slice 1's `injection.followed` already attributes by the exposed payload's fingerprint and target; schedule if
  L0/L1 results show runs where two payloads were exposed and asked for the same action.

- Carry `docs/knowledge/subagent-stall-after-usage-limit.md` to agent-methodology's `tooling-gotchas.md`, then drop the
  local note at the next `methodology update` — from #57's methodology review (finding 7); waits because it is a
  change to another repository, its own unit.

- agent-methodology: `forge.sh` calls `gh pr view <n>` (and `gh api repos/{owner}/{repo}/…`) without `--repo`; on
  this fork, whose parent is now in an organization, that fails (`methodology gate approve`: "could not read #N's
  labels") even with `gh repo set-default` (`docs/knowledge/gh-pr-create-token.md`). Carry a fix (pass the origin's
  repo explicitly) — from #55; waits because it is another repository's change.
- AG-UI e2e: `platform/dev/e2e` checks tool grouping for two calls in one response only; add a fake-agent case with
  calls across two model steps (no text between them) that must form one group, its header saying "Exploring"
  while the run lasts, so a CopilotKit upgrade that
  changes the rule fails a free check (spec clarification 25) — from #50's review; waits because only the paid
  all-features check covers it today.
- The AG-UI `ui-dev` profile (`spe_agui_ui_dev: true`, `chat-ui-dev`, upstream's hot-reload chat) has no archive:
  `run_archive`'s export copies and stops `chat-ui` and runs the exporter from its image, so it refuses `ui-dev`,
  and `destroy.yml` there needs `-e spe_archive_skip=true` (the chats are lost); `checks.yml` skips the
  hardening check there and scans `chat-ui-dev`'s sessions. From the 2026-11-04 upstream merge (#35); waits because
  no workspace runs `ui-dev` for a recorded run yet.
- AG-UI chat: branching, editing or regenerating messages in the chat, plus export from the UI, full-text search over messages and folders (Open WebUI features not asked for) — from the living AG-UI spec's `docs/specs/2026-10-15-agui-frontend-design/out-of-scope.md` (PR #19); waits until someone asks for them.
- AG-UI `/compact`: other slash commands, a compact button, an escape for sending the literal text `/compact …` to the model, and manual compaction while automatic compaction is off — from the living AG-UI spec's `docs/specs/2026-10-15-agui-frontend-design/out-of-scope.md` (PR #26); waits until someone asks for them.
- AG-UI `/compact`: the agent backstops no focus length: a client that reaches the agent directly can send a focus of any size, which shrinks the transcript to its pinned entries without an error (`chat-ui` refuses more than 1000 characters, §15 *The run route*); a `RUN_ERROR` as for "Nothing to compact yet." would match — from PR #28's local review (correctness, finding 3), waits because only `chat-ui` reaches the agent and the spec names no agent-side limit.
- AG-UI record: `chat-ui` forwards the client's `tools`, which the model sees (TM-005, scenario 5); the chat UI
  defines none, so `lib/recorder.ts` can drop them, with a recorder test and a §13 clarification (decision 5, and
  *Boundary*, which does not name client tools yet) — from PR #43; was waiting on kraatz #17, which carried §13 and has merged.
- AG-UI record: the protocol's server-managed history (draft ag-ui#3135), the client sending only unconfirmed
  messages, would retire most of `lib/anchor.ts`; #3135 says CopilotRuntime clones agents per request and falls
  back to full history, so `chat-ui`'s path may need more than the release — from PR #43; waits on the protocol.
- AG-UI record: recording runs sent straight to the agent (not through `chat-ui`) beyond its run log — from `docs/specs/2026-10-15-agui-frontend-design/out-of-scope.md` (PR #19); waits until a frontend other than `chat-ui` reaches the agent.
- AG-UI record: a promptfoo target that runs through `chat-ui`, the mitigated variant of §13 *Approach*'s experiment — from `docs/specs/2026-10-15-agui-frontend-design/out-of-scope.md` (PR #19); waits for the record's slices.
- Open WebUI: recording edits made in Open WebUI (its event webhook or audit log), so its history is as trustworthy as the AG-UI record's — from `docs/specs/2026-10-15-agui-frontend-design/out-of-scope.md` (PR #19); waits until the record is built.
- Wire the methodology's CI on the fork: copy `.methodology/template-ci/.github/workflows/` (`agent.yml`, `agent-review.yml` with the test command) and `.methodology/template/.github/workflows/pr-checks.yml` (with `exclude` for `platform/**/package-lock.json`, `**/uv.lock`, `platform/agui/pydantic-ai-agent/tests/fixtures/*`), install agent-action's Apps on the fork, add it to the runner's `repos`, create the `agent:` labels (`approved` and `waiting-on-user` exist), turn on auto-delete of head branches; then switch *Reviewers* from `local` to the `agent:` labels — from the methodology adoption (`change/adopt-methodology`), waits because `thodkatz/agent-action` is private and the fork has no access to it yet, and the user chose the local side first.
- Fork-only workflows must not run on upstream PRs: when the CI above lands, check that `.github/workflows/` added on the fork stays out of upstream branches (`AGENTS.md`, *Contributing upstream*, and the exclude list in `docs/guides/contributing-upstream.md`, step 1: add `.github/workflows/agent*.yml` and `pr-checks.yml` to the fork-only list) — from the methodology adoption, waits on the item above.
- Spec for the typed GA4GH tool server (`spe_agent_tool_surface: typed`), the canary ladder's L4 — from `docs/superpowers/specs/2026-10-22-canary-eval-ladder-design/out-of-scope.md`, waits for that spec's plan; its requirements are the L4 row of part 01.
- Per-user and per-session LLM budgets that apply to every frontend we expose an agent through (Open WebUI, the AG-UI agent, the promptfoo provider), not just one of them: the LLM endpoint knows only a key, not users or sessions, and a per-agent cap such as the AG-UI agent's optional `total_tokens_limit` covers one frontend and resets every run. A likely shape is a gateway in the instance that every frontend's model calls go through (e.g. LiteLLM proxy: a virtual key per user or session, budgets and rate limits, frontends passing the user and the chat/thread id). Until it exists, a run's only caps are each frontend's own (AG-UI: requests and tool calls) and the provider account's spend limit. From PR #4 (the AG-UI token cap made optional so the two frontends are comparable) and `docs/specs/2026-10-15-agui-frontend-design/05-agent-service.md`, *Limits* ("portal or per-user budgets remain deferred"). Waits because the evaluations so far run one participant per instance, so per-user limits change nothing yet.
- Chat sessions with owners in the AG-UI chat: the sessions of the living AG-UI spec (`docs/specs/2026-10-15-agui-frontend-design/`, §6) belong to the instance, not a participant, and the session API has no authentication of its own (the SSH tunnel or Coder's owner-only proxy is the gate); several participants per instance would need identity in the chat UI and an owner per session. From its *Out of scope* (first the chat sessions spec's, review M5 on PR #7). Waits, like the per-user budgets above, for multi-participant instances.
- AG-UI notes like Open WebUI's (standalone Markdown notes per instance, pinnable, archived under `notes/`): brainstormed and dropped (user, 2026-11-08): upstream's portal run report (`platform/report/`, one per workspace, every frontend) covers the write-up notes were for, and it deliberately keeps what participants write off the instance under test. If built later: owned by the instance, Markdown canonical, no sharing, no AI enhance, EasyMDE as on the Report page. Waits until participants ask for scratch notes beyond the report.
- AG-UI compaction: drop or shorten old tool results before summarising (Anthropic's context editing), as a cheaper first stage — from the compaction spec (#15), *Out of scope*, waits because nothing shows summary requests are costly yet (the run log's `compactions` will).
- AG-UI compaction on qwen: one summary request returned the answer instead of a summary ("The last line `seq 1 3000` printed is: **3000**"), and after each compaction qwen re-read the tool output the summary had dropped, so a 20000 window compacted three times in one run and hit the cap; review `compaction_prompt.md` against qwen (e.g. promptfoo over archived transcripts) — from slice 3/3, task 3 (`docs/superpowers/plans/2026-11-03-agui-compaction/evidence/slice-3/denbi/README.md`), waits because at a realistic window the session passed.
- AG-UI compaction estimate: `CHARS_PER_TOKEN` = 3 under-counts digit-heavy output on qwen, whose tokenizer splits numbers into single digits (237599 estimated against 316927 counted by de.NBI's gateway for `seq 1 87382`), so the proactive trigger fires later than 80 % of the window there; the reactive path recovered the session — from slice 3/3, task 4 (`docs/superpowers/plans/2026-11-03-agui-compaction/evidence/slice-3/decision-13/README.md`), waits because no session failed from it.
- Canary ladder: AG-UI runs may be compacted, so the context a canary or an injected instruction sits in can change mid-run; scoring and analysis read the run log's `compactions` — from the compaction spec (#15), *Run log*, waits because the ladder's slices have not reached AG-UI scoring.
- AG-UI compaction: fold its spec into the living AG-UI spec (`docs/specs/2026-10-15-agui-frontend-design/`) as its own part, the fork spec's status then *folded* — from the user's choice of one living spec (2026-11-03, PR #19); can start: the compaction track ended with slice 3/3 (2026-11-03), so no open slice cites the fork spec any more.
- Participants very likely have root on their SPE VM: the Coder template gives every workspace `web_terminal`, `ssh_helper` and `port_forwarding_helper` (`platform/coder/template/main.tf`), the Coder agent runs as `ubuntu` (`roles/coder_agent`), and nothing in `roles/base` removes the cloud image's passwordless sudo. Then a participant can read the agent key (`agent.env`), reach port 8100 through port forwarding, `docker exec` into any container and edit any chat record on disk, Open WebUI's included, so no record kept on the VM is tamper-proof against them. Check first in a workspace terminal: `sudo -n true && echo root`. Options: no terminal, SSH or port forwarding in the participant presets; a terminal user without sudo or the `docker` group; or records shipped off the VM as they are written. Changes the Coder template, so it reaches upstream and the portal. From the AG-UI conversation record design discussion (2026-11-03), which states this as outside its boundary; waits on the check and the user's choice.
- AG-UI chat sessions: per run the recorder's `fetch` parses the whole request body to find the run id, and admission (`admit()`) reads and rebuilds the whole journal per run — from the PR #9 review (slice 1/3), waits because histories that size are rare and the cost is small against model latency.
- AG-UI chat sessions: a stop clicked between Enter and the browser's own POST reaching the Next.js route handler would abort before the recorder's `run()` ever starts, writing nothing (not even `cancelled`), so the open session's reconciliation would show "this session could not be saved" after its retries — from the slice 3/3 header task's review (fix round 1, item 3). Not reproduced in 10 attempts (the POST always reached the server well before any second Playwright click, every one recorded `cancelled`); waits because the window is too small to drive from outside the browser.
- AG-UI record: the rebuild's cost grows with the square of a session's length: `lib/rebuild.ts` `structuredClone`s the anchor's path for each run before applying its events, so a session of n runs copies O(n²) messages on every load — from PR #22's local review (deferred minor of task 3), waits because evaluation sessions are short; revisit if slice 3's index pass over the journals at startup is slow.
- AG-UI record: the exporter's `owner` map is keyed by the original AG-UI id, so two literal duplicate ids in one run's `new_messages` would overwrite each other's owner entry; it also takes a run's user messages from `run.new_messages` while rebuild uses `run.added`, and filtering on `added` would cover both — from #23's review, waits because `classify`'s `seen` keeps journal ids unique, so no server-written journal reaches either path.
- AG-UI record: the exporter script's missing-directory test (`test_write_run_agui.py`) checks only the exit code 1, not the error message on stderr — from #23's review, waits because it is a test-strength gap, not a behaviour bug.
- AG-UI record: a model that numbers tool-call ids per response (reusing an id across runs, e.g. `call_0`) would make the live browser view differ from a reopened (rebuilt) session, because `@ag-ui/client` merges a recurring tool-call id into the earlier call; `platform/dev/fake_agent.py` was changed to make its ids unique per call for this reason — from slice 3's task 5 (ruling D1), waits on slice 4's Playwright checks and a check against the de.NBI model's own ids.
- AG-UI record: each session's `JournalWriter` (`lib/sessions.ts`) stays open for the chat UI process's life, one fd per session ever appended to, never closed even at shutdown — from slice 3's final review, waits because fd growth only bites a long-lived instance with many sessions; options are closing idle writers past a cap or an age, or `shutdown()` closing them after the drain.
- AG-UI record: a journal the index build could not read (a transient EMFILE or EIO) stays out of the index until a restart: `list()` leaves it out and `GET` answers 404 while runs are still admitted, and after the next run the entry is folded from the new lines only (wrong `created_at` and auto title, earlier `meta` lines missing) — `lib/sessions.ts`, `build()`; fix: fold the whole journal when `append` finds no entry, or retry skipped files on `ready()` — from #24's review (finding 3), waits because it needs a read failure at startup and a restart repairs it.
- AG-UI record: a journal that cannot be read (`isDeleted` or `load` throwing in `admit`, `lib/recorder.ts`) refuses the run with "this session could not be saved", which tells the user and operator that saving failed when reading did; a distinct "this session could not be read" is a spec change: §13 step 1, `REFUSAL_MESSAGES` and `reconcile.ts`'s refused-run list, as the spec fixes six refusal messages — from #24's review (finding 4), waits because the run is refused either way and the log line says `reading … failed`.
- AG-UI record: the chat route refuses a second in-flight run on one session ("Thread already running": CopilotRuntime's default `InMemoryAgentRunner`, `onConcurrentRun: "throw"`, no `runner` override in `app/api/copilotkit/[[...slug]]/route.ts`), so decision 9's overlap holds in `lib/recorder.ts` (`npm test`) but not through the route — from the conversation record's slice 4, task 2 (Playwright checks); waits because it fails safe (the second run errors, nothing is recorded wrong) and the user ruled two tabs sending on one session at once acceptable as refused (2026-11-03) and fixing it needs a `runner` override or a different `AgentRunner`, outside the slice.
- AG-UI archive: a final archive re-run after its barrier failed (e.g. `chat-ui` exited 1, a drain timeout) finds the services already stopped, so `export.yml`'s exit-code check has nothing to check and the bundle and `index.md` say `final` ("copied after the chat UI and the agent had stopped") although the last run's end may be missing from its journal; the failure message says so, the archive does not — from PR #25's local review (correctness, finding 4); waits because the run then shows as incomplete in the archive rather than wrong, and marking it needs a new bundle field through the exporter and `write_run.py`.
- Canary ladder: the test receiver's log `/var/lib/spe-eval-sink/` lies outside the instance's owned paths, so
  `destroy.yml` leaves it on an existing host (only a build with `spe_eval_sink` off removes it) — from slice 4's
  pre-flight (F2); waits because the reset refuses any path outside the owned ones, and the evaluation reads the
  log by length, so an old log is harmless.
