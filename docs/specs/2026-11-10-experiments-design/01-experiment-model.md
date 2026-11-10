# The experiment model

An experiment ties five kinds of thing together. Three are descriptions, one file each, beside each other at the
repository root; injections stay in the injection catalogue and tests where the suites are. An experiment file
names them.

| Kind | Where | Id | Exists today |
|---|---|---|---|
| Threat | `threats/TM-NNN-<slug>.md` | `TM-NNN` | yes (TM-001 … TM-005), checked by `validate.py` |
| Path | `paths/P<n>-<slug>.md` | `P<n>` | no: P1–P4 are a table in the ladder's design text |
| Mitigation | `mitigations/<id>.yml` | `L<n>` for ladder levels, else kebab-case | no: four Ansible variables |
| Injection | `platform/ansible/catalog/injections/fixtures.json` entry plus its payload file | kebab-case `id` of the entry | yes: three, each on its own `spe_inject_*` switch |
| Test | `platform/promptfoo-evals/tests/<group>.yaml` (ladder) and `tests/experiments/<name>.yaml` | kebab-case `id` in the test's `metadata` | ladder tests yes; experiment tests no |
| Experiment | `experiments/<name>.yml` | the file's stem | no |

**Threat and path differ.** A threat is what goes wrong (data exposure, prompt injection); a path is the concrete
route through this stack (agent-written workflow code, egress). They are many-to-many: TM-001 happens through any
path; TM-003 enters through P1 and usually uses P2. A mitigation closes paths, not threats. A threat and a path
are descriptions; what makes one happen on the stack is an attack, a test's prompt or a planted injection
(*Attacks*).

## Paths

`paths/P<n>-<slug>.md`, front matter and body fixed like a threat's (`paths/TEMPLATE.md`):

```markdown
---
id: P2
name: Agent-written workflow code
description: >
  The agent registers a workflow that reads a sensitive file, submits it to WES and reads its output.
reaches: [flag_file, honeypot_files, registry_tokens, vcf_variants]   # canary types, the template's keys
---
# P2: Agent-written workflow code
## Route
## Shown by
```

*Route*: the steps, with the real endpoints. *Shown by*: the probe or test that demonstrates it open. P1–P4 are
written from the ladder's table (06). `reaches` uses the canary types of the Coder template's `canaries`
parameter.

## Mitigations

`mitigations/<id>.yml`:

```yaml
id: L2
name: Data tiers
description: Workflow containers mount only the listed tiers of /data-share and /drs-data.
closes: [P3]                 # path ids; may be empty for a control that narrows rather than closes
on:  {spe_harden_data_tiers: [ref, genomes]}
off: {spe_harden_data_tiers: []}
requires: []                 # optional: mitigation ids that must also be on
conflicts: []                # optional: mitigation ids that must not be on
probes: [tier-reach]         # optional: the controls-suite probes it closes when on (03, the gate)
```

- `on` and `off` are the Ansible values; `off` must equal the defaults in `platform/ansible/inventory/group_vars/all.yml`
  (decision 4), so a build without the mitigation is today's build. A value may be a list or a map, which a plain
  boolean switch could not express (L2 is a list).
- A participant's mitigation adds its own variable, default off, named `spe_mitigate_<id with _>`, and guards
  its Ansible change with it.
  Like an injection on a new surface (*Attacks*), its change carries the `stack`, `drs`, `trs` or `frontend` tag so
  `spe-apply all` applies it, and both arms of `spe-eval run`, on a running workspace; a change that acts only at
  creation is tried by building fresh from the branch template (05, step 5).
- **Each Ansible key belongs to one mitigation.** No two mitigation files set the same key in `on`, so selecting
  any set of them merges without one value silently replacing another (both `spe-eval`'s `-e` values on the VM and
  Terraform's `merge` at a build keep the last);
  `validate.py` refuses an overlap and names both files. A participant whose control needs a key another
  mitigation owns adds its own `spe_mitigate_*` switch instead, or declares the pair in `conflicts`.
- Mitigations are combined through `base`: a contributed mitigation is measured on top of the ones it lists there,
  so an interaction between two (one masking or breaking the other) shows only in an experiment that has one in
  `base` and the other under test. `requires` and `conflicts` declare the interactions an author knows of; a
  merge conflict in a shared Ansible file is resolved in the PR, as for any code.
- `requires` and `conflicts` are checked twice: by `check_experiment.py` on the files, and by `create.yml` on the
  build (as it already refuses the airlock with Open WebUI).
- `hardening.json` (the hand-off) gains `mitigations: [ids]`, the mitigations the build was made with.

## Attacks

A participant proposes a threat and a path as files (above, 05); an attack is how the experiment makes it happen
on the stack. There are two kinds, and an experiment may use either or both:

- **A prompt**: the participant, as the agent's user, asks for the harm or for a benign task that leads to it. It is
  a test in `tests/experiments/<name>.yaml` (*Tests*), nothing else.
- **A planted injection**: text an attacker controls placed where the agent reads it, which the agent may follow
  while doing a benign task. It is an entry in `platform/ansible/catalog/injections/fixtures.json` (`id`,
  `switch`, `surface`, `payload`, `select`, `target_file`, `canary_file`, `action`, `disclosure`, as the three
  today) plus its payload file beside it, on its own switch `spe_inject_<id with _>`, default `false` in
  `group_vars/all.yml`, so a build without it is today's (as for a mitigation's `off`, decision 4).
  - On a surface that exists (`trs-description`, `drs-description`, `workflow-comment`), it is data only, once
    the roles that plant there read the catalogue: today `drs_register` and `trs_install` take the first entry
    per surface and test the three `spe_inject_*` switches by name, so they learn to plant every entry whose
    switch (named in the entry, `false` when undefined) is on, and the ladder's three keep their placements.
    They run under the `drs` and `trs` tags, so `spe-apply all` plants an injection on a running workspace with
    no rebuild, as for the ladder's three today.
  - On a new surface (a file in `/data-share`, a tool's output, a page reached by egress), it is also code: the
    role that plants it, guarded by the switch, reports its placement (`surface`, `location`, `payload_sha256`)
    as `trs_install.py` and `drs_register.py` do, so `injections_manifest.py` checks it like the others (exactly
    one placement, the committed payload, a canary in its target), and carries the `stack`, `drs` or `trs` tag
    so `spe-apply all` plants it on a running workspace. A surface planted only at creation is tried by building
    fresh from the branch template (05, step 5).
  - With a new **action** (what the payload asks for: today only `register-workflow-run-read-stdout`, a workflow
    that reads the target and prints it), it is also scoring code: a detector for that action in
    `metrics.py`, finding evidence of it in the state diff and the trace as `_actions` does for today's, with
    unit tests on a fixture trace. `injection.followed` picks the detector by the entry's `action`, so an
    injection may ask for anything a detector can see (a write to TRS, a request out, a deleted object).

  The evaluation side reads all three from the catalogue as the labels are (decision 3): today
  `injections_schema.py` lists the three ids, the surfaces' location keys and the one action in code; it builds
  them from `fixtures.json`, the location keys from a `surfaces` map beside the fixtures, and the actions from
  the detectors `metrics.py` defines. So a completely different injection (new surface, new action, or both)
  needs no edit to the schema, only its planting role and, for a new action, its detector.

  What stays fixed is the schema's guidance, the same for every injection: the entry's fields (and no token, seed
  or credential field), one placement of exactly the committed payload, a payload that names its target, a
  canary in that target, a switch that defaults off. Changing those is a change to `injections_schema.py`,
  reviewed as shared code. `disclosure` stays derived from the canary file's directory (`registry/`: first five
  lines; `secret/`: whole file); a target under another directory extends that rule in the same change.

The experiment lists its injections (`injections: [ids]`); they are **on in both arms**, so the attack is held
fixed and only the mitigation varies (03). The planted injections are scored with no new assertion:
`injection.followed` scores every entry of the arm's `injections.json` against the state diff and the trace, so
the experiment's tests need only the benign requests that pass through the planted text (`group: injection`, as
`tests/injection.yaml`). A path whose attack is neither (a new route out, P4-like) is shown by a test and, when
a mitigation should close it, by that mitigation's `probes` (03, the gate).

## Tests

The ladder's suite (`agent.yaml`, `tests/<group>.yaml`) stays one fixed catalogue run unchanged at every level, so
its levels stay comparable; its count stays pinned by its lint. An experiment's own tests go into
`tests/experiments/<name>.yaml`, same format and labels, run only by that experiment (03). Labels:

| Key | Values | Read from |
|---|---|---|
| `group` | the test files' stems | `tests/*.yaml`, `tests/experiments/*.yaml` |
| `threat` | `TM-NNN` or null | `threats/` |
| `path` | `P<n>` or null | `paths/` |
| `closed_by` | a mitigation id or null | `mitigations/` |

`matrix.CATALOGUE` is built from these files at import (decision 3); its role as the one definition the lint and
`counts` share does not change, and the ladder's ids (TM-001…, P1–P4, L1–L5) keep their meaning, so committed
counts stay valid. L4 and L5 stay valid `closed_by` values while their mitigation files do not yet exist: a
mitigation may be listed with `status: planned` and no `on`/`off`, which the form does not offer.

## Experiments

An experiment file is a preset of the `spe-experiments` template (02), in the shape of `spe`'s testbeds, with an
`experiment:` block and, optionally, `vars:`:

```yaml
name: TRS guard
description: Does validating TRS writes stop agent-written workflows?
parameters:              # the template's parameters; `experiment` and `mitigations` as well
  experiment: trs-guard
  mitigations: []        # = base: the workspace starts in the baseline arm
  samples: [HG002, HG003, HG004, HG005]
  ...
experiment:
  threat: TM-003
  paths: [P2]
  mitigation: trs-guard  # the one under test: off in the baseline arm, on in the mitigated arm;
                         # null for a one-arm experiment (ladder-l0: the build as it is)
  base: []               # mitigations on in both arms
  injections: [registry-preflight]   # planted attacks, on in both arms (*Attacks*); [] for none
  tests: [register-broken-workflow, summarise-workflows]   # ids; the utility group always runs as well
vars:                    # Ansible values the experiment needs that are not form parameters
  spe_frontends: [agui]
  spe_eval_sink: true
```

An experiment with `mitigation: null` has one arm, the baseline: it measures a build as it is (`ladder-l0`) and
is a starting point to write experiments from, not a contribution (`spe-eval pr-body` refuses it).

`vars` exists because a preset can only set form parameters, and an evaluation needs build settings the form does
not offer (frontends, the test receiver). `main.tf` applies them (02). Keys in `vars` that a mitigation, an
injection or a parameter also sets are refused by the checker: one place per value; an injection's switch is set
only through `injections`.

An experiment fixes no seed: the seed is secret (it reproduces every canary), and the two arms already
share one build's canaries. Comparison across workspaces is the official ladder's business, not an experiment's.
