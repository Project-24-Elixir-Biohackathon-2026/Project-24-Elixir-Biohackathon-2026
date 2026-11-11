# Contributing an experiment

Threats, paths and mitigations are not fixed: you can measure your own idea against the stack and
send it back as a pull request. This is how.

## A skeleton, not a rulebook

An **experiment** (`experiments/<name>.yml`) is a threat and the path it takes, measured with no
mitigation on (the **baseline** arm) against the one mitigation under test, if any (the
**mitigated** arm). It ties together one slot per part of the idea:

| Slot | File | Filled when |
|---|---|---|
| Threat | `threats/TM-NNN-<slug>.md` | the harm is not in the catalog yet |
| Path | `paths/P<n>-<slug>.md` | the route is not one of the existing paths |
| Attack | a test prompt in `tests/experiments/<name>.yaml`, or a planted injection | the existing attacks do not make the threat happen through the path |
| Mitigation | an Ansible switch (`spe_mitigate_<id>`, default off) and `mitigations/<id>.yml` | there is a control to measure |
| Tests | `tests/experiments/<name>.yaml`, or ids of tests already in the catalog | always: the experiment names the tests it runs |
| Experiment | `experiments/<name>.yml` | always: it ties the slots together |

You fill only the slots your idea needs and reuse the rest from the catalog. The hardening
ladder (`experiments/ladder-l0.yml` … `ladder-l3.yml`, indexed in `experiments/README.md`) is the
worked example: every slot filled, level by level, from the plain build (`ladder-l0`) up through
TRS read-only, data tiers and egress control. Common shapes:

- **an attack** against an existing build: no mitigation under test, naming the build it breaks;
  the baseline arm alone shows the harm;
- **a mitigation** against existing attacks: your experiment's `tests` and `injections` name
  attacks already in the catalog; both arms show its effect;
- **both**, an attack and the mitigation against it;
- **a description only** -- a threat or path with no attack yet, or any change that is not an
  experiment (a fix, a doc, a tool) -- reviewed by hand, no checker involved.

Nothing refuses a contribution for its shape, or for what its run showed: a mitigation that turns
out not to help is a result too.

## The path

1. **Start a workspace** from the `spe-experiments` template, with an existing experiment
   (`ladder-l0`, the plain build, or one to build on). Your own experiment is written inside it.
2. **Fill the skeleton**, by hand or by asking the workspace's coding agent:
   `spe-eval new <name> [--threat TM-NNN] [--path P<n>] [--injection <surface>] [--from <experiment>]`
   writes every slot's file with `TODO`s; delete the files a slot your idea does not need (the
   command's own output says how).
3. **Try it live**: `spe-eval arm <name> mitigated` to apply your build (`baseline` for a
   one-arm experiment), then chat with the agent; `spe-eval run` to measure both arms, read with
   `spe-eval results` or in **Evaluations**.
4. **Check**: `python3 check_experiment.py <name>` (PyYAML installed on the VM already; elsewhere,
   `uv run --with pyyaml python check_experiment.py <name>` needs no install). Run it after every
   edit (`spe-eval test <name>` does this plus the evaluation suite's own offline tests); it must
   exit 0 before you push.
5. **Build it fresh**, to confirm a clean build or try a change that only takes effect at
   creation: push `experiment/<name>`; a workspace from the branch template `spe-x-<name>`
   already offers your new mitigation and experiment on its form.
6. **Open a pull request** with the body `spe-eval pr-body <name>` prints: it fills in
   `.github/pull_request_template.md` from your files, the run's counts, and the checker's own
   output. Once it is merged, your experiment and mitigation appear on the `spe-experiments`
   form for everyone within minutes.

The portal follows upstream's own `main` and makes branch templates from upstream branches only,
so step 5 needs push access there and step 6 is an upstream pull request.

## The commands

Every step above is one command, non-interactive, printing no secrets: exit 0 on success, 1 when
the thing it checked failed (a refused gate, a failed run, a failing test or checker problem), 2 on
a usage or configuration error. `spe-eval --help` prints this same table.

| Step | Command | What it does |
|---|---|---|
| Start | `spe-eval new <name> [--threat TM-NNN] [--path P<n>] [--injection <surface>] [--from <experiment>]` | writes every slot's file with `TODO`s, deriving the mitigation id, its switch and the test file's name from `<name>` |
| Check | `check_experiment.py [<name>] [--json]` | offline, under a minute: whether the experiment will run and fits the catalog, without judging its shape; without `<name>`, every experiment |
| Test offline | `spe-eval test [<name>]` | the evaluation suite's own offline unit tests, then the checker, on the named experiment (default: the build's own) |
| Try | `spe-eval arm [<name>] baseline\|mitigated` | applies one arm and waits for the stack to answer |
| Run | `spe-eval run [<name>] [--repeat N] [--detach]` | measures every arm: the baseline, then the mitigated arm if there is one |
| Watch | `spe-eval status [--json]`, `spe-eval wait [--timeout S]` | the lock and the run in progress; `wait` blocks until it ends |
| List | `spe-eval runs [--json]` | every kept run, newest first |
| Read | `spe-eval results [--run <id>] [--json] [--test <id>]` | the latest run, or the one named: both arms, side by side |
| Share | `spe-eval pr-body [<name>] [--run <id>]` | the PR title and body, filled in from the files and the run |

## What the checker checks

`check_experiment.py [<name>]`, at the repository root beside `validate.py` (standard library plus
PyYAML, offline, under a minute), checks that an experiment will run and that its files fit the
catalog -- the threat, path, mitigation and test ids it names resolve; no `TODO` is left in a file
it names; an injection's payload, canary file and switch are consistent; every mitigation's `off`
matches the Ansible defaults. It does not judge what a contribution should contain: it never
refuses an experiment for its shape, or for what its run showed. `--json` prints the same problems
as a list; without `<name>` it checks every experiment in `experiments/`.

## Writing up the result

The PR template (`.github/pull_request_template.md`, applied automatically to every PR) has one
section per slot, each marked *if any*, plus *Idea and rationale* and *Result*. `spe-eval pr-body`
fills in the files and the run's counts for you; what it leaves as a placeholder is yours to
write:

- **The reasoning goes in the pull request**: why this attack or mitigation, what you tried,
  known limits -- under *Idea and rationale*.
- **The lasting explanation goes in the files**: the experiment's own `description`, and the
  threat or path files it names, so it is still there once the PR itself is old history.

*Result* is `matrix.py counts`-level output: labels and counts for each arm, never an answer or a
token, so it is always safe to post. It is one data point, read next to the cumulative ladder
view that lives alongside the committed controller-side runs. A contribution edits neither
`matrix.py` (its labels come from the catalog files, not a hand-kept list) nor that view -- an
experiment adds a row to the catalog, it does not change how the catalog is read. A reviewer who
wants the result reproduced can build their own workspace from `spe-x-<name>` and run
`spe-eval run`.

## See also

- `experiments/README.md` -- the index of experiments, and the ladder as the worked example.
- `threats/TEMPLATE.md`, `paths/TEMPLATE.md`, `mitigations/TEMPLATE.yml`, `experiments/TEMPLATE.yml`
  -- one template per slot, each with a comment per key; `spe-eval new` fills them in for you.
- `platform/instance/workspace/AGENTS.md`, *Experiments* -- the same path, for a coding agent,
  with every command's success output and a worked example of writing a mitigation.
