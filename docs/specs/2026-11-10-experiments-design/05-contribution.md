# Contributing

## Kinds of contribution

Participants come to the stack from either side: some break it (red team), some harden it (blue team), some do
both. So a contribution is one of four kinds. The three measured kinds are all experiments, differing in what the
PR adds; each is justified by the evaluation pipeline (`spe-eval run`, the checker), never by prose alone.

| Kind | Adds | Must not add | The experiment | Its evidence |
|---|---|---|---|---|
| **red** (attack) | at least one attack: a planted injection or a test prompt, with its tests; threat and path files when new | a mitigation | `mitigation: null`; `base` names the build it attacks (e.g. `[L1, L2]`: "breaks `ladder-l2`") | the baseline arm: a test the experiment runs records the harm (a security metric fails; `injection.followed` included, for a PR that adds only an injection) |
| **blue** (mitigation) | one mitigation (its Ansible change behind `spe_mitigate_<id>`, `mitigations/<id>.yml`) | an attack, a threat or a path | the mitigation under test, new or changed; `injections` and `tests` name attacks already on the target ref (the ones on the paths it `closes`) | both arms: baseline vs mitigated, the utility tests passing with it on |
| **end-to-end** | an attack and a mitigation against it, threat and path files when new | | as in 01 | both arms, as blue |
| **other** | anything that is not an experiment: a fix, a doc, a tool | an `experiments/*.yml`, or any threat, path, mitigation, injection or test | none | review by hand |

- **A new threat or path comes with an attack.** It is a description; what makes it real on the stack is an
  attack that makes it happen (01, *Attacks*). So it arrives in a red or end-to-end PR, never alone; an idea
  without an attack yet is an issue, not a PR.
- **The kind is read from the files, not declared.** `check_experiment.py` compares the branch with the
  **target ref**, the branch the PR targets (`--base`, default `origin/main`; not the experiment's `base:`
  mitigations). *New* means added or changed against it, so improving L1 makes its mitigation new. It reads
  every catalogue file the branch makes new (threats, paths, mitigations, injections, tests) and the experiment
  file:

  | New on the branch | Experiment's `mitigation` | Kind |
  |---|---|---|
  | an attack (an injection or a test), no mitigation | `null` | red |
  | an attack, and the mitigation under test | new | end-to-end |
  | no attack | new, or an existing one on a new `base` (an interaction) | blue |
  | no catalogue file and no experiment file | | other |

  It prints the kind first and applies that kind's checks (*`check_experiment.py`*). A branch that fits no row is
  refused with what to add or remove: a new attack against an unchanged mitigation under test (to show a bypass,
  put that mitigation in `base` with `mitigation: null`: red), a new threat or path with no attack, a new
  catalogue file with no experiment file, a blue branch adding a test, an experiment that adds nothing (`null`,
  no new attack), two experiment files. Since the files decide, the participant, the reviewer and a later CI get
  the same answer.
- **The evidence is checked where it lives.** The checker stays offline and structural; the result is the run's.
  `spe-eval pr-body` refuses a red PR whose latest run recorded no harm (nothing was shown) and a blue or
  end-to-end PR with no mitigated arm, and puts the counts in the body; the reviewer reproduces them from
  `spe-x-<name>` (*The PR*).

## The path

1. **A workspace from `spe-experiments`**, with an existing experiment: `ladder-l0` (the default, the plain build) or
   one to build on. Nothing new is needed to create it; the participant's own experiment is written inside it.
2. **Build the experiment**, usually by asking the workspace's coding agent (Coder Agents, which follows
   `platform/instance/workspace/AGENTS.md`), or by hand:
   - `spe-eval new <name> [--kind red|blue|end-to-end]` (default `end-to-end`) writes the skeleton of what the kind needs from the list below
     (07); `--kind` only picks the skeleton, so a red start that grows a mitigation becomes end-to-end;
   - the threat (`threats/`, from `TEMPLATE.md`) and the path (`paths/`), if new (red, end-to-end);
   - the attack (red, end-to-end), if the existing ones do not make the threat happen through the path: a prompt
     is a test (below); a planted one is an injection, a payload file and its `fixtures.json` entry on
     `spe_inject_<id>` (default off), plus a planting role guarded by it for a new surface (01, *Attacks*);
   - the mitigation (blue, end-to-end): its Ansible change guarded by `spe_mitigate_<id>` (default off), and
     `mitigations/<id>.yml`;
   - its tests, `tests/experiments/<name>.yaml` (red, end-to-end; a blue experiment names existing tests, which
     `new --kind blue --path P<n>` fills in from the catalogue);
   - the experiment, `experiments/<name>.yml`, with its `experiment:` block and `parameters.experiment: <name>`.
3. **Try it live**: `spe-eval arm <name> mitigated` to apply it (`baseline` for red), chat with the agent; then
   `spe-eval run` for the arms, read with `spe-eval results` or in **Evaluations**.
4. **Check**: `python3 check_experiment.py <name>`, which names the kind. (Every step has a command for a coding
   agent: 07.)
5. **Build it fresh** (when the change acts only at creation, or to confirm a clean build): push
   `experiment/<name>`; the portal makes `spe-x-<name>`, whose form already offers the new mitigation and experiment.
6. **Open a PR** through `spe-eval pr-body <name>`: it prints the title, the body from the kind's PR template, and
   the new-PR link that selects that template (*The PR*). Merged upstream, the experiment and its mitigation
   appear on `spe-experiments`' form for everyone within minutes.

The portal follows upstream's `main` and makes branch templates from upstream branches, so step 5 needs push
access there and step 6 is an upstream PR.

## `check_experiment.py [<name>]`

At the repository root, beside `validate.py`, standard library plus PyYAML, offline, under a minute. It checks the
experiment's structure, not its result. Without `<name>` it takes the one experiment file the branch adds or
changes against the target ref; with none, the kind is *other* if the branch makes no catalogue file new (the
only check then), and refused otherwise.

It first prints the kind (*Kinds of contribution*) and what decided it, e.g. `kind: red (new: injection
drs-desc-v2, test leak-via-drs; mitigation under test: none)`. Comparing with the target ref reads git refs only, so it
stays offline; `spe-eval new` and `pr-body` run `git fetch` first so the base is current, and a reviewer fetches
before running it. Then, for every measured kind:

- the experiment file exists, has an `experiment:` block, and sets `parameters.experiment` to its own stem;
- its threat, paths, mitigation, base mitigations, injections and test ids resolve to files and tests;
- each listed injection's entry is complete, its payload file exists and names its `target_file`, its
  `canary_file` is a canary file the experiment's `canaries` parameter plants, its surface has location keys and
  its action a detector, and its switch defaults to `false`;
- `validate.py` passes (threats, paths, mitigations);
- each named mitigation's `off` equals the Ansible defaults, and no key it sets is set by another mitigation's `on`;
  `requires` and `conflicts` hold for base plus the one under test;
- each test's labels resolve (the catalogue lint) and its Python assertions name real functions;
- its `parameters` keys are parameters of the new template's `main.tf`, and its `vars` set no key a mitigation sets;
- the branch adds or changes one experiment file, and fits its kind: a new threat or path comes with a new attack;
  red adds no mitigation file and its experiment has `mitigation: null`; blue adds no injection, test, threat or
  path, and its experiment's injections and tests are all on the target ref.

Each refusal names the file and the id. Its unit tests cover one refusal each, and each kind on a fixture branch.
`--json` adds `kind` and what decided it. `--list-checks [--kind <kind>]` prints one line per check above that
applies to the kind, which that kind's PR template's *Checks* list repeats (a test compares them).

It is the gate of a contribution: the coding agent runs it as the last step, the participant pastes its output into
the PR, a reviewer runs it on the branch, and CI runs it once the repository has workflows. Whether the attack or
the mitigation *works* is the result's job, below.

## The PR

GitHub has no picker for PR templates: a PR opened the usual way gets the default template, and another is chosen
only by `?template=<file>` on the new-PR link. So a participant opens the PR through `spe-eval pr-body`, which
picks the template from the kind; `CONTRIBUTING.md` and the workspace guide say to do it that way.

- **`spe-eval pr-body [<name>] [--run <id>]`** runs the checker, then prints three things: a title with the
  kind's prefix (`[red] <one line>`, `[blue] …`, `[end-to-end] …`, `[other] …`), the body (the kind's template filled in
  from the files, the run's counts and the checker's output), and the new-PR link
  (`https://github.com/<target>/compare/main...<head>?quick_pull=1&template=<kind>.md`), built from the remote
  the PR targets (`upstream` when it exists, else `origin`): `<head>` is `<branch>` when the branch is pushed
  there, `<owner>:<branch>` when it is pushed to another remote (a fork). It refuses, exit 1, a red experiment whose
  latest run recorded no harm, and a blue or end-to-end one with no mitigated arm. The body can also go to
  `gh pr create --title … --body-file -`.
- **Templates**, in `.github/PULL_REQUEST_TEMPLATE/`: `red.md`, `blue.md`, `end-to-end.md` and
  `other.md`. Each lists only its kind's files, result and checks.
- **The default**, `.github/pull_request_template.md`, is for a PR opened by hand: it asks which kind this is and
  says to run `spe-eval pr-body`, or to add `&template=<kind>.md` to the compare page's URL and reload. It cannot
  hold working links (the text knows no branch, and a link in a created PR resolves against the PR). Whether
  GitHub still applies it beside the template directory is untried: slice 6 checks on the fork, and if not,
  `CONTRIBUTING.md`'s same URL pattern is the by-hand route.
- **Labels**, one per kind and named as it (`red`, `blue`, `end-to-end`, `other`), created once on upstream by a maintainer. A PR
  template cannot set labels, and an author from a fork usually cannot add them, so the reviewer adds the one the
  checker names. A wrong template does no harm: the checker's kind wins, and the reviewer labels by it.

`end-to-end.md`:

```markdown
## Experiment: <name>

**Threat:** TM-NNN (new / existing): <one line>
**Paths:** P<n> (new / existing): <the route>
**Attack:** <a prompt test, or injection `<id>` (new / existing): its surface and action>
**Mitigation:** `<id>` (`spe_mitigate_<id>`): <what it changes, where>
**Experiment file:** `experiments/<name>.yml`

### Files
- [ ] threat and path files, if new (`validate.py` passes)
- [ ] the attack: a prompt test, or a payload file and its `fixtures.json` entry on `spe_inject_<id>`, default
      off, plus any planting role (new surface) or detector in `metrics.py` (new action)
- [ ] `mitigations/<id>.yml`; the Ansible change behind `spe_mitigate_<id>`, default off
- [ ] `platform/promptfoo-evals/tests/experiments/<name>.yaml`
- [ ] `experiments/<name>.yml`, with its `experiment:` block

### Idea and rationale
<why this attack and this mitigation, what was tried, known limits>

### Result
Model: <provider / model>   Repeat: <n>
<`matrix.py counts` of each arm, or the rendered table: baseline vs mitigated>
Utility tests pass with the mitigation on: yes / no

### Checks
`python3 check_experiment.py <name>`: <output>
<one checkbox per line of `check_experiment.py --list-checks --kind end-to-end`>
```

`red.md` has the same header without *Mitigation* and with **Attacks build:** `<base mitigations>` (the ladder
level or experiment it breaks); its *Files* drop the mitigation; its *Result* is the baseline arm's counts and the
tests that recorded the harm. `blue.md` has no threat or path line and names, under **Against:**, the existing
injections and tests it is measured on; its *Files* are the mitigation and the experiment file; its *Result* is
both arms, as end-to-end. Every measured template keeps *Idea and rationale*, which `pr-body` leaves as a
placeholder for the participant: the reasoning goes in the PR, the lasting explanation in the experiment's
`description` and the threat and path files (`CONTRIBUTING.md` says so). `other.md` is free text: what, why, and
how it was checked.

The result is `matrix.py counts` output: labels and counts only, never an answer or a token, so it can be posted.
It is one step, read against the cumulative ladder view (`matrix.py render` over the controller-side runs, committed
under `docs/results/`); a contribution edits neither `matrix.py` (its labels come from the files, decision 3) nor
that view. `CONTRIBUTING.md` says the same.
A reviewer who wants to see it reproduced creates a workspace from `spe-x-<name>` and runs `spe-eval run`.

## The guides

- `CONTRIBUTING.md` (new, root): how to contribute, for people. It opens with the four kinds (the table above, in
  its readers' terms: break it, harden it, both, or something else), then the path for each, and says to open the
  PR with `spe-eval pr-body` because GitHub cannot choose the template; it points to the templates and the
  checker.
- `platform/instance/workspace/AGENTS.md`, a new section *Contributing an experiment*: the same steps for the
  coding agent, per kind, including that a mitigation is a switch with a default of off, that a new threat or path
  needs an attack, and that it runs the checker and reports its output (the kind first) before pushing.
- `threats/TEMPLATE.md`'s *Detective* section points to experiments for the promptfoo side.
