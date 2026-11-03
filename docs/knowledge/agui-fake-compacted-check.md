# The fake agent can't tell a fresh compaction by the request's shape

**Symptom.** `fake_agent.py` sent a history with a marker from an earlier run, then a new `compact`
(slice 1 of the compaction command plan, task 3's hand check): `grep -c spe-compaction-` printed 0, the reply
was "Turn 1: the command ran. The conversation was compacted." without compacting.

**Cause.** `build_sent` cuts at the latest marker and merges the first request after it into the head, so the
model gets `[system, frame(summary), latest prompt]`, the same as `compacted()` sends right after a fresh
compaction within the run. No test on the messages alone separates the two.

**Fix.** `summarise()` ends each automatic summary with `[summary <hex>]` and adds it to `FRESH`; `scripted`
answers "compacted" only for a head frame holding a nonce still in `FRESH`, and discards it. Check:

    curl … -d '{…"messages":[{"id":"u1","role":"user","content":"compact"},{"id":"spe-compaction-1","role":"assistant","content":"S"},{"id":"u2","role":"user","content":"compact"}]}' | grep -c spe-compaction-

prints non-zero (the full command: the plan's `slice-1-agent.md`, task 3, step 2).
