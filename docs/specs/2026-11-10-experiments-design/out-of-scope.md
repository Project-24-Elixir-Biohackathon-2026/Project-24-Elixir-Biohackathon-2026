# Out of scope

| Item | Why not now | Where it goes |
|---|---|---|
| A shared, team-wide view of the official ladder results (the replayed evals) on the portal | an experiment's viewer is per workspace and owner-only; a shared one needs its own access rule for canary values and its own service | a later spec of its own |
| L4 and L5 as selectable mitigations | L4 (typed tools) is not built; L5 (airlock) is refused while Open WebUI runs | `mitigations/L4.yml`, `L5.yml` stay `status: planned` until their specs land |
| Branch templates from forks or PR refs | the portal makes them from upstream branches only | a later change to `sync-template.sh` |
| CI running `check_experiment.py` | the repositories have no workflows yet | with the first CI workflow |
| Labelling a PR by its kind automatically | no workflows yet; the reviewer adds the label the checker names | a workflow running `check_experiment.py --json`, with the first CI workflow |
| A threat or path contributed alone | a description the pipeline cannot run; it comes with an attack (red or end-to-end) | an issue; `check_experiment.py` refuses it as a PR |
| A probe for every participant mitigation | a mitigation's `probes` is optional; without them the gate checks only the ladder's | a later spec, if experiments show the need (03's gate notes an undeclared probe meanwhile) |
| The ladder matrix in the viewer | promptfoo has no levels or conditions | `matrix.py render`, as a command |
| Comparing experiments across workspaces | the seed is secret, so builds differ | the official ladder's controller-side runs |
| Keeping or deleting the existing template `spe` | the new template must prove itself first | the user, once `spe-experiments` runs the ladder experiments on the portal |
| Creating, reaching or stopping workspaces with the `coder` CLI (an agent on the participant's laptop) | participants work in their workspace, created from the dashboard; agents in it do not create or destroy workspaces | not planned (the user, 2026-11-10: "they should work on their workspace") |
| A contributed mitigation as a ladder level, with a column in the cumulative matrix | a merged mitigation stays an experiment; a level is chosen by maintainers and measured by controller-side runs against the same canaries | a later spec, per level (as L4 and L5) |
