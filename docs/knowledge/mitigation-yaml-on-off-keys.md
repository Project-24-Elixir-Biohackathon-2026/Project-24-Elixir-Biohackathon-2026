# A mitigation's `on`/`off` keys must be quoted

`validate.py` on a new `mitigations/<id>.yml` with bare `on:` and `off:` keys fails with
`FAIL L1.yml: unknown field 'True' (allowed: id, name, description, closes, on, off, requires, conflicts,
probes, status)` (and the same for `'False'`), not a message naming `on` or `off` at all.

**Cause**: YAML 1.1's default resolver (what PyYAML's `safe_load` uses) reads the unquoted scalars `on`, `off`,
`yes`, `no` as booleans, so the top-level key `on:` becomes the boolean key `True`, and `off:` becomes `False`.

**Fix**: quote both keys, `"on": {...}` and `"off": {...}`, as every mitigation file in `mitigations/` does.
