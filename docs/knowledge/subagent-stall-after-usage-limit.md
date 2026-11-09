# A subagent stalls after a usage-limit pause

**Symptom** (2026-11-08, slice 1 of leave-running-chat): an implementer subagent running the Playwright rejoin
check hit the account's usage limit mid-run. Once the limit lifted and it resumed, it sat on a Bash call that
never ran: no output and no exit, and the task did not move again.

**Fix:** don't resume it. Start a fresh subagent with the same task (it re-ran the evidence, about 10 minutes of
Playwright), and discard whatever the stalled one half-wrote. To lose less next time:

- Run long Playwright checks (~10 min each) in a subagent, not in the main session, so that a stall costs only
  that subagent.
- Give the run's Bash call an explicit `timeout` (up to 600000 ms), so that a hung call ends with an error
  rather than waiting forever.

Not specific to this repo: carry it to agent-methodology's `tooling-gotchas.md` (`BACKLOG.md`), then drop this
note once `methodology update` brings it in.
