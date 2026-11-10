# Clarifications

Numbered, append-only: why the design changed after approval.

1. **A contribution has a kind: red, blue, end-to-end or other** (2026-11-10; PR #87, the user in session). A
   red PR adds an attack and shows its harm on a named base (`mitigation: null`); a blue PR adds a mitigation
   measured against attacks already on `main`; end-to-end is the former single kind; other is not an experiment.
   A new threat or path comes only with an attack. `check_experiment.py` reads the kind from the files against
   `--base`; a PR template per kind, opened through `spe-eval pr-body`'s link since GitHub has no PR template
   picker; labels added by the reviewer until CI exists. The end-to-end template gains the *Attack* line and *Idea
   and rationale* (from `BACKLOG.md`). Settled by the agent in PR #87's review round, for the user to overrule there:
   *new* is added or changed against the target ref (the git ref, named apart from the experiment's `base:`); the
   kind is read from every catalogue file the branch makes new, so a lone threat, path, mitigation or injection is
   refused, not *other* (a threat idea with no attack is an issue); a new attack against an unchanged mitigation
   under test is refused (a bypass is red, that mitigation in `base`), and an experiment file alone re-measuring an
   existing mitigation on a new base is blue; an experiment may name any catalogued test; `pr-body` refuses only a
   missing arm or harm, leaving a mitigation's effect to the reviewer; labels are named as the kinds. *Reason:* participants come as red or blue teams and should contribute one
   side without building the whole chain, while every merged piece stays measured. *Amends:* decisions 17 and 18,
   01 (*Tests*, *Experiments*), 05 (*Kinds of contribution*, the path, the checker, the PR, the guides), 07 (*Commands*), slice 6, the glossary,
   approaches, out of scope. *Status:* folded.
