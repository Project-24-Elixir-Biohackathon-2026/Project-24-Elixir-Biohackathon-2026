# Contributing an experiment

## The path

1. **A workspace from `spe-experiments`**, with an existing experiment: `ladder-l0` (the default, the plain build) or
   one to build on. Nothing new is needed to create it; the participant's own experiment is written inside it.
2. **Build the experiment**, usually by asking the workspace's coding agent (Coder Agents, which follows
   `platform/instance/workspace/AGENTS.md`), or by hand:
   - `spe-eval new <name>` writes the skeleton of what follows (07);
   - the threat (`threats/`, from `TEMPLATE.md`) and the path (`paths/`), if new;
   - the attack, if the existing ones do not make the threat happen through the path: a prompt is a test (below);
     a planted one is an injection, a payload file and its `fixtures.json` entry on `spe_inject_<id>` (default
     off), plus a planting role guarded by it for a new surface (01, *Attacks*);
   - the mitigation: its Ansible change guarded by `spe_mitigate_<id>` (default off), and `mitigations/<id>.yml`;
   - its tests, `tests/experiments/<name>.yaml`;
   - the experiment, `experiments/<name>.yml`, with its `experiment:` block and `parameters.experiment: <name>`.
3. **Try it live**: `spe-eval arm <name> mitigated` to apply it, chat with the agent; then `spe-eval run` for the two
   arms, read with `spe-eval results` or in **Evaluations**.
4. **Check**: `python3 check_experiment.py <name>`. (Every step has a command for a coding agent: 07.)
5. **Build it fresh** (when the change acts only at creation, or to confirm a clean build): push
   `experiment/<name>`; the portal makes `spe-x-<name>`, whose form already offers the new mitigation and experiment.
6. **Open a PR** from the branch, with the experiment PR template. Merged upstream, the experiment and its
   mitigation appear on `spe-experiments`' form for everyone within minutes.

The portal follows upstream's `main` and makes branch templates from upstream branches, so step 5 needs push
access there and step 6 is an upstream PR.

## `check_experiment.py <name>`

At the repository root, beside `validate.py`, standard library plus PyYAML, offline, under a minute. It checks the
experiment's structure, not its result:

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

Each refusal names the file and the id. Its unit tests cover one refusal each. `--list-checks` prints one line per
check above, which the PR template's *Checks* list repeats (a test compares them).

It is the gate of a contribution: the coding agent runs it as the last step, the participant pastes its output into
the PR, a reviewer runs it on the branch, and CI runs it once the repository has workflows. Whether the mitigation
*works* is the result's job, below.

## The PR

`.github/PULL_REQUEST_TEMPLATE/experiment.md`, chosen with `?template=experiment.md` on the new-PR link the
workspace guide gives:

```markdown
## Experiment: <name>

**Threat:** TM-NNN (new / existing): <one line>
**Paths:** P<n> (new / existing): <the route>
**Mitigation:** `<id>` (`spe_mitigate_<id>`): <what it changes, where>
**Experiment file:** `experiments/<name>.yml`

### Files
- [ ] threat and path files, if new (`validate.py` passes)
- [ ] `mitigations/<id>.yml`; the Ansible change behind `spe_mitigate_<id>`, default off
- [ ] `platform/promptfoo-evals/tests/experiments/<name>.yaml`
- [ ] `experiments/<name>.yml`, with its `experiment:` block

### Result
Model: <provider / model>   Repeat: <n>
<`matrix.py counts` of each arm, or the rendered table: baseline vs mitigated>
Utility tests pass with the mitigation on: yes / no

### Checks
`python3 check_experiment.py <name>`: <output>
- [ ] the experiment file has an `experiment:` block and sets `parameters.experiment` to its own name
- [ ] its threat, paths, mitigation, base mitigations, injections and test ids resolve
- [ ] each injection's entry is complete, its payload names its target, its canary file is planted, its switch defaults off
- [ ] `validate.py` passes (threats, paths, mitigations)
- [ ] each mitigation's `off` equals the Ansible defaults, no key is set by another mitigation's `on`; `requires` and `conflicts` hold
- [ ] each test's labels resolve and its Python assertions name real functions
- [ ] its `parameters` are the template's, and its `vars` set no key a mitigation sets
```

The result is `matrix.py counts` output: labels and counts only, never an answer or a token, so it can be posted.
It is one step, read against the cumulative ladder view (`matrix.py render` over the controller-side runs, committed
under `docs/results/`); a contribution edits neither `matrix.py` (its labels come from the files, decision 3) nor
that view. `CONTRIBUTING.md` says the same.
A reviewer who wants to see it reproduced creates a workspace from `spe-x-<name>` and runs `spe-eval run`.

## The guides

- `CONTRIBUTING.md` (new, root): how to contribute an experiment, for people; points to the PR template and the
  checker.
- `platform/instance/workspace/AGENTS.md`, a new section *Contributing an experiment*: the same steps for the
  coding agent, including that a mitigation is a switch with a default of off, and that it runs the checker and
  reports its output before pushing.
- `threats/TEMPLATE.md`'s *Detective* section points to experiments for the promptfoo side.
