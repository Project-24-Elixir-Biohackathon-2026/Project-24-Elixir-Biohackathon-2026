# A reasoning model spends `max_tokens` on thinking first

**Symptom.** On de.NBI (`qwen3.8-27b`), every `POST /title` answered 422 and the run log had
`{"type": "title", "title": null, "usage": {"output_tokens": 64}, "error": "the model returned an empty title"}`
(2026-11-04). The chat kept the first message as the session's title.

**Cause.** qwen reasons before it answers, and the reasoning counts against `max_tokens`. A title request spent 124
reasoning tokens before its 13-token JSON answer (one direct request, `max_tokens: 1024`, `usage.completion_tokens_details.reasoning_tokens`),
so a cap of 64 ended the response inside the reasoning, with no text part.

**Fix.** `title.max_tokens` defaults to 1024. Any other small output cap in front of a reasoning model needs the same
headroom; `compaction.summary_max_tokens` (4096) has it.

Check a cap without the agent: from a de.NBI VM, `curl …/v1/chat/completions` with the prompt and `max_tokens`, and
read `usage.completion_tokens_details.reasoning_tokens` and whether `message.content` is empty.
