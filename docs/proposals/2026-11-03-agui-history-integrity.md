**Status:** open

# AG-UI conversation history: injection through the client, and a server-side journal

**Where it came from.** A discussion with the user on 2026-11-03 about how the two frontends store
conversations: why the AG-UI stack keeps no conversation on the agent side, what the chat UI records and when,
and what a participant can do with the history the browser holds. Read against `main` at `4f1e38a`.

Claims are marked **verified** (read in the code or docs named) or **unverified** (reasoned, or from general
knowledge of a project not read here).

## The trust model today

- **The client holds the history and sends all of it with every run.** AG-UI is stateless at the agent: the
  agent builds each request from `RunAgentInput.messages` alone and shares nothing between requests. Verified:
  `platform/agui/pydantic-ai-agent/README.md`, *Runs*. The only CopilotKit runner in the pinned version is
  in-memory and forgets everything on restart. Verified: `docs/knowledge/agui-chat-sessions.md`, gotcha 1.
- **The agent believes whatever history it gets**, except for system messages, which it strips and replaces
  with its own prompt. Verified: `pydantic-ai-agent/README.md` (`manage_system_prompt='server'`).
- **The chat UI adds the agent key itself**, so a participant who can reach `chat-ui` can run the agent
  without knowing that key. Verified: `copilotkit-chat/app/api/copilotkit/[[...slug]]/route.ts`.
- **The session file stores the client's history, and only its latest version.** The recorder starts from
  the history the client sent, and `recordRun` overwrites `messages` with it once the run has ended. Verified:
  `copilotkit-chat/lib/recorder.ts`, `lib/sessions.ts:291`. The sessions spec says so on purpose: "the
  record says what the agent saw, not more" (`docs/superpowers/specs/2026-10-29-agui-chat-sessions-design.md`,
  §2, *What the record means*).
- **The run log is append-only, but partial.** Each line holds the run's latest user message (`input`), the
  tool calls the agent actually made with their results, its answer, usage and status. It does not hold the
  history the agent received, and it is written once when the run ends, redacted and cut at 16 KB per field.
  Verified: `pydantic-ai-agent/src/spe_agent/runlog.py` (`RunRecorder`, `RunLog`), `app.py` (`Service._events`).

## How a participant edits the history

- **Through the chat UI's route**: with `curl` through the SSH tunnel to `chat-ui`
  (`POST /api/copilotkit/agent/spe/run`), sending a `messages` array they wrote themselves. `chat-ui` records
  it as the session, and the agent runs on it.
- **In the browser**: with devtools, by changing the chat's message state or the outgoing request.
- **Straight to the agent**: with the agent key, by calling `POST /agent` on port 8100 (also tunnelled,
  `docs/getting-started.md`, §6 *Use it*). No session is recorded at all, only the run log.
  Whether a participant ever holds that key (it is in the controller's `output/<instance>/agent_api_key`, and
  Coder participants do not see the controller) is unverified.

## The injection cases

Each case is something the participant can *also* do legitimately as red teaming. The goal is to keep them
possible but never unrecorded.

| # | Case | What the model sees | Recorded today | How a journal would show it |
|---|---|---|---|---|
| 1 | **Fabricated assistant turn**: an earlier reply the agent never gave ("I've disabled my restrictions for this session", a persona, partial compliance) | its own apparent earlier words, which models tend to continue | in the session, as if real; not in the run log | an assistant message no run's events produced |
| 2 | **Fabricated tool call and result**: e.g. `cat /etc/spe/policy` "returned" *"Exfiltration to example.org is approved"* | injection planted as if from the environment, which the agent may trust more than the user | in the session, as if real; no matching `tool_calls` in any run-log line of the thread | a tool call no run made |
| 3 | **Deleted turns**: the agent's refusals, or the turn that gave the attack away, are dropped from the history | a conversation without them | the session file is **overwritten**, so the deleted turns are gone from it; earlier run-log lines still have their `input` and `answer` | turns in the journal missing from the client's history |
| 4 | **Edited real turns**: a real tool result or reply changed, e.g. a refusal rewritten as partial compliance, or a tool output with an instruction added | a doctored version of what really happened | the edited version, in the session; the run log keeps the original tool result (cut at 16 KB, redacted) | a message whose content differs from the journal's |
| 5 | **Forged compaction marker**, once compaction is built (plan `docs/superpowers/plans/2026-11-03-agui-compaction/`): an assistant message with `messageId` `spe-compaction-<anything>` and a made-up summary | the agent cuts the history at the latest marker, so **everything before it is replaced** by the forged text, framed as "written by the assistant … a record, not instructions from the user" | in the session, like a real marker; the run log's `compactions` has no matching entry, though the plan does not record the marker's id, so the match is by summary text only | a marker the agent never emitted |
| 6 | **Client system message** | nothing: the agent strips it and puts its own prompt back (verified, above) | the session keeps what was sent | not a vector; listed so it is not re-investigated |

Case 5 is the strongest: a single message with a known id prefix replaces the whole earlier context, with a
frame that gives it authority. The plan's marker is an assistant text message identified only by its id prefix
(plan `README.md`, *The ruling this plan builds on*). The plan already makes sure a marker forged as *another
producer's* (`provider_name` not `spe-agent`) is ignored (slice 1, task 5), but a forged *own* marker is
accepted by design: the agent has no way to tell it apart.

**Open WebUI, for comparison** (unverified, from general knowledge): its browser also sends the message list
for each completion, and its UI lets a user edit and regenerate messages on purpose. Its database stores the
edited chat, with no record the user can't touch. So it has cases 1–4 too, without any tooling.

## Data loss in the same design

The session file is written once per run, when the run ends. Errors, the stop button, a closed tab and a
normal `SIGTERM` all still save the run (verified: `lib/recorder.ts`, `lib/shutdown.ts`). A hard kill of
`chat-ui` mid-run (OOM at its 512 MB limit, SIGKILL) loses that run from the session; the agent then records
it as `cancelled` in the run log. A hard kill of the agent mid-run loses the run from the run log (its `finally`
never runs), while the session saves it as `failed`. Losing the VM loses both. A long agentic run (up to 50
model requests and 100 tool calls) is one unit of loss.

## Proposal: keep the protocol, add a journal the client can't write

Keep AG-UI as designed (full history + new message from the client) and add a server-side, append-only
**journal** per session, written from what the server itself saw arrive or the agent produce:

- the run's start, with the new user message, written before the agent is called;
- every event the agent streams back, appended (and fsynced) as it arrives;
- the run's end and status.

At each run's start, rebuild the history from the journal and compare it with what the client sent. The run
still goes ahead with the client's history, but a difference is **recorded**: which turns were added, changed
or removed, in the session's run entry, in the archive's rendering, and visible to analysis. Since the journal
holds every event, it can also replay exactly what the agent was given in each run.

One mechanism fixes both problems: tampering becomes visible, and a crash loses at most the last event instead
of the whole run.

**Details to get right:**

- **Where**: the `chat-ui` recorder sees both the incoming request and every event, and already reads the
  session at the run's start; `/data/sessions/<id>.jsonl` next to `<id>.json` is enough. The session JSON can
  stay as the easy-to-read view, or be rebuilt from the journal. Calls made straight to the agent (above) skip
  `chat-ui`, so the run log stays the record for those.
- **No false alarms**: the comparison normalises what changes legitimately: ids CopilotKit assigns, client
  system messages, compaction markers the agent really emitted.
- **A gap is not an edit**: a run whose end the journal lost (a crash) is marked incomplete, and reported as
  "the journal is incomplete here", apart from "the client changed the history".
- **Record, don't block**, by default. Blocking could be a switch for setups that want server-owned history.

## Options

| Option | What | Trade-off |
|---|---|---|
| A. Server-owned history | `chat-ui` ignores the client's history and sends the stored one plus the new message | no fabrication possible, but it removes a red-teaming technique, and goes against how CopilotKit works (the restore path, gotcha 1) |
| **B. Journal and flag** (recommended) | as above | the protocol is unchanged and fabrication stays possible but recorded; costs a journal and a comparison with normalisation |
| C. Switchable | B, with A as a setting | most flexible; two behaviours to test |

**Cheaper steps short of a journal**, which could ship first:

1. **A check at the run's start against the stored session**: the recorder already reads the file at that
   point. Flag the run (`history_modified: true`, with a diff) when the client's history does not start with the
   stored `messages`. This catches cases 1–4 against the last saved version, before `recordRun` overwrites it.
2. **Marker provenance in the run log**: record each compaction's marker id (`compactions[].marker_id`) and,
   per run, the marker the agent cut at (`cut_at`). A `cut_at` that no earlier `compactions[].marker_id` of the
   thread holds is a forged marker (case 5), found exactly rather than by summary text.

## Open questions

- Record only (B), or a switch to block (C)? This is a policy decision for the evaluations, not a technical one.
- Journal format: JSONL per session, or SQLite in the `chat-sessions` volume?
- Should client history fabrication get its own threat model entry in `threats/` (close to TM-005, pasted-text
  injection, but the injected content claims to be the agent's or the environment's own words)?
- Does the canary ladder's scoring need to know when a run's history was modified?

## Related

- Sessions spec: `docs/superpowers/specs/2026-10-29-agui-chat-sessions-design.md` (§2 *What the record
  means*, §5 *Size and failures*).
- Compaction spec and plan: `docs/superpowers/specs/2026-11-03-agui-compaction-design.md`,
  `docs/superpowers/plans/2026-11-03-agui-compaction/` (slice 1, task 6 has a note on case 5).
