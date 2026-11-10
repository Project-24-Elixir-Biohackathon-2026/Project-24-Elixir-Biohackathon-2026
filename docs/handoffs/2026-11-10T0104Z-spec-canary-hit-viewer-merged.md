# 2026-11-10: spec canary hit viewer merged

**Unit done:** the spec, `docs/specs/2026-11-10-canary-hit-viewer.md`, merged as `dc64a92` (PR #74, squash).
One local review round (correctness, methodology): 18 findings, all fixed before the merge (the PR's review
comment lists them). Approved by the user ahead of time, in words relayed by the session that started this one
("can you please tell it to self approve the spec and proceed with its recommendation"); the approval comment
on #74 quotes them. The proposal's open questions are settled in the spec's *Rulings on the open questions*,
each with its cost if wrong.

**Next unit:** the plan, branch `plan/canary-hit-viewer`, written with `superpowers:writing-plans` into
`docs/superpowers/plans/2026-11-10-canary-hit-viewer/` (a directory: more than one slice). The user asked the
track to continue without stopping for approval (plan, then slices); the floor still holds (no paid model calls
beyond a one-shot check, one de.NBI instance at most, no canary values or secrets committed).

**For the plan:**
- Start from the spec's *Inputs for the plan*: four unverified claims to check first (volume host paths and
  passwordless `sudo` on a Coder instance; whether Open WebUI's chats reach `runs.jsonl`; the AG-UI event types
  in a real journal; whether the Coder template sets an age recipient) and the build order.
- The early output (the archive scan rendered as the participant page, on a real `/data-share/runs/` run) is
  the first slice's output; it needs the portal VM's archive, so check access to it before planning that slice
  as runnable here.
- `canarymatch.py` lives in `platform/report/`; on the fork `metrics.py` moves onto it. The spec is meant to
  port upstream: keep fork-only links out of it and out of `platform/` code.
- The deferred inline chat marks and Open WebUI toast are in `BACKLOG.md` (*Unscheduled*).

**Still to do outside this repo:** move the `biohackathon` pin to `dc64a92` (or to this handoff's commit).

**Gotcha seen:** `gh pr ready/edit/merge` still fail on this fork; the REST/GraphQL forms in
`docs/knowledge/gh-pr-create-token.md` worked for every step (body PATCH, ready mutation, label, squash merge).
