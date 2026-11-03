# Clarifications

The decision log: numbered, append-only, never renumbered. History, not design: each entry's change is already
in the parts it amends.

1. **The spec becomes the living AG-UI spec: §6 holds the chat sessions, §13 and §14 the conversation record**
   (2026-11-03; the fork's PR #19). The single file is split into this directory, one part per section; §6 states
   the sessions, session API and sidebar as built, restated for the record (their journal parts wait for it); §13
   (the record) and §14 (the archive) are added, with the README's decisions table, early output and glossary; §2,
   §3, §5 *History*, §9 and §10 are rewritten where they said the chat keeps no conversation, the client's history
   reaches the agent unchanged, or the chat UI has no tests. *Reason:* the chat sessions and the record were
   designed in separate specs; one spec, kept current, lets the AG-UI work be read, reviewed and ported as one
   package. Chat sessions stored the client's history, which a participant can forge; the record replaces that
   storage (decisions 1–18) and carries the rest of the sessions' design over (decisions 19–30). *Amends:* §2, §3,
   §5 *History*, §6, §9, §10; adds §13, §14. *Status:* folded.

2. **The archive copies live; only the final archive stops the services** (2026-11-03, the user, after #19
   merged). `archive.yml` no longer stops `chat-ui` and the agent: it copies the journals and the run log from
   the running containers, so it can run at any time as a backup without interrupting participants. The stop
   (the barrier) stays only in the archive `destroy.yml` runs (`spe_archive_final: true`), and the services are
   not started again there. The bundle records `live` or `final`. *Reason:* the user wants to archive and back
   up without stopping users; a stop per archive cancels every run in progress. The append-only journal (§13)
   makes a live copy safe: it is an earlier state of each file with at most a torn last line, which the
   rebuild already skips, and a run without `run_end` reads as `incomplete`. *Cost if wrong:* a live archive
   can miss the last second of a run and show runs as `incomplete` that complete later; the final archive
   still has them whole. *Amends:* §14 *Export* and *Write*, decision 30. *Status:* folded.

3. **The archive renders the agent's compaction marker as a section, and `index.md` counts them** (2026-11-03;
   AG-UI compaction, slice 2/3, the fork's PR #18). An assistant text message whose id starts with
   `spe-compaction-` is rendered as `## Compacted`, the line "From here the model saw this summary instead of the
   messages above." and the summary in a fence; `index.md`'s columns become `# | Session | Tags | Created | Runs |
   Compactions | State`. *Reason:* the agent compacts a conversation that no longer fits the model's context and
   marks the point in the session's messages (`docs/superpowers/specs/2026-11-03-agui-compaction-design.md`, §7,
   clarification 1). It was written as the chat sessions spec's clarification 8 on that branch, which #19's fold
   took first. *Amends:* §14, the archive as built (`index.md` columns). *Status:* folded.

4. **The feasibility sample comes from the built server once the journal is wired; the first slice shows the
   verdict at the runtime level** (2026-11-03; the fork's PR #20, the conversation record's plan). *Early output*'s
   first sample (the built server, a `curl` with a fabricated turn and a forged marker, `fake_agent.py`'s echo, the
   journal lines) is shown when the journal is wired into the run route, not in the first slice; the first slice
   shows the verdict through CopilotKit's runtime handler and a real `HttpAgent`, a middleware that replaces the
   history deciding what the agent receives, and stops the work for the user's decision if it does not. *Reason:*
   the journal lines and `fake_agent.py`'s echo of what it received exist only once the journal and the run route
   are built; the runtime-level test answers the same question (can `chat-ui` replace the history?) before any of
   that is built, which is what the early sample is for. *Cost if wrong:* the user sees the sample with journal
   lines one slice later than the spec said; a negative verdict still stops the work in the first slice.
   *Amends:* README, *Early output*. *Status:* folded.

5. **`spe_agui_source_dir` is `platform/agui`, not the repository root** (2026-11-03; the fork's PR #18 rewrote
   §7, PR #20 records it). §7's default is `{{ playbook_dir }}/../../agui`, the directory holding
   `pydantic-ai-agent/` and `copilotkit-chat/`; a deploy from another checkout passes
   `-e spe_agui_source_dir=<checkout>/platform/agui`. *Reason:* the platform moved under `platform/`, and the
   `agui` role stages `pydantic-ai-agent` and `copilotkit-chat` relative to this directory, so the repository
   root made `create.yml` fail. *Amends:* §7, the `agui` role's variables. *Status:* folded.

6. **Classification reads decision 2 literally where §13 left it open: a known, unchanged message off the
   anchor's path is not recorded** (2026-11-03; conversation record, slice 1/4). §13 *The run route*, step 2 now
   states: the anchor is the client message the journal added last, not the last in the client's order; a run's
   last message is not a run boundary while a tool call that run made has no result in that run; the messages
   cut when the anchor moves back are `deleted` even if the client sent them; a message without a string id is
   `fabricated`, and a repeated new id counts once; `ignored` lists the client's messages first, then `deleted`
   in path order; a known message whose compared fields equal the journal's is not recorded, even off the
   anchor's path (a message resent from another branch). *Reason:* the record keeps what reached the agent and
   what the client sent that differs; an unchanged known message differs in nothing, the journal already holds
   it verbatim, and `run_start.anchor` shows which branch the run continued; a reordered history must not raise
   false alarms. *Cost if wrong:* an analyst cannot see in the journal that a client resent an unchanged message
   from another branch; recording it later is one more `ignored` kind and its rendering in `write_run.py`,
   absent from journals written before. *Amends:* §13 *The run route*, step 2; decision 2. *Status:* folded.

7. **A run without `run_end` is no boundary at its last message, nothing after a run's first `run_end` is applied,
   and new messages count from the anchor's position as the client sent it** (2026-11-03; conversation record,
   slice 1/4's review round, the fork's PR #22). §13 *The run route*, step 2 states the first and third,
   *Rebuilding the conversation* the second. *Reason:* while a run streams, its newest message holds no tool call
   yet, so a second run (§13, *Concurrency and branches*) could anchor at that partial reply; the first run then
   attaches a tool call to it with the result on its own branch, and a later run on the second branch sends the
   agent a dangling call. Lines after a run's first `run_end`, which only a damaged or hand-edited journal holds,
   could do the same to an ended run another run is anchored at. The cutoff for new messages was left open by
   clarification 6; the code counts from the anchor's place in the client's history before it moves back, the
   stricter reading (fewer messages count as new, the rest `fabricated`). *Cost if wrong:* a run that anchors at a
   still-streaming or crashed run's reply moves back to that run's user message and records the reply `deleted`, an
   alarm an analyst must read past; a damaged journal's late lines are left out of the rebuild, though the
   archive's raw journal keeps them. *Amends:* §13 *The run route*, step 2, and *Rebuilding the conversation*;
   decision 2. *Status:* folded.

8. **The archive's chat file also shows the messages off the active branch; the exported chat names a run's
   error, folds an anchor into its run's message and never reuses a client id** (2026-11-03; AG-UI conversation
   record, slice 2/4). `chats/NN-<slug>.md` renders the branch along `currentId`, then a section "Other branches"
   with every other message in record order, each naming the message it follows, with the same status lines and
   ignored blocks; `index.md` has the AG-UI columns `# | Session | Tags | Created | Runs | Compactions | State`.
   In the exported chat, `spe_run` also carries `error` (from `run_end.error`), which the status line shows; a
   run's `content` is its text joined without a compaction marker's summary, which stays its own `message` item;
   a run's message is `spe-run-<run id>`, and an anchor folded into an earlier run's message makes that run's
   message the parent; a client message id that is already exported, or starts with `spe-run-` or `spe-msg-`,
   is exported under a fresh `spe-msg-<n>` id with `spe_original_id`. *Reason:* a refused run adds no message,
   so it is never on the tip's branch, and two tabs make sibling branches; rendering only the active branch would
   hide a refused run's status and ignored content, which decision 16 says the archive shows. A failed run's
   reason belongs in the archive next to its status. Open WebUI shows a run's `content` as the reply, which the
   summary is not. An anchor is an AG-UI message id, and an assistant one lives inside its run's exported
   message. A client-chosen id equal to its own run's message, or to another exported id, could make a message
   its own ancestor and hang the walk along `currentId`. *Amends:* §14 *The Open WebUI chat* and *Write*.
   *Status:* folded.

9. **`GET /api/sessions/{id}` no longer answers `last_run_at`** (2026-11-03; AG-UI conversation record,
   slice 3/4, task 1). §6's row for that call drops the field; it stays on `GET /api/sessions`'s list rows.
   *Reason:* `last_run_at` tells a client its run was journaled apart from a metadata change, which a list
   row needs to reconcile after a run (decision 26); one session's own view does not, and the store's `get()`
   builds `SessionView` as `SessionMeta` without it rather than carrying a field nothing reads. *Cost if
   wrong:* a caller that read `last_run_at` off `GET /api/sessions/{id}` gets `undefined`; none does today.
   *Amends:* §6, the `GET /api/sessions/{id}` row. *Status:* folded.

10. **Activity messages on the journal's path are neither sent to the agent nor counted `deleted`** (2026-11-03;
    AG-UI conversation record, slice 3/4, task 2). §13 *The run route*, step 2 leaves every `role: "activity"`
    message out of the path it classifies against, and step 5 sends the agent that path. *Reason:* `@ag-ui/client`
    1.0.2's `AbstractAgent.prepareRunAgentInput` drops every activity message from a run's input, so the browser
    never sends one back, and counting it `deleted` would raise a false alarm on every run after one that emitted
    an `ACTIVITY_SNAPSHOT`; the recorder calls the agent itself, past that filter, so without this the agent would
    get an activity message no other run's input can carry. *Cost if wrong:* a client that dropped an activity
    message on purpose is not recorded as having done so, and a `MESSAGES_SNAPSHOT` sent after ignored content
    lacks activity messages (the browser keeps its own, which the snapshot does not mark authoritative); recording
    them later is a change to `classify` alone. *Amends:* §13 *The run route*, steps 2 and 5; decision 2.
    *Status:* folded.

11. **The conversation record is built; the archive exports the journals, and every archive still runs the
    barrier** (2026-11-03; AG-UI conversation record, slice 3/4). `chat-ui` keeps `/data/sessions/<uuid>.jsonl`
    (§13) and serves §6's session API from it; `archive.yml` copies the journals and the run log, exports the
    journals with the chat UI's exporter and renders them with `write_run.py` (§14); `<uuid>.json` and
    `write_agui_run.py` are gone. Until the live copy is built, every archive stops `chat-ui` and then the agent
    before the copy and starts them again after it, as the archive of the chat sessions did, and the bundle says
    `final`. (`GET /api/sessions/{id}` without `last_run_at` is clarification 9.) *Reason:* the record and its
    archive ship together, so `main` never holds journals the archive cannot render; the live copy (decision 30)
    follows separately. *Cost if wrong:* until the live copy, an archive taken while participants work pauses
    their runs for the copy (a run in progress ends `cancelled`), as it did before the record. *Amends:* the
    README's status line and the note above the decisions table, §14 (the paragraph on the archive as built, the
    last paragraph of *Why a live copy is consistent*). *Status:* folded.

12. **`/compact` is a command run: `chat-ui` journals it as a command, the agent compacts** (2026-11-03; the
    user, the fork's PR #26). §15 adds compaction on request: a run whose only new message is `/compact
    [focus]` is journaled with a `command`, never as a message; `chat-ui` sends the agent the path and
    `forwardedProps.spe_command`; the agent makes one summary request and returns the marker; a marker cut short
    is no cut point; the archive says the participant asked for it. Considered: a separate agent endpoint with
    `chat-ui` writing the marker as a new journal line (a second kind of marker for the rebuild, the exporter
    and the archive), and the agent recognising a `/compact` user message (the command stays in the history as
    the participant's words, and compaction decision 4 would keep it as the latest request). *Reason:* the
    user's request (2026-11-03, PR #21) that the command never be stored as a user message, and what other
    tools do: Claude Code, Codex CLI, OpenCode, Gemini CLI and Open WebUI all treat a manual compaction as a
    command, Open WebUI's offered only while its compaction is on. Decision 3 still refuses a client request
    with no new user message: a command run has one, the `/compact`, which `chat-ui` turns into a command.
    Decision 39's model-backed check runs on de.NBI's `qwen3.8-27b`, the platform participants use, at the
    user's request, not on the development VM's model. *Cost if wrong:* a participant who wants the literal text
    `/compact …` sent to the model cannot send it; the `/compact` bubble disappears when the run starts, which
    could read as a lost message (the early output shows it). *Amends:* §5 *Endpoints*, §13 (intro, *The run
    route* steps 2, 4 and 5, *The journal*'s `run_start` row, *Rebuilding the conversation*), decisions 2–6,
    the compaction design (decision 11, §8 *Run log*; its clarification 9), the README (status, decisions 31–39, early output,
    glossary, parts), `out-of-scope.md`, `inputs-for-plan.md`; adds §15. *Status:* folded.
13. **Decision 9's overlap is the recorder's; the route admits one run per thread** (2026-11-03; AG-UI
    conversation record, slice 4, task 2's Playwright checks). `lib/recorder.ts` supports two runs from one
    anchor overlapping and becoming sibling branches, proved by `npm test` driving `recorder.run()` directly;
    through `app/api/copilotkit/[[...slug]]/route.ts`, `CopilotRuntime` is constructed with no `runner`
    override, so its default `InMemoryAgentRunner` (`onConcurrentRun: "throw"`) admits one run per thread id at
    a time and refuses a second in-flight run on the same session with "Thread already running" before the
    recorder is ever called. §13 *Concurrency and branches* now says so, and slice 4's `check_restore_tip`
    proves decision 13's restore-to-tip and decision 2's no-false-alarm over two tabs without ever sending two
    runs on one session at once: it waits for tab A's run to end before tab B sends, so the two requests never
    collide with the route's lock, and the sibling-branch property still holds because neither tab refetches
    the other's work, so both still anchor at the one reply they last knew. *Reason:* no one had driven two
    truly overlapping runs on one session through the real route before this check; it is left as
    a known gap rather than fixed here because it fails safe (the second run errors; nothing is recorded
    wrong) and a fix needs a `runner` override or a different `AgentRunner`, outside this slice. *Cost if
    wrong:* a future regression specific to the route's own concurrent-run handling would not be caught by a
    Playwright check, only by `npm test`'s recorder-level coverage, until the route is fixed. *Amends:* §13
    *Concurrency and branches*; decision 9 (true of `lib/recorder.ts`, not yet of the route). *Status:* folded.

14. **The conversation record is built** (2026-11-03; the conversation record's slice 4/4).
    Decisions 1–18 and the journal parts of 19–30 are implemented, and the archive copies live, with the barrier
    only in the final archive `destroy.yml` runs (decision 30). The README's status and the decisions table's
    introduction no longer say the record waits to be built, and §14 drops the sentence that kept the barrier
    for every archive until then; no design changed. *Reason:* the plan's four slices merged and their acceptance
    checks ran (the last on the development VM). *Amends:* README (status, *Decisions taken*), §14 *Export*.
    *Status:* folded.
