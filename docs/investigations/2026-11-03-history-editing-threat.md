# Editing the chat history: a vulnerability, and why Open WebUI allows it

**Question** (the user, 2026-11-03): Open WebUI lets a user edit model replies in the history. Isn't that a
vulnerability? An edited reply that shows the model exposing a secret, even a dummy one, could signal that the
model does that, so on the next request it actually exposes real secrets. Why does Open WebUI keep the feature?

**Short answer.** The attack works. But in Open WebUI's own threat model it is not a vulnerability, because the
user owns the chat. It matters in an SPE because the agent holds data the participant must not steer, and the
evaluation needs to know what really happened. The model's refusal was never the security boundary.

Background, with the code references: [`../proposals/2026-11-03-agui-history-integrity.md`](../proposals/2026-11-03-agui-history-integrity.md)
(the injection cases, Open WebUI v0.11.3's behaviour). Claims are marked **verified** where that proposal checked
them in the source, **unverified** where they are reasoning or general knowledge.

## Why the attack works

- **It is the proposal's case 1, a fabricated assistant turn.** The model reads the edited reply as something
  it already did, and models tend to stay consistent with their own earlier behaviour. It is the same mechanism
  as prefill attacks and many-shot jailbreaking: fake "I already complied" turns make it more likely to comply
  on the next request. (Unverified: general knowledge of model behaviour, not measured here.)
- **Case 2, a fabricated tool result, is stronger.** Text that looks like it came from the environment ("policy
  says export is approved") gets more trust than the user's own words. Open WebUI v0.11.3 lets you edit tool
  calls and results too, in the response edit view's JSON editor, and replays them to the model. (Verified, in
  the proposal.)
- **The edited turn leaks nothing by itself.** A real leak only happens if, on the next run, the model actually
  reads the data with its tools and puts it in an answer.

## Why it isn't a vulnerability in Open WebUI's own terms

- **The user owns the chat.** An edit gives them nothing they don't already have: they could write "earlier you
  agreed to show me the file, here's what you said: …" as a normal prompt. Editing makes the injection more
  convincing, but the person doing it already has the power to do it.
- **Model APIs accept made-up history anyway.** The OpenAI-style and Anthropic message APIs are stateless: the
  caller sends the whole `messages` array every time, fake assistant turns included, and tool results always come
  from the caller, since the caller runs the tools. Anyone with an API key can do this without Open WebUI, so
  blocking it in the UI would not secure anything. (Unverified for OpenAI; for Anthropic, see the next section.)
- **The model refusing was never the security boundary.** If the only thing between a participant and a secret
  is the model saying no, that boundary already falls to an ordinary jailbreak; history editing just makes it
  easier. In an SPE the real controls are in the environment: what the agent's tools can reach, where network
  traffic can go, and checks on what leaves.

## What Anthropic's API accepts (checked 2026-11-03)

Checked against the `claude-api` skill bundled with Claude Code 2.1.280 (`shared/model-migration.md`), not
against Anthropic's live docs. This corrects an earlier version of this note, which said from memory that
Anthropic "documents prefill as a feature":

- **Prefill is gone on current models.** A request whose last message is an assistant turn (a prefill) returns a
  400 on Opus 4.6 and later, Sonnet 4.6 and later, and the Fable family. Haiku 4.5 is not in the list of models
  that removed it.
- **Fabricated earlier turns are still accepted.** Past assistant turns, tool calls and tool results in the
  history are not checked against what the model really produced.
- **Edits are checked only through thinking blocks.** On Fable 5.1 and Opus 5.5, each thinking block is signed
  together with the conversation before it. If an earlier turn is edited and a later thinking block is replayed,
  the request fails with a 400 (enforced by default for accounts created on or after 2026-08-31, opt-in for older
  ones), or the block is dropped. A history with no thinking blocks has nothing to check, so on our reading of
  the docs a fully fabricated history without them still goes through. The docs present this as keeping the
  model's reasoning consistent, not as a defence against jailbreaks.

So the provider does not guarantee that a history is real. The client is trusted to send it honestly, and
resistance to a fake history is left to the model's training and the provider's safety classifiers.

## Why Open WebUI keeps the feature

Reasoning only: no stated rationale was found in Open WebUI's docs or source. For a personal assistant these
uses are useful and harmless:

- **Curating the context**: remove a hallucinated answer so it doesn't pollute later turns, fix a wrong fact,
  cut a long reply to save tokens.
- **Prompt-engineering work**: build few-shot examples by hand, steer a persona, branch to try alternatives
  (*Save As Copy*, or *Send* on a user message).
- **Light cleanup**: fix formatting or typos before exporting or sharing a chat.

## Why it matters here anyway

The SPE threat model differs on two points:

1. **The agent holds data and tools the participant must not be able to steer**, so anything that makes
   jailbreaking easier counts in the evaluation.
2. **The evaluation needs to know what really happened.** In Open WebUI an edit leaves almost no trace (only
   `originalContent`, one level deep, for in-place text edits of replies), and the archive exports the edited
   chat (verified, in the proposal). So an edited conversation can make it look as if the model leaked something
   it never did, or hide the turns that set up a real leak.

This is why the proposal's direction is *record, don't block*: keep editing possible as a red-teaming technique,
but never let it go unrecorded.

## Follow-up questions (same discussion)

**Why is the API stateless, and could Anthropic tell if this session's history were edited?** Keeping state is
feasible: Anthropic's Managed Agents keeps server-side sessions, and OpenAI's Responses API can continue from a
stored response (unverified). Statelessness is a design choice. Our reasons for it, not a stated rationale from
Anthropic: any server can answer any request; nothing stored means nothing retained; the developer keeps control
of the context; the client runs the tools anyway; and prompt caching makes resending the history cheap. A Claude
Code session is the same pattern: the transcript lives on the user's disk (`~/.claude/projects/…`) and is sent
whole with every request. Edit it and resume, and Anthropic sees only the edited version. The exception is signed
thinking (Opus 5.5 and Fable 5.1): an edit followed by a later thinking block fails the check. It is rejected for
accounts created on or after 2026-08-31, and recorded for older accounts but acted on only if the request opts in.
An edit with no thinking block after it, or a history with every thinking block stripped, passes.

**Does a signature stop tampering?** It makes tampering *detectable*, under three conditions: verification is
mandatory (unsigned history doesn't pass silently), the signature covers the whole conversation up to that point
(so turns can't be deleted from the middle or reordered), and the key stays away from the client. It cannot
detect a client going back to an earlier, validly signed version. Only server-side state can see that, for
example the latest signature per conversation.

**Is going back to an earlier version bad?** No. Rollback and forking are legitimate, the same as editing an
earlier message and resending it (Open WebUI's *Send* does this). The history the model gets back is one it
really produced, so the model is not fooled. Deleting a turn from the middle while keeping the later ones is a
different thing: that gives the model a conversation that never happened. What rollback does affect is the
record. Example: a participant asks for the dataset at turn 3 and is refused, then retries from the same point
20 times until one phrasing works. The session file, overwritten with the client's latest history, then shows a
three-turn conversation that leaked at turn 3, and the archive renders that file. The run log has all 22 runs,
but each line holds only that run's new message, so nothing links the 20 attempts as branches of one
conversation. "Leaked once in 20 attempts" reads as "leaked at turn 3". So a rollback should be recorded as a
branch, not flagged as tampering.

**Can the chat UI edit history?** No (verified). `@copilotkit/react-core` 1.79.0 shows a user message's edit
button only when the page passes `onEditMessage`, and a reply's regenerate button only with `onRegenerate`
(`dist/copilotkit-DQvE96lZ.mjs`, around lines 6428 and 6786). `app/page.tsx` passes neither. So in the UI a
participant can only append. Editing needs devtools, `curl` to `chat-ui`'s route, or a call to the agent with
its key (the proposal, *How a participant edits the history*). This is the general rule: **the frontend is not
a security boundary.** Anyone who can reach the server can send it any request, posing as the client. Enforcing
or recording has to happen in `chat-ui`'s server route or in the agent. A check in `chat-ui` alone misses calls
made straight to the agent. Whether a participant can ever hold the agent key is still unverified.

## Why two records, and whether that still holds

**Question** (the user): Open WebUI has no split between agent and chat logs. Why does AG-UI keep a chat
session (`chat-ui`'s `/data/sessions/<id>.json`) apart from the agent's run log (`runs.jsonl`), and is that
useful?

**Where the split comes from.** It wasn't designed as a feature:

- **Two processes.** Open WebUI is both the chat app and the thing that calls the model and runs the tools, so
  one stored chat is the whole record. In AG-UI the agent (`pydantic-ai-agent`, port 8100) runs the model and
  the tools, `chat-ui` (CopilotKit) is a separate app in front of it, and the agent keeps no conversation state:
  the client resends the whole history on every run.
- **Build order.** The run log came first (`docs/specs/2026-10-15-agui-frontend-design.md`, *Run log*), when the
  chat had "no persistence" (§6): it was the only record, written where the tool calls happen. Sessions came
  later (`docs/superpowers/specs/2026-10-29-agui-chat-sessions-design.md`) for the sidebar, restoring chats and
  the archive, stored in CopilotKit's own message format so that restoring is `setMessages()`.
- **Explained afterwards.** The sessions spec (§1) then gave each a role: "the run log stays the authoritative
  record of tool calls; the session is the conversation as the participant saw it", joined by `run_id` and
  `thread_id`.

**What is useful about it.** Two things, and neither needs two formats:

- **The participant can't change the run log later.** The session's history comes from the browser; the run log
  is appended by the agent and never rebuilt from that history.
- **It catches requests that skip the chat app.** A call straight to port 8100 never reaches `chat-ui`, but the
  agent logs it.

**What the run log already rebuilds.** Read in order per `thread_id`, each line's `input`, `tool_calls` and
`answer` give much of the conversation, so comparing it with the session file already shows an edited earlier
reply. What it can't give:

- the history each run *received*;
- branches: lines are ordered, but not linked to the point they continued from;
- the order of text and tool calls within a run (`answer` joins all text);
- earlier messages when a run brought several (`input` is the last user message);
- exact content (the three key values redacted, each field cut at 16 KB);
- a run lost to a hard kill, or one the agent refuses before its recorder (its 503s, only in the session).

The session keeps only the latest version of the conversation. So edits and branches fall between the two
records, and the sessions spec's *"the record says what the agent saw, not more"* doesn't hold over time.
Adopting a fix would need a clarification in that spec.

**A cheap step** (unverified, not built): the agent logs per run a hash of the history it received and of what
it returned; the next run in the thread should start with the previous output. That tells continuation, branch
or edit apart on every path, without signatures, but not what changed.

**If designed fresh, one record would do** (unverified, a direction, not decided): the agent writes an
append-only journal, per run the history it received (or a hash of it) and every event it emitted, and the chat
session shrinks to UI state (title, tags, pinned, hidden, deleted) plus the `thread_id`. That is one record like
Open WebUI's, but kept where the participant can't edit it and where every request passes. In this note's terms
it merges B and D into the agent. Still to settle: logging the runs the agent refuses before its recorder, the
storage of every received history, and linking branches to the point they continued from (the hash above can).

## Synthesis

**The one question underneath:** who holds the history the model sees, and can we trust it and record it? Each
hop trusts the history the hop before it sends:

| Hop | Who holds the history | Who trusts it |
|---|---|---|
| Participant → `chat-ui` | the browser (CopilotKit state) | `chat-ui` records it as the session and forwards it |
| `chat-ui` → agent | sent by `chat-ui`, or by anyone with the key straight to port 8100 | the agent runs on it (except system messages) |
| Agent → Anthropic | the agent builds each request | Anthropic: stateless, checks only signed thinking blocks |

Anthropic trusting our agent is fine, because we are the accountable party. The first two hops are the problem:
the participant controls what arrives.

**The "sessions", named apart:**

- **Chat session**: `chat-ui`'s `/data/sessions/<id>.json`, overwritten after each run with the client's latest
  history. It holds one version, the last.
- **Agent**: has no session. Each run is built from the request alone. Its run log is append-only, one line per
  run, without the history the run received.
- **Claude Code's session** is the same pattern one level up: our agent stands where Anthropic stands, stateless
  and trusting its caller.

**Two separate problems:**

1. **Integrity**: is the history what really happened? Fabricated replies or tool results, edited turns, turns
   deleted from the middle, a forged compaction marker.
2. **Record**: does what we store show everything that happened? Abandoned branches and attempts, crashes
   mid-run. Rollback and forking belong here, as branches.

**What each mechanism gives** (A and B are the proposal's options; D is new here; none is decided):

| Mechanism | Integrity | Record | Cost and limits |
|---|---|---|---|
| A. Server-owned history (Open WebUI) | prevents injection through the request | only if the stored copy can't be edited without a trace, which isn't true in Open WebUI | removes a red-teaming technique; goes against how CopilotKit restores chats |
| B. Journal in `chat-ui` | detects and explains each difference | full: branches, attempts, replay of what the agent saw, a crash loses one event | storage and a normalised comparison; misses calls straight to the agent |
| D. Signatures by the agent | detects, statelessly, on every path including port 8100; catches a forged marker exactly | none; a small "latest per conversation" state marks branches | key kept from the participant; CopilotKit must carry the signature (maybe in `messageId`); all unverified |
| Cheap steps (the proposal) | a check against the stored session; marker ids in the run log | none | marker provenance is redundant if D is built |

**How it reconciles:**

- Detection (D) and recording (B) complement each other: signatures in the agent cover every path, and the
  journal in `chat-ui` explains what happened and keeps the branches.
- *Record, don't block*, in both: tampering stays possible as red teaming but never goes unrecorded.
- What this protects is the evaluation, not the data. The model refusing was never the SPE's boundary: egress,
  tool scope and output checks have to hold even when the model is fooled.

**Open:**

- B alone, or B with D? Or both in one journal at the agent (*Why two records*)?
- Can a participant ever hold the agent key? That decides whether D is needed at all.
- Does the canary ladder's scoring need attempt counts per branch?
