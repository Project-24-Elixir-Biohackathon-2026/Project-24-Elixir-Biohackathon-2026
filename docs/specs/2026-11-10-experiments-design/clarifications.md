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
   approaches, out of scope. *Status:* superseded by 2 (its kinds, refusals, templates and labels; *Idea and rationale* stays).
2. **A skeleton to test the stack with, not contribution rules** (2026-11-11; the user in session: "the main idea
   is to provide an end to end skeleton … to leverage to test a system end to end", for our stack, changed
   directly on `main` at their word, without a spec PR). The design gives one slot per part of an evaluation
   (threat, path, attack, mitigation, tests, experiment), filled as an idea needs and reused from the catalogue
   otherwise, with the ladder as the worked example. Dropped: contribution kinds (red, blue, end-to-end, other)
   as anything a tool reads or enforces, the checker's comparison with a target ref, its refusals by a branch's
   shape (a lone threat or path, a blue branch adding a test, two experiment files), `pr-body`'s refusals by
   result (a red run with no harm, a missing mitigated arm), the PR template per kind, the new-PR link that picks
   one, and the kind labels. Kept: the checker's checks that an experiment runs and fits the catalogue; one PR
   template whose sections are each *if any*; `pr-body` filling it in; red, blue and both as words in the guides
   for common shapes. A threat or path alone is now a PR reviewed by hand. *Reason:* clarification 1 turned the
   skeleton into a rulebook, and policing what a contribution contains is not what a hackathon participant needs;
   people read the result. *Cost if wrong:* a PR that shows nothing reaches review; the reviewer says so, and
   the kinds can come back as a checker report without refusals. Also recorded: runtime conflicts between
   mitigations are undetected (fork issue #91), in out of scope. *Amends:* the README's decision paragraph,
   decisions 17 and 18, the glossary (*Kind* becomes *Slot*), 01 (*Tests*, *Experiments*), 05 (rewritten), 07
   (*Commands*), approaches (*How a contribution's kind is known*), out of scope, slice 6, clarification 1.
   *Status:* folded.
