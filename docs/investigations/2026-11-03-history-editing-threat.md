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
- **The model refusing was never the security boundary.** If the only thing between a participant and a secret
  is the model saying no, that boundary already falls to an ordinary jailbreak; history editing just makes it
  easier. In an SPE the real controls are in the environment: what the agent's tools can reach, where network
  traffic can go, and checks on what leaves.

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
