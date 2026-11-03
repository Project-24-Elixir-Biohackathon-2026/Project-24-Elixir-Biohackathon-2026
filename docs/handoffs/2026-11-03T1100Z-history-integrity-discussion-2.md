# 2026-11-03: chat history integrity — continue the discussion (2)

An interactive discussion, not a unit: no branch, no PR. Continues
[`2026-11-03T0823Z-history-integrity-discussion.md`](2026-11-03T0823Z-history-integrity-discussion.md). Ended
at the context budget. Start by reading
[`docs/investigations/2026-11-03-history-editing-threat.md`](../investigations/2026-11-03-history-editing-threat.md)
(its *Synthesis* first), then ask the user where they want to pick up.

**The user asked not to touch the proposal** (`docs/proposals/2026-11-03-agui-history-integrity.md`). Write
what the discussion establishes into the investigation note instead, and keep the parent repo's pin as it is.

## Where it stopped

The last exchange: why AG-UI keeps a chat record (`chat-ui`'s session file) apart from the agent's run log, and
whether that still makes sense. The answer given, **not yet in the note** (the user had not said yes):

- The split matches the two problems: *record* belongs at `chat-ui` (the journal, B), *integrity* at the agent,
  the one point every path passes through (signatures, D). Why they are separate: sessions spec §1–2 (the run
  log is "the authoritative record of tool calls; the session is the conversation as the participant saw it",
  joined by `run_id` and `thread_id`) and `pydantic-ai-agent/README.md`, *Run log*.
- What doesn't hold: the spec's *"the record says what the agent saw, not more"*. Neither record keeps the
  history over time (session: last version only; run log: each run's new message only, redacted, 16 KB per
  field), so edits and branches fall between them. Adopting a fix would mean a clarification in the sessions
  spec.
- A cheap step suggested: the agent logs per run a hash of the history it received and of what it returned; the
  next run in the thread should start with the previous output. Continuation, branch or edit, on every path,
  without signatures. Doesn't say what changed.

The user then asked for **an example of an agent log line and a chat (session) file**; it was given in chat,
one conversation of two runs, built from the shapes in `runlog.py` (`RunRecorder.record`) and the sessions spec
§1. Tool names in it were illustrative: the agent's tools come from the sandbox's OpenAPI spec
(`sandbox.py`).

## Open, for the user

- Add the "two records" answer and the hash idea to the note?
- The note's open questions: B alone or B with D; can a participant hold the agent key; does the canary ladder
  need attempt counts per branch.

## Correction after the example

The user pointed out that the run log, read in order per `thread_id`, rebuilds much of the conversation
(each run's `input`, `tool_calls`, `answer`), so comparing that with the session file already shows an edited
earlier reply. The example had said the edit was not visible: too strong. What the log still cannot give: the
history each run *received*; branches (lines are ordered, but not linked to the point they continued from);
the order of text and tool calls within a run (`answer` joins all text); earlier messages when a run brought
several (`input` is the last); exact content (redacted, 16 KB per field); a run lost to a hard kill. Worth adding
to the note with the "two records" answer.
