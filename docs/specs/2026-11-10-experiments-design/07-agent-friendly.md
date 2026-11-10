# Built for coding agents

Most participants will run the whole path through a coding agent: Coder Agents in the dashboard, or Claude Code,
Codex or opencode in the workspace terminal. (This is the participant's helper, not the SPE agent under test.) So
every step is a command an agent can run, read back as text, and judge from its exit code. The one app,
Evaluations, is a view for people over what `spe-eval results` prints; there is no run button.

## One entry point for the agent

`platform/instance/workspace/AGENTS.md`, which every one of those agents reads in the workspace, gets a section
*Experiments*: the path of 05 as numbered steps, each with its command and what success prints. Slice 3 writes its
first steps (`arm`, `run`, `status`, `wait`), which the early output tries with an agent; slice 6 completes it. It points to
`experiments/README.md`, the index of experiments (one line each: name, threat, paths, mitigation), and to the
ladder experiments as worked examples. Nothing an agent needs is only in a UI or only in this spec.

The section includes one worked example of writing a mitigation, the step the commands cannot do for the agent:
L1 (TRS read-only) as the reference, shown as its parts: the Ansible change in the SPE agent's path (Traefik and
WES, not an installer), the Jinja guard on its switch so the stack is unchanged with it off, `mitigations/L1.yml`,
the probe that shows it, and the two `curl` checks (one refused, one still working) to make after
`spe-eval arm … mitigated`. A participant's guard service follows the same shape.

Agents in the workspace work in that workspace: they do not create, stop or delete workspaces (each is a cloud
VM, and stop destroys it); a fresh build from a branch template is the participant's step, from the dashboard.

## Commands

How to run the tests is these commands, in this order: `test` after each edit (offline), `arm` to try a build by
hand, `run` to measure both arms (the baseline only for red), `results` to read them. The workspace guide's *Experiments* section and
`CONTRIBUTING.md` give the same table; `spe-eval --help` prints it.

| Step | Command | For an agent |
|---|---|---|
| Start | `spe-eval new <name> [--kind red\|blue\|end-to-end] [--threat TM-NNN] [--path P<n>] [--injection <surface>] [--from <experiment>]` | `--kind` (default `end-to-end`) picks what the skeleton holds (05, *Kinds of contribution*): `red` no mitigation and `mitigation: null`, `base` the `--from` experiment's `base` plus its mitigation (from `ladder-l2`: `[L1, L2]`, the build it attacks); `blue` no injection, threat, path or test file, and the experiment's `tests` and `injections` filled from the catalogue's attacks on `--path`; `end-to-end` all of the following. Writes the skeleton: `experiments/<name>.yml`, `mitigations/<name>.yml` with a `spe_mitigate_<name>` switch, its default in `group_vars`, with `--injection` a `fixtures.json` entry, a payload file and a `spe_inject_<name>` switch defaulting to `false` (01, *Attacks*), `tests/experiments/<name>.yaml` with one labelled test, and threat or path files from their templates when the ids are new; prints each path and the `TODO`s to fill |
| Check | `check_experiment.py [<name>] [--base <ref>] [--json]` | the kind first (`kind: red (…)`), then each problem as `file:line: id: what is wrong: what to do`; `--json` the same as a list |
| Test offline | `spe-eval test` | the offline checks, no instance and no model: the evaluations' unit tests (`pytest` in `platform/promptfoo-evals`, which lint the catalogue and every assertion a test names) and the checker; seconds, so an agent runs it after every edit |
| Try | `spe-eval arm [<name>] baseline\|mitigated` | applies one arm and exits when the stack answers |
| Run | `spe-eval run [<name>] [--repeat N] [--detach]` | `--detach` starts the run in the background (a user systemd unit) and returns at once with its id; the agent's own command timeouts never cut a run short |
| Watch | `spe-eval status [--json]` | the lock, the run id, arm, test *k* of *n*, last error; `spe-eval wait [--timeout S]` blocks until the run ends or the timeout passes, for agents that can wait in bounded steps |
| List | `spe-eval runs [--json]` | every kept run, newest first: id, experiment, mitigation sets, model, repeat, how it ended |
| Read | `spe-eval results [--run <id>] [--json] [--test <id>]` | the latest run, or the one named; the two arms side by side as text: per test and metric, baseline and mitigated pass counts, the utility tests' outcome, and a one-line verdict per metric (closed, narrowed, unchanged, worse); a one-arm run gives the baseline counts and no verdict; `--test` adds that test's assertion reasons |
| Share | `spe-eval pr-body [<name>] [--run <id>]` | prints the title with the kind's prefix, the kind's PR template filled in from the latest run of `<name>` or the one named (the files, the counts, the checker's output), and the new-PR link that selects that template, since GitHub cannot choose one; ready to open the link and paste, or to pass to `gh pr create --title … --body-file -`; refuses a red run with no harm recorded and a blue or end-to-end one with no mitigated arm |

Every command is non-interactive, prints no secrets, and exits 0 on success, 1 on a failure of the thing checked
(a failed check, a run whose gate refused), 2 on a usage or configuration error, so an agent can branch on it
without parsing prose.

`results` reads the counts (`matrix.py counts` of each arm) and the reports; by default it prints labels, counts and
reasons only. A reason may quote a canary, as the viewer does; both are the workspace owner's, like the chats.

## Conventions an agent can follow without asking

- **Names derive from one name.** Given `<name>`: the experiment `experiments/<name>.yml`, the mitigation id
  `<name>` (unless it reuses one), its switch `spe_mitigate_<name with _>`, its tests
  `tests/experiments/<name>.yaml`, its branch `experiment/<name>`, its template `spe-x-<name>`.
- **Templates for every file**: `threats/TEMPLATE.md` (exists), `paths/TEMPLATE.md`, `mitigations/TEMPLATE.yml`,
  `experiments/TEMPLATE.yml`, each with a comment per key; `spe-eval new` fills them.
- **Commit and push as you go**: to `experiment/<name>`, after each working step; stop destroys the VM (the
  archive saves unpushed work too, decision 21, but a pushed branch is what others can build from).
- **One check before every push**: `check_experiment.py <name>` exits 0.
- **A run needs the workspace alone**: the agent says so to the person before `spe-eval run` (chats are reset by
  the restores), and does not `spe-apply` while the lock is held (it would be refused).

## Acceptance

An agent given only the workspace and the sentence "propose an attack and a mitigation for TM-003 through P2 and measure it" can
reach a pushed `experiment/<name>` branch with a passing checker and a filled PR body, using only the commands
above and the workspace guide. The plan's last slice checks this end to end, with a coding agent in a de.NBI
workspace, and records where it needed help.
