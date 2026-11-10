# Experiment tests

An experiment's own tests: `<name>.yaml`, same format and labels as `../`'s `tests/*.yaml`
(`id`, `group`, `threat`, `path`, `closed_by` metadata, linted by `tests/test_catalogue.py`).
Run only by that experiment, never by the ladder's `agent.yaml` (`tests: file://tests/*.yaml`
does not reach this directory): experiments spec `docs/specs/2026-11-10-experiments-design/01-experiment-model.md`, *Tests*.
