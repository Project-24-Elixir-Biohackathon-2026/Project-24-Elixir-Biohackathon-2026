# 2026-11-10: experiments questions open items

**What this session was.** Questions from the user about the merged experiments spec
(`docs/specs/2026-11-10-experiments-design/`), on `main`, no unit of its own. The experiments track itself runs in
its own session (slice 2, `impl/experiments-2-template`, PR #86, its handoff
`docs/handoffs/2026-11-10T1352Z-experiments-slice-2-mid.md`); this handoff does not touch it.

**Done (on `main`, pushed):** `BACKLOG.md` *Unscheduled* gained four experiments items: the PR template's missing
attack line and rationale section, a reviewer check for contributed planting roles and detectors, the Coder form's
option descriptions / `doc:` / template README (`7cb67c3`), and real multi-turn attacks (`c7e80d4`, corrected in
`e0a01fe`: the attacker LLM runs on de.NBI, not Anthropic). The stale *Next* item asking to approve the spec was
dropped. The submodule pin in `biohackathon` was not moved for these.

## Waiting on the user (asked, not answered)

1. **"Scenario" vs "path".** "Scenario" means three things: a TM file's *Attack Scenarios* (prose, ≈ path +
   attack), knowledge 0005/0007/0011's "scenario profiles" (≈ an experiment's build), and 0017's scenario (≈ an
   experiment's tests + injection, labelled with threat and paths). Proposed: one glossary line in the spec README,
   and optionally `threats/TEMPLATE.md` asking each scenario to name its path. Direct commit or backlog line?
2. **Inbox #24 and #23 look stale**: #24 asks to approve the spec (merged as #84); #23 asks for a de.NBI LLM key for
   ladder slice 5 (the ladder finished since). Close both, with the reason?
3. **A parallel track for slice 6's offline part** (`check_experiment.py`, PR template with the backlog items,
   `CONTRIBUTING.md`): needs only slice 1's files and, at the end, slice 2's `main.tf` parameters; no de.NBI.
   Needs a re-slicing ruling in `inputs-for-plan.md` and `methodology next --new`. Start it?
4. **de.NBI is one VM, `denbi-agui-01`, `spe_provision: existing`**: builds rewrite its stack, never the VM. Parallel
   tracks needing de.NBI would clobber each other; a second instance (new VM, or a second stack on the host,
   unverified) needs the user's OK. The user asked; no decision yet.
5. **OpenTofu stays installed**: the user wants it to persist. Proper fix is the `opentofu` package in nixed's guest
   config (another repository); a quick one is the release binary in `~/.local/bin` if the guest's home persists
   (unchecked), with `docs/knowledge/opentofu-coder-template-test.md` (on PR #86's branch) updated to point there.
