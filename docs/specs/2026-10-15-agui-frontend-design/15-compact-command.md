## 15. `/compact`: compaction on request

The participant types `/compact`, or `/compact <focus>`, in the chat, and the agent compacts the conversation
now, without waiting for the trigger: the same summary request, the same marker, the same divider in the chat and
the same "Compacted" section in the archive as an automatic compaction (the AG-UI compaction design, whose
decisions this section cites as "compaction decision N"). `chat-ui` recognises the command and journals it
as a **command**, never as a message; the agent, which holds the LLM key, makes the summary. Decisions 31–39 of
the [README](README.md#decisions-taken).

### Approach

Every tool with a manual compaction treats it as a command, not as something the participant said: Claude Code
(`/compact [instructions]`, a command entry and a compact boundary in its transcript), Codex CLI (`/compact`, an
operation of its own, never in the history), OpenCode (`/compact`, a synthetic message holding a typed
`compaction` part, not text), Gemini CLI (`/compress`) and Open WebUI (`/compact`, a built-in command, offered
only when its context compaction is on and not while a response is generating, and saying why when it skips).
Two other shapes were considered (clarification 12):

- **A separate agent endpoint** returning the summary, with `chat-ui` writing the marker as a new journal line:
  the rebuild, the exporter and the archive would each learn a second kind of marker, and the stop button and
  the run log their own path.
- **The agent recognising a `/compact` user message**: no change to the run route, but the command stays in the
  history as the participant's words (the title, the archive's turns, anything that scores them), the agent
  parses chat conventions on every path that reaches it, and the latest user request it keeps after a cut
  (compaction decision 4) would be the command itself.

So a `/compact` is an ordinary run from `chat-ui` to the agent, carrying a command instead of a new message.
Every other part of the record (the journal, rebuild, branches, tip, archive, run log) handles it as any run.

### What counts as a command

A run is a **command run** when its new messages (decision 2) are exactly one user message whose content is a
string that, trimmed, is `/compact`, or `/compact` followed by whitespace and a **focus** (the rest, trimmed).
Case matters. Anything else is an ordinary message: `/compacted`, `/compact:`, a message whose content is not a
string, `/compact` arriving with other new messages. There is no escape for sending the literal text to the
model.

### The run route

§13 *The run route*, with these differences for a command run:

- **Step 2.** The command message is not a new message: the run's `messages` is empty. Its id is **known** from
  then on, for one purpose only: a later client history that sends it back with the same role (`user`) and
  content that parses to the same command and focus ignores nothing for it; one with a different role, or
  content that does not parse to the same command and focus, records it `edited`. The comparison is against the
  parsed command, not the raw string, since `run_start.command` keeps only the parsed form: `/compact` resent as
  `  /compact  ` is not `edited`. It is never the anchor and never on the path, so it is never `deleted`, and the
  rebuild and the session API leave it out. The browser does send it back: after a refusal, or a stop before the
  agent's `RUN_STARTED`, no snapshot replaces its bubble, and the next run anchors on the latest path message the
  client holds, as if the bubble were not there.
- **Step 4.** `run_start` carries `command: {name: "compact", focus: <string | null>, message_id: <the client's
  id>}`. Two refusals follow it, checked in this order, as decision 3's do (`run_end` `refused`, `RUN_STARTED`
  then `RUN_ERROR` to the client, the agent not called):
  - the path holds no message after its latest compaction marker (an empty session, or one compacted with
    nothing since): "Nothing to compact yet." A path that both ends in a marker and carries a too-long focus is
    refused for this reason, since it is checked first;
  - the focus is longer than 1000 characters, counted in code points (1000 emoji are allowed, as 1000 letters
    are): "The focus after /compact is too long (1000 characters at most)."

  A session whose only runs are refused is not listed (decision 9), so a new chat opened with `/compact` leaves
  no session and no title.
- **Step 5.** The agent is sent the path, with no new message, and `forwardedProps.spe_command = {name:
  "compact", focus}`. `chat-ui` sets that key on every run: it first removes any `spe_command` the client sent,
  so only a typed `/compact` makes a command run. Before that, a `forwardedProps` that is not a plain object
  (absent, `null`, a list) is treated as `{}`: a command run then sends `{spe_command: {...}}`, and an ordinary
  run sends `forwardedProps` exactly as the client sent it, whatever shape that is. `run_start.request` keeps
  `forwardedProps` as the client sent them. Right after the agent's `RUN_STARTED`, `chat-ui` always sends the
  client a `MESSAGES_SNAPSHOT` of the path, so the `/compact` bubble the browser added is gone, live as after a
  reload, and the marker lands after the last message.

Everything else in §13 is unchanged: the admission checks, the duplicate `runId`, a run with no new user message
(decision 3), the journal's lines and fsyncs, the termination table, concurrency (a `/compact` sent beside another
run is a sibling branch from the same anchor; the browser's input is disabled during a run anyway). Accepted:
a `/compact` from a second tab while the first tab's run streams compacts the path up to that run's user
message, and if the other run ends later the tip is its reply, on a branch without the marker, so the
compaction has no effect on what the chat reopens on; the archive keeps both branches.

### In the chat input

The command is discoverable and marked, without changing what counts as one:

- **The slash menu.** CopilotKit's input opens a menu from its `toolsMenu` when the text starts with `/`. The chat
  passes one entry, `compact`, while the input's whole text is a prefix of `/compact` (`/`, `/co`, `/compact`),
  and none otherwise, so a `/compact <focus>` (or any other text starting with `/`) shows no menu rather than
  "No commands found". Picking the entry, by a click or Enter while it is highlighted, clears the input and sends
  a bare `/compact`: with the menu open, Enter picks the entry instead of sending, which is why the whole text
  counts and not only its first line (a focus on a second line would be lost). The "+" button, which would show
  the entry too, stays as it is without it.
- **The marking.** While the input's text parses as a command (*What counts as a command*), the composer is
  marked: a stronger border, the text in monospace, and a "command" badge on its border. A textarea cannot
  colour one word, so the whole composer is marked.

Acceptance: `npm test` (`offersCompact`: `/`, `/c`, `/compact` offer the entry; `/compact `, `/compact keep x`,
`/compact` then a newline and `keep x`, `/` then a newline and `hello`, `/compacted`, ` /compact`, `/COMPACT` do
not); Playwright against `fake_agent.py` (`sessions.py --scenario
compact-command`): `/co` shows the entry and leaves the composer unmarked, `/compact keep the canary paths` shows
no menu and marks it, and Enter on `/comp` with the entry highlighted adds a second divider and journals a
command with no focus.

### The agent

When the run input's `forwardedProps.spe_command.name` is `"compact"`, `app.py` does not start the model loop:

1. It sends `RUN_STARTED` at once, before any model request, so `chat-ui`'s snapshot (step 5) replaces the
   bubble as the run starts. It converts the input as for any run (markers become cut points) and takes what
   would be sent (compaction §3).
2. With compaction off (`compaction.enabled: false`): `RUN_ERROR` "Compaction is turned off on this instance."
   With nothing after the latest cut: `RUN_ERROR` "Nothing to compact yet." (the backstop of `chat-ui`'s check).
3. Otherwise one summary request, as compaction decision 5 makes it (same model, no tools, the package's
   prompt, cut tool output, the window budget, the retry with the older half left out when the summary request
   itself overflows). Two things differ. The focus is not a `User:` entry of the transcript: it follows the
   transcript as a section of its own, "The participant's instructions for this summary", fenced with a fence
   longer than any backtick run inside, in a user part of its own (so no tool output in the transcript can pose
   as it), never in the system prompt; so the latest real request stays the one the
   transcript pins and the summary quotes. And the prompt and the summary's frame say the participant asked for
   the summary, not that the conversation no longer fit (a manual variant of each). It counts towards the run's
   usage limits and is checked before it is sent.
4. It streams the marker's three events (compaction decision 7, its id `spe-compaction-manual-<uuid4>`), back to
   back once the summary is complete, then `RUN_FINISHED`. A failed summary request is `RUN_ERROR`, sanitized as
   every error is. A run cancelled
   during the summary request (the stop button, or `chat-ui` going away) sends no marker events, and its run log
   record has the cancelled run's status and `compactions` empty.

Any other `spe_command` gets `RUN_ERROR` "Unknown command." The run log's record has `input` `/compact`, or
`/compact <focus>`, not the path's last user message, and `compactions: [{trigger:
"manual", focus, …}]` (`manual` a third trigger beside `threshold` and `overflow`), the fields of compaction
decision 11, `next_input_tokens` null, redacted as every
record is.

### A marker cut short

A marker counts only when its `TEXT_MESSAGE_END` is in the journal. The rebuild drops a marker message with no
`TEXT_MESSAGE_END`, whatever its run's status (stopped, failed, cut, or incomplete with no `run_end`), so the agent is never
sent a truncated summary as its cut point. This holds for automatic compactions too. Stopping a command run
during the summary request ends it `cancelled` with no marker: nothing is compacted.

### The archive

The marker renders as compaction's "Compacted" section (§14, decision 16), with one more line when its run was a
command run: *Requested by the participant (`/compact`)*, and the focus, fenced with a fence longer than any
backtick run inside. The exporter takes it from `run_start.command` and puts it on the run's message as
`spe_command`, for every command run, refused and failed ones too, so the archive shows the command a refused
or failed run carried beside its status. `index.md`'s `compactions` count includes manual ones.

### Upstream

`/compact` reaches participants with the AG-UI compaction, in the same upstream change or after it, never
before: it needs the agent's compaction.
