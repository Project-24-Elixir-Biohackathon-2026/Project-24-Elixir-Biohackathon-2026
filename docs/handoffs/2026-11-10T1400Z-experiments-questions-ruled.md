# 2026-11-10: experiments questions ruled


**What this session was.** The unattended follow-up to `docs/handoffs/2026-11-10T1358Z-experiments-questions-open-items.md`:
its five questions to the user, decided where no gate stood in the way (rulings below, each overrulable). On
`main`, no unit; the experiments track (slice 2, PR #86) runs in its own session and was not touched.

## Rulings

1. **"Scenario"**: one glossary row in the experiments spec README (`339aa1e`), mapping the three senses to path,
   arm and test. No clarification (no design change); `threats/TEMPLATE.md` left as is, since asking each scenario
   for its path would be an upstream-facing change for a wording issue.
2. **Inbox #24 and #23 closed** as stale: #84 (the spec) merged 11:17Z today, #64 (ladder slice 5) merged
   2026-11-09.
3. **No parallel track for slice 6's offline part.** Starting it would edit `inputs-for-plan.md` while slice 2's
   PR is open, and its end needs slice 2's `main.tf`; the experiments track takes slice 6 in order. A user *yes*
   reverses this: a re-slicing ruling there, then `methodology next --new`.
4. **Second de.NBI instance**: a gate (outside the standing OK), so not decided; now a *Next* line in `BACKLOG.md`.
5. **OpenTofu persists**: `tofu` v1.10.7 installed in `~/.local/bin` (the home is a virtiofs share that outlives
   the guest), and the machine notes say so (`34dfac7`). PR #86's own `docs/knowledge/opentofu-coder-template-test.md`
   still downloads into the scratchpad; that session may point it at the machine notes, not done from here.

## Not done

- The submodule pin in `biohackathon` was not moved (docs and backlog only).
- The repo is 8 commits behind the machine's methodology (`methodology update`, its own change).
- `methodology worktree --prune` cannot read the forge: the upstream org rejects the fine-grained token's
  lifetime (> 366 days); only worktrees whose remote branch is gone are pruned until the user renews the token.

Nothing waits for a next session from this handoff.
