## 13. The conversation record

`chat-ui` **owns the history**, as Open WebUI's backend does when it fronts an external agent: per session it
keeps an append-only **journal** of every run, written before the agent is called and as each event arrives.
For each run it takes from the client's request only the new user message, and sends the agent the history
from its journal. Everything else the client sent that differs from the journal is **ignored and recorded**
in full, with its kind. The agent stays stateless and unchanged (§5, *History*). A `/compact` is a **command run**, which
differs in steps 2, 4 and 5 below (§15). Decisions 1–11, 14, 17, 18 and 24 of
the [README](README.md#decisions-taken).

### Approach

Open WebUI's backend loads the stored chat and sends the model that, not the history in the completion request
(`load_messages_from_db` in v0.11.3's `utils/middleware.py`). When it fronts an external agent, the agent is
stateless and the backend owns the history. `chat-ui` is already a backend in that sense: its server route adds
the agent key and records the session. So it takes the same place, and the agent stays stateless:

- the record does not depend on the system under evaluation, which an infrastructure team may replace with
  another AG-UI agent;
- tools send history straight to the agent as before (promptfoo does), so the same attack can be run against
  the agent alone (it trusts a fabricated history) and through `chat-ui` (it does not), as a baseline and a
  mitigated variant of one experiment;
- the agent's compaction needs no change: it still trusts the marker it is sent, and through the chat a marker
  can now only come from the journal, that is from the agent itself.

Unlike Open WebUI, nothing edits the stored copy: there is no route that changes a message, so an edit through
the chat is always a new branch or ignored content, never an overwrite.

### The run route

The hook is a recorder middleware on the `spe` agent's `HttpAgent` (`lib/recorder.ts`, AG-UI `Middleware`,
`run(input, next)`, attached with `agent.use(...)`), which sees `input.messages` before the request is sent.
The runtime clones the agent per request (`cloneAgentForRequest`); `AbstractAgent.clone()` copies
`middlewares` and the in-memory runner calls `runAgent()`, which applies them, so the middleware survives the
clone (read in CopilotKit 1.79 and `@ag-ui/client` 1.0.2, pinned by a test). The middleware object is shared by
every clone, so it keeps no per-run state: each call of its `run()` makes a fresh run state in its own closure.

The in-memory runner runs the agent **detached** from the browser's request: when the client goes away the run
is not cancelled, it runs to its end. Only the stop button (the runtime's `/stop`, the runner's `stop`)
cancels a run.

Per run:

1. **Admit.** Refuse, without a journal line, a run whose `threadId` is not a valid id, whose session is
   deleted, or that arrives while `chat-ui` is closing (§14, *Barrier*): emit `RUN_STARTED` then `RUN_ERROR`
   ("invalid session" / "this session was deleted" / …) and do not call the agent.
2. Load the session from the index or journal. Compute the **anchor** and the **new messages** (decision 2),
   and compare the client's history with the journal's path to the anchor. The anchor is, of the client's
   messages whose id the journal holds, the one the journal added last, whatever the client's order. An anchor
   inside a run (a message that is neither a user message nor a run's last message, such as an assistant tool
   call whose result follows, a run's last message while a tool call that run made has no result in it, as
   a run cancelled, failed or cut mid tool call leaves it, or a run's last message while that run has no
   `run_end`, as a run still streaming or cut leaves it) moves back to the last run boundary before it, and
   the journal's messages after that boundary are `deleted`, even those the client sent, so the agent is never
   sent a dangling tool call. The new messages are the user messages after the anchor, in the client's order and at
   the anchor's position before any move back, whose ids the journal does not hold, each id counted once. A client message the journal holds with the same role, content, tool
   calls and tool call id is not recorded, wherever it stands: the journal already holds it, and
   `run_start.anchor` shows which branch the run continued. `ignored` lists the client's messages in the
   client's order, then `deleted` in path order:
   - a client message with an id the journal does not hold, other than a new message: `fabricated`; this
     includes every message after the anchor that is not a user message, every forged marker and every
     message without a string id;
   - a client message with a known id whose role, content, tool calls or tool call id differ: `edited`;
     other fields CopilotKit may add are not compared;
   - a message on the journal's path missing from the client: `deleted`, except an activity message
     (`role: "activity"`), which the client never sends back: `@ag-ui/client`'s `prepareRunAgentInput` drops
     every activity message from a run's input. Activity messages are left out of the path altogether;
   - a client system message: `system` (the agent replaces it anyway; recorded so it is not mistaken for one
     that reached the model).

   A command run's `/compact` message is none of these: its id is known from that run on, and it is never on
   the path (decision 32).
3. Refuse a run with a `runId` the journal already holds, without a journal line (decision 3).
4. Write `run_start` (decision 4). Then refuse a run with no new user message: `run_end` `refused`, and
   `RUN_STARTED` then `RUN_ERROR` to the client, without calling the agent (decision 3), so what it carried
   is recorded. A command run (§15) has no new message: its `run_start` carries the `command`
   instead, and it has refusals of its own (decision 34).
5. Replace `messages` with the path plus the new messages and call `next` (decision 5). The path holds no
   activity message (step 2), as no run's input does once `@ag-ui/client` has prepared it. If anything was
   ignored, emit `MESSAGES_SNAPSHOT` to the client right after the agent's `RUN_STARTED` (decision 6):
   `@ag-ui/client` 1.0.2's event verifier refuses a stream whose first event is not `RUN_STARTED` or
   `RUN_ERROR`. On every run, any `spe_command` the client put in `forwardedProps` is removed; a command run is
   sent the path, `spe_command` and always the snapshot (decisions 31, 33).
6. Append each event; write `run_end` from the terminal event, before that event is passed on, with its
   status:

   | Termination | `status` |
   |---|---|
   | `RUN_FINISHED` | `completed` |
   | `RUN_ERROR` with `code: "abort"` (the stop button, once the agent's response headers have arrived) | `cancelled` |
   | the stream errors with a raw `AbortError` (the stop button, before the agent's response headers arrive) | `cancelled` |
   | any other `RUN_ERROR`, or the stream errors with any other error (including an HTTP error from the agent before any event) | `failed` |
   | the stream completes without a terminal event | `failed` |
   | unsubscribed before a terminal event | `cancelled` |
   | refused after `run_start` (decision 3) | `refused` |
   | an append failed mid-run (decision 8) | `aborted` |

   `@ag-ui/client` 1.0.2 converts the stop's `AbortError` into `RUN_ERROR` `code: "abort"` only inside its SSE
   parser, which subscribes once the agent's response headers have arrived; a stop clicked earlier reaches
   the hook as the fetch's raw `AbortError` on the stream's `error:` callback. `error.name === "AbortError"`
   is what tells a stop from a failure (a dropped connection, a malformed frame).

Content is compared as the canonical JSON of the compared fields, so key order and absent-versus-empty fields
do not count as edits; the no-false-alarm check in decision 2 pins this against what CopilotKit really sends.

### The journal

`/data/sessions/<uuid>.jsonl`, one object per line, each with `type` and `at` (ISO 8601 UTC):

| `type` | Fields |
|---|---|
| `created` | `version: 1`, `id`; first line, written with the first `run_start` |
| `run_start` | `run_id`, `anchor` (message id or null), `messages` (the new messages), `ignored` (list of `{kind, message}`; for `deleted`, the id), `request` (`tools`, `context`, `state`, `forwardedProps` as sent), `source: "chat"`; a command run (§15) also `command` (`{name, focus, message_id}`) |
| `event` | `run_id`, `event` (the AG-UI event as received) |
| `run_end` | `run_id`, `status`, `error` (message or null) |
| `meta` | any of `title`, `tags`, `pinned`, `hidden`, `deleted_at`, as the session API sets them |

The title rule is §6's. A run's `run_start` is fsynced before the agent is called; events are fsynced at most
a second apart, and `run_end` at once, so a hard kill loses at most a second of one run. A run without
`run_end` is `incomplete`. Write failures end the run (decision 8): a record that silently misses events would
be worse than a failed run. The journal and the archive hold no request headers and no configuration, so
never the agent key; message content is stored unchanged. Session files in an earlier JSON format
(`<uuid>.json`) are neither read nor migrated.

A hard kill can leave a torn last line. Before its first append after loading a journal, `chat-ui` appends a
`\n` if the file does not end in one, so the next line starts clean; the rebuild skips a line that does not
parse (and logs it), so one torn line never hides the rest of the journal.

### Concurrency and branches

Open WebUI allows a second message while a reply is streaming; so does this design. Each line names its run, and
appends to one session go through one queue, so lines never interleave within a line. `chat-ui` is one Node
process (`node server.js`), so no cross-process lock is needed; Next.js bundles each route separately, so the
queue and the session list's index (§6) are kept on `globalThis` under `Symbol.for("spe.sessions.queue")`
and `Symbol.for("spe.sessions.index")`, and every route bundle uses those.

Two runs from the same anchor each chain their messages under it: siblings. A browser that keeps sending its
own history continues from its own latest message, so concurrent runs from two tabs show up as two branches
rather than one corrupted history. The session's **tip** is the last message of the run whose `run_end` (or,
if incomplete, last event) came last, among the runs that added a message; a refused run adds none. A session
none of whose runs added a message (only refused runs) is journaled and archived but not listed, and `GET`
answers `404` for it, as for a missing one. The chat reopens on the tip; navigating between branches in the chat is
out of scope (the archive keeps them all).

This overlap is the recorder's own: through `chat-ui`, two runs on one session are refused serially today, because
`app/api/copilotkit/[[...slug]]/route.ts` builds its `CopilotRuntime` with no `runner` override, so its default
`InMemoryAgentRunner` admits one run per thread id at a time and refuses a second in-flight run with "Thread
already running" before the recorder is ever called (clarification 13; a known gap, not fixed yet).

### Rebuilding the conversation

For each run in journal order: take the path to its anchor, append its new messages, and apply its `event` lines
with `@ag-ui/client`'s event application, as the browser does. A run's first `run_end` ends it: a later
`run_end` or `event` line of that run is skipped and logged by run id, so an ended run, which another run may
be anchored at, never changes. The messages the run added are, in order of first
appearance, chained by `parentId`: the first new message's parent is the anchor, every later message's parent
is the one before it. A `MESSAGES_SNAPSHOT` the agent itself sends is applied like any event; the one
`chat-ui` sends to the browser (decision 6) is not journaled, since it is derived. A compaction marker whose
`TEXT_MESSAGE_END` is not journaled is dropped (§15 *A marker cut short*, decision 37). The rebuild lives in one module
used by the run route, the session API and the exporter (§14), so the chat and the archive cannot disagree.

The session list's index (§6, *Session API*) holds, per journal, its `created`, its latest `meta` values, its
first user message and its last line's time; one pass over the journals at startup builds it, and every append
updates it.

### Boundary

The design closes the history edits made through the chat: the browser, devtools, and requests to `chat-ui`.
Two paths stay outside it and are stated, not solved:

- **The agent key.** Whoever holds it calls the agent directly, on port 8100; the agent trusts any history and
  only its run log (`runs.jsonl`) records the run. `chat-ui` holds the key in `chat-ui.env`, the agent in
  `agent.env`; the controller keeps a copy in its output directory. The sandbox shares the agent's `tools`
  network, so its environment must never hold the key (decision 17).
- **Root on the VM.** Whoever has it can edit any record on the VM, Open WebUI's database and these journals
  alike. Making records tamper-proof against root needs them shipped off the VM as they are written.

The threat entry (decision 18) describes the attack independently of the frontend: the injected content claims
to be the agent's own words or the environment's (a tool result), which makes it stronger than pasted text
(TM-005). Open WebUI's request path is closed the same way, but its stored chat is editable by design (its
message edit and history merge endpoints), so there the entry's mitigation is partial.
