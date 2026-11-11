# Using the skeleton, and contributing back

## A skeleton, not a rulebook

What this design gives a participant is a skeleton for testing our stack end to end: one slot per part of an
evaluation, each a file of a fixed shape (01), wired together so that one command builds and measures them (03).

| Slot | File | Filled when |
|---|---|---|
| Threat | `threats/TM-NNN-<slug>.md` | the harm is not in the catalogue yet |
| Path | `paths/P<n>-<slug>.md` | the route is not one of P1–P4 |
| Attack | a test prompt in `tests/experiments/<name>.yaml`, or a planted injection (01, *Attacks*) | the existing attacks do not make the threat happen through the path |
| Mitigation | its Ansible change behind `spe_mitigate_<id>`, and `mitigations/<id>.yml` | there is a control to measure |
| Tests | `tests/experiments/<name>.yaml`, or ids of tests already in the catalogue | always: the experiment names the tests it runs |
| Experiment | `experiments/<name>.yml` | always: it ties the slots together |

A participant fills the slots their idea needs and reuses the rest from the catalogue. The ladder (06) is the
worked example: every slot filled, for four experiments. Common shapes, as words for the guides and not checked
by anything:

- **an attack** against an existing build: `mitigation: null`, `base` naming the build it breaks (e.g. `[L1, L2]`:
  "breaks `ladder-l2`"); the baseline arm shows the harm;
- **a mitigation** against existing attacks: the experiment's `tests` and `injections` name attacks already in the
  catalogue; both arms show its effect;
- **both**, an attack and the mitigation against it;
- **a description only**, a threat or path with no attack yet, or anything that is not an experiment (a fix, a
  doc, a tool), reviewed by hand.

What any of them shows is the run's result, read by people: the counts of each arm, in the PR. Nothing refuses a
contribution for its shape or for what its run showed; a mitigation that does not help is a result too.

## The path

1. **A workspace from `spe-experiments`**, with an existing experiment: `ladder-l0` (the default, the plain build) or
   one to build on. Nothing new is needed to create it; the participant's own experiment is written inside it.
2. **Fill the skeleton**, usually by asking the workspace's coding agent (Coder Agents, which follows
   `platform/instance/workspace/AGENTS.md`), or by hand:
   - `spe-eval new <name> [--from <experiment>]` writes every slot's file with `TODO`s (07); the participant deletes
     the ones the idea does not need;
   - the threat (`threats/`, from `TEMPLATE.md`) and the path (`paths/`), if new;
   - the attack, if the existing ones do not make the threat happen through the path: a prompt is a test (below);
     a planted one is an injection, a payload file and its `fixtures.json` entry on `spe_inject_<id>` (default
     off), plus a planting role guarded by it for a new surface (01, *Attacks*);
   - the mitigation, if any: its Ansible change guarded by `spe_mitigate_<id>` (default off), and
     `mitigations/<id>.yml`;
   - its tests, `tests/experiments/<name>.yaml`, or ids of existing tests in the experiment's `tests`;
   - the experiment, `experiments/<name>.yml`, with its `experiment:` block and `parameters.experiment: <name>`.
3. **Try it live**: `spe-eval arm <name> mitigated` to apply it (`baseline` when it has no mitigation), chat with
   the agent; then `spe-eval run` for the arms, read with `spe-eval results` or in **Evaluations**.
4. **Check**: `python3 check_experiment.py <name>`. (Every step has a command for a coding agent: 07.)
5. **Build it fresh** (when the change acts only at creation, or to confirm a clean build): push
   `experiment/<name>`; the portal makes `spe-x-<name>`, whose form already offers the new mitigation and experiment.
6. **Open a PR** with the body `spe-eval pr-body <name>` prints (*The PR*). Merged upstream, the experiment and its
   mitigation appear on `spe-experiments`' form for everyone within minutes.

The portal follows upstream's `main` and makes branch templates from upstream branches, so step 5 needs push
access there and step 6 is an upstream PR.

## `check_experiment.py [<name>]`

At the repository root, beside `validate.py`, standard library plus PyYAML, offline, under a minute. It checks that
an experiment will run and that its files fit the catalogue: what would otherwise fail in the middle of a run, or
break another experiment. It does not judge what a contribution should contain. Without `<name>` it checks every
experiment in `experiments/`.

- the experiment file exists, has an `experiment:` block, and sets `parameters.experiment` to its own stem;
- its threat, paths, mitigation, base mitigations, injections and test ids resolve to files and tests;
- each listed injection's entry is complete, its payload file exists and names its `target_file`, its
  `canary_file` is a canary file the experiment's `canaries` parameter plants, its surface has location keys and
  its action a detector, and its switch defaults to `false`;
- `validate.py` passes (threats, paths, mitigations);
- each named mitigation's `off` equals the Ansible defaults, and no key it sets is set by another mitigation's `on`;
  `requires` and `conflicts` hold for base plus the one under test;
- each test's labels resolve (the catalogue lint) and its Python assertions name real functions;
- its `parameters` keys are parameters of the new template's `main.tf`, and its `vars` set no key a mitigation sets.

Each problem names the file and the id. Its unit tests cover one problem each. `--json` gives the same as a list.

The coding agent runs it as the last step, a reviewer runs it on the branch, and CI runs it once the repository
has workflows. Whether the attack or the mitigation *works* is the result's job, below.

## The PR

One PR template, `.github/pull_request_template.md`, with a section per slot, each marked *if any*: GitHub applies
it to every PR opened the usual way, so no link or picker is needed.

- **`spe-eval pr-body [<name>] [--run <id>]`** runs the checker, then prints a title and the template filled in
  from the files, the run's counts and the checker's output, slots the experiment does not fill left out. It
  refuses nothing about the result: an experiment with no run gets a *Result* placeholder. The body can be pasted
  into the PR or passed to `gh pr create --title … --body-file -`.

```markdown
## Experiment: <name>

**Threat:** TM-NNN (new / existing): <one line>
**Paths:** P<n> (new / existing): <the route>
**Attack:** <a prompt test, or injection `<id>` (new / existing): its surface and action> (if any)
**Mitigation:** `<id>` (`spe_mitigate_<id>`): <what it changes, where> (if any)
**Base:** <base mitigations: the build it runs on>
**Experiment file:** `experiments/<name>.yml`

### Idea and rationale
<why this attack or mitigation, what was tried, known limits>

### Result
Model: <provider / model>   Repeat: <n>
<`matrix.py counts` of each arm, or the rendered table: baseline vs mitigated>
Utility tests pass with the mitigation on: yes / no (if a mitigation)

### Checks
`python3 check_experiment.py <name>`: <output>
```

A PR that is not an experiment deletes the template's text and says what, why, and how it was checked.

*Idea and rationale* is left as a placeholder for the participant: the reasoning goes in the PR, the lasting
explanation in the experiment's `description` and the threat and path files (`CONTRIBUTING.md` says so).

The result is `matrix.py counts` output: labels and counts only, never an answer or a token, so it can be posted.
It is one step, read against the cumulative ladder view (`matrix.py render` over the controller-side runs, committed
under `docs/results/`); a contribution edits neither `matrix.py` (its labels come from the files, decision 3) nor
that view. `CONTRIBUTING.md` says the same.
A reviewer who wants to see it reproduced creates a workspace from `spe-x-<name>` and runs `spe-eval run`.

## The guides

- `CONTRIBUTING.md` (new, root): how to use the skeleton and contribute back, for people. It opens with the slots
  (the table above) and the ladder as the example, then the path, and points to the checker and the PR template.
- `platform/instance/workspace/AGENTS.md`, a new section *Contributing an experiment*: the same steps for the
  coding agent, including that a mitigation is a switch with a default of off, and that it runs the checker and
  reports its output before pushing.
- `threats/TEMPLATE.md`'s *Detective* section points to experiments for the promptfoo side.
