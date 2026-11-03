# `pkill -f` from an agent's shell kills that shell

**Symptom.** A Bash tool call such as `pkill -f "13000:127.0.0.1:3000"; .methodology/shared/claude/next-session.sh <handoff>`
returns only `Exit code 144`, and nothing after `pkill` runs. On 2026-11-03 this skipped `next-session.sh`, so the
chained session sat idle for six hours while its last message said the next session had started.

**Why.** The Bash tool runs each call as `zsh -c '… <the whole command text> …'`, so `pkill -f`'s pattern also
matches the tool's own shell (`pgrep -af "13000:127.0.0.1"` lists it).

**Fix.** Keep the pattern from matching itself: `pkill -f "1[3]000:127.0.0.1:3000"`, or kill a recorded PID. Run
`next-session.sh` alone in its own tool call, and stop only after its "The next session (N of M) starts…" line.
Reported upstream as agent-methodology#37; drop this note once `tooling-gotchas.md` carries it.
