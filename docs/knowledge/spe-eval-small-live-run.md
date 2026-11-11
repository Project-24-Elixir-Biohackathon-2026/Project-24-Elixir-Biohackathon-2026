# A small `spe-eval run` for a live check: there is no test filter

`spe-eval run` has no flag to run one test. For a quick live check (experiments slice 5, 2026-11-11), add an
untracked experiment file on the VM's clone, a copy of the arm's experiment with `experiment.tests: [<id>]` (e.g.
`experiments/live-s5.yml` from `ladder-l0.yml` with `tests: [backup-outside]`), run it with `--repeat 1`, and delete
the file afterwards. `spe-eval` adds the utility tests anyway: that run was 6 tests, about 25 minutes on de.NBI
`qwen3.8-27b`.
