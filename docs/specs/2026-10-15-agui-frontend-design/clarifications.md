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

15. **A manual marker's id is `spe-compaction-manual-<uuid4>`, and every compaction record has `focus`**
    (2026-11-03; AG-UI `/compact`, slice 1/2). The agent is stateless, so the next run can only tell a manual
    marker (whose frame says the participant asked) from an automatic one by what the chat sends back; every
    reader still matches the prefix `spe-compaction-` (`isCompactionMarker`, `is_compaction`,
    `_is_marker_message`), so nothing else changes. `markers_to_activities` carries the id onto the
    `CompactionPart` (`id=`), and `build_sent` reads it back to pick the frame. Every compaction record gains
    `focus` (null for the `threshold` and `overflow` triggers), so decision 11's records keep one shape.
    *Reason:* rulings 1 and 2 of the `/compact` plan. *Cost if wrong:* a marker written before this slice is
    automatic, which it was; a reader that parses the id after the prefix as a UUID breaks (none does); one more
    null field per record. *Amends:* §15 *The agent*, item 4; the compaction design's decisions 7 and 11.
    *Status:* folded. Added in review (#28): the focus is a user part of its own after the transcript's, not text
    appended to it, since a tool output in the transcript could carry the heading and pose as a focus; §15 *The
    agent*, item 3, says so.

16. **Sessions get a model-written title, the sidebar is resizable, and the chat gets a System/Light/Dark
    theme toggle** (2026-11-04; the fork's PR #29). §6 *Sessions* now says the fallback title (first user
    message, 60 characters) is replaced by a title the agent writes once the session's first run completes,
    unless the user already renamed it, journaled the same way a `PATCH` is; the session API table gains
    `POST /api/sessions/{id}/title`; §6 *The sidebar* now says the sidebar is resized by drag or the
    Left/Right arrow keys (200–480 px, 260 default, `localStorage` key `spe.sidebarWidth`) and its footer
    carries the theme control (`spe.theme`, `data-theme`, applied before paint so there is no flash); the
    README's decision 22 is rewritten for the title rule. §5 *Endpoints* gains `POST /title`, its
    *Configuration* block gains `title: {enabled, max_tokens}`, and its *Run log* now says a title call is a
    `{"type": "title", ...}` line, distinct from a run line (no `type`), which a run-log reader skips when
    counting runs. *Reason:* asked for by the user (2026-11-03): session titles and the sidebar's width were
    the two items left on the AG-UI chat minors backlog item, and a theme toggle was asked for alongside them.
    Both the title generation and the theme control are modelled on Open WebUI 0.11.3 (`ENABLE_TITLE_GENERATION`
    and its model request, and the sidebar's theme setting). *Amends:* §5 *Endpoints*, *Configuration*, *Run
    log*; §6 *Sessions*, *The sidebar*; README decision 22. *Status:* folded.

17. **Tool-call cards after Open WebUI's `ToolCallDisplay`** (2026-11-04; the fork's PR #31). §6 *Tool calls
    are rendered* now gives the card a status icon and an "Executing `<name>`…" / "View Result from
    `<name>`" / "`<name>` failed" title in place of the tool name, the command and the
    "preparing…/running…/done" text; the arguments as key/value rows instead of a JSON dump, `run_command`'s
    command as a `$ <command>` line; a failed state (a string `error` or a nonzero `exit_code` in the
    result); and a group header over the calls of one assistant message. *Reason:* asked for by the user
    (2026-11-03). Grouping covers one assistant message only, i.e. one model response's calls: calls from
    successive model steps arrive as separate messages (with reasoning between them on qwen), and grouping
    across messages would mean replacing CopilotKit's message list. *Cost if wrong:* successive single
    calls still show one card each, as before; a result whose JSON has an unrelated top-level `error` string
    is shown as failed; when a message's second call streams in, its first card moves under the new group
    header and remounts, so a card opened while the calls stream in closes again. *Amends:* §6 *Tool calls
    are rendered*. *Status:* folded.

18. **A resent command message is compared by its parsed command, not its raw text; `forwardedProps` that is not
    a plain object is normalized before the command key is set; the focus limit counts code points; and step 4's
    two refusals are checked in that order** (2026-11-04; AG-UI `/compact`, slice 2/2). §15 *The run route* now
    says: a resent command message stays unedited when its role is `user` and its content parses to the same
    command and focus, since `run_start.command` keeps the parsed command, not the raw text (`/compact` resent
    as `  /compact  ` is not `edited`); a `forwardedProps` that is not a plain object (absent, `null`, a list) is
    treated as `{}`, so a command run sends `{spe_command: {...}}` and an ordinary run sends it as the client
    sent it; the 1000-character focus limit is counted in code points, so 1000 emoji are allowed as 1000 letters
    are; and "Nothing to compact yet." is checked before the focus-length check, so a path that both ends in a
    marker and carries a too-long focus is refused for the first reason. *Reason:* slice 2's implementation
    needed each of these to behave one specific way, and the spec left them open. *Cost if wrong:* a resent
    `/compact` with different whitespace would be recorded `edited` though nothing the agent saw changed; a
    non-object `forwardedProps` could crash the merge instead of starting a run; a focus near the limit would be
    measured in UTF-16 units instead of characters, cutting a focus with emoji short of 1000; and the two
    refusals could report the wrong reason on a path that triggers both. *Amends:* §15 *The run route*, steps 2,
    4 and 5. *Status:* folded.

19. **`/compact` gets a slash-menu entry and a marked composer** (2026-11-04; the fork's PR #32). §15 gains *In the
    chat input*: CopilotKit's built-in slash menu offers a `compact` entry while the input's whole text is a
    prefix of `/compact`, and picking it sends a bare `/compact`; the composer is marked (border, monospace, a
    "command" badge) while the text parses as a command. The out-of-scope list no longer names a command menu.
    *Reason:* asked for by the user on #30 (2026-11-04): the command was undiscoverable and looked like a
    message until sent. *Cost if wrong:* the menu's entry sends `/compact` with no focus, so a participant who
    wanted one has to type it after the command. *Amends:* §15, out-of-scope. *Status:* folded.

20. **Tool cards worded as Open WebUI 0.11.3 words them** (2026-11-04). §6 *Tool calls are rendered* now titles a
    finished card `<name>` alone instead of "View Result from `<name>`" (Open WebUI's label in a narrow chat;
    "Executing `<name>`…" and "`<name>` failed" stay); labels the unfolded card's arguments "Input" and its result
    "Output"; and heads a group "Exploring" / "Explored" followed by the tools called, each once with its count
    (`list_files, 2 run_command`), as Open WebUI's `ConsecutiveDetailsGroup` does, instead of "Executing N
    tools…" / "View Results from N tools" and a separate list of names. The group keeps our "· N failed".
    *Reason:* asked for by the user while testing #32 on de.NBI (2026-11-04): the check icon already says a call
    is done, so "View Result from" repeated it; checked against Open WebUI's `ToolCallDisplay.svelte` and
    `ConsecutiveDetailsGroup.svelte` at v0.11.3, which show the raw tool name, no friendlier per-tool text.
    *Cost if wrong:* a finished card no longer says in words that it can be opened, only its chevron does; the
    group still covers one model response's calls, not Open WebUI's run of consecutive calls and reasoning
    across steps (clarification 17). *Amends:* §6 *Tool calls are rendered*; clarification 17's titles.
    *Status:* folded.

21. **The theme control becomes a toggle at the chat pane's top right** (2026-11-04). §6 *Look* and *Layout*: the
    sidebar footer's System / Light / Dark select is replaced by a pill switch (sun, moon, a sliding knob) pinned
    to the chat pane's top right. The stored values stay `system` / `light` / `dark` under `spe.theme`, and the
    before-paint script is unchanged: a click flips the rendered theme, stored as `light` or `dark`, or as
    `system` when the system already prefers the new theme. *Reason:* asked for by the user while testing #32 on
    de.NBI (2026-11-04): the footer select looked dated and was hard to find. *Cost if wrong:* there is no
    explicit "System" option; a participant whose system theme changes while a forced theme is stored keeps the
    forced one until they flip the toggle to the system's theme. *Amends:* §6 *Look*, *Layout*; clarification
    16's footer control. *Status:* folded.

22. **The frontend runs from a clone of the repository on the VM** (2026-11-04; the fork's merge of `upstream/main`,
    PR #35). Upstream replaced the role's rendered compose file and content-hashed images with the clone-on-VM
    layout: `platform/instance/compose.yml` with compose profiles, images tagged `:local` built by `spe-apply`,
    the prompt (`/etc/spe-agent/sandbox/system_prompt.txt`, read per run) and the agent's source bind-mounted from the clone; `spe_agui_source_dir` is gone and a branch is
    deployed with `-e spe_repo_ref=<branch>`. The `chat-sessions` volume moved into that compose file, mounted in
    `chat-ui` and in the `ui-dev` profile's `chat-ui-dev`. *Reason:* upstream's layout, taken in the merge.
    *Cost if wrong:* the `ui-dev` profile has no archive and no chat-ui hardening check yet. Upstream also folded pasted text (TM-005) into indirect prompt
    injection (TM-003) and dropped `python-frontmatter` from the validator. *Amends:* §5's example `agent.yaml`, §6
    *Storage*, §7 *Role `agui`* and its variables, §13's threat reference, decision 18's check. *Status:* folded.

23. **Both frontends run on every instance, and the AG-UI part of a run is archived in `agui/`** (2026-11-04; the
    merge of kraatz #16, `d2a6232`). Upstream made the single-valued `spe_frontend` a list,
    `spe_frontends`, by default `[openwebui, agui]`, both driving one sandbox; the portal has no frontend parameter
    any more and the old `spe_frontend` is still read when set. The archive exports each frontend that is on, and
    `write_run.py` renders the AG-UI bundle into `<run dir>/agui/` (its `index.md`, `chats/`, the bundle, the raw
    journals `agui-journals/` and the run log `agent-runs.jsonl`), because rendered into the run directory itself it
    would replace Open WebUI's `chats/` and `index.md`. The top `index.md` links `agui/index.md`. *Reason:* upstream runs
    both frontends; a separate `agui/` keeps `write_run.py` from clearing Open WebUI's `chats/` and `index.md`. *Cost if wrong:* a run from an
    AG-UI-only instance has its sessions one directory down, and a tool reading `<run>/agui-journals/` must read
    `<run>/agui/agui-journals/`. *Amends:* §1 *Goal*, §3's container table intro, §7's variables, §9's condition,
    §14 *Export* and *Write*, decisions 15's and 30's checks. *Status:* folded.

24. **A click outside the row menu refocuses its `⋯` when it left focus nowhere; a reopened session opens on its
    newest content** (2026-11-08, the user's choice; the fork's PR #46). After a press outside closes the row menu (or its tag
    editor), in the sidebar and the chat header, the page waits for the press's own focus change and gives focus
    back to the `⋯` only if it is then on the page itself (`body`, `<html>` or none), and not after a tap (a
    touch press), so a press on a field, button or link keeps it; before, a click outside always left focus where it put it. Opening or reloading a session no longer
    animates a scroll through its whole history (CopilotKit's scroll view, `initial: "smooth"`, about a second
    with the newest content below the fold): it starts at the end at once; a live send still scrolls smoothly.
    *Reason:* the refocus had waited only because it would take focus from what the click landed on; checking
    where focus went after the press removes that, and a keyboard user is not dropped to the top of the tab
    order by a stray click. The scroll was seen with `/compact`'s divider, below the fold right after a reload.
    *Cost if wrong:* in Safari, which does not focus a button on click, a click on another button gives focus to
    the `⋯` although the button acted; a click into chat text moves focus (not the selection) to the `⋯`; the
    instant start relies on CopilotKit passing the scroll slot's props to `use-stick-to-bottom`, which its type
    leaves out. *Amends:* §6 *Row menu*, *Opening a session*; reverses the chat sessions spec's clarification 7
    (a click outside never refocusing the `⋯`). *Status:* folded.
