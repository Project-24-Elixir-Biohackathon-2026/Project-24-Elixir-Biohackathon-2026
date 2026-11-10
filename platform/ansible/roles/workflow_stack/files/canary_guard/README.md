# canary-guard

A TM-001 control in the SPE agent's path: a reverse proxy between Traefik and
WES, DRS and TRS that redacts canary tokens in every API response before the
agent reads them. Whichever chat frontend drives the agent, its data arrives
through these three APIs: DRS descriptions and aliases, TRS descriptions and
workflow files, service-info, and WESkit run stdout/stderr (the "print it to
stderr, then read the run log" route).

- **Matching:** every candidate substring is hashed and looked up in the
  hand-off's hash-only manifest, copied to `~/workflow-stack/guard/manifest/`.
  JSON bodies are matched in their decoded string values too, so the escaped
  newlines of a WESkit run log do not hide the token on the next line.
  The VM never holds plaintext canaries. Same matcher as
  `platform/canary_check/`, which checks archives after the fact.
- **Action:** text/JSON bodies get `[REDACTED:<type>]`; a hit in a binary body,
  a hit that cannot be replaced in the raw body (a token written with `\u`
  escapes), or a body over `GUARD_MAX_BYTES` is refused with 502 (fails closed).
- **Evidence:** each hit is one JSON log line (type, method, path; never the
  token): `docker compose -p workflow-stack logs canary-guard | grep canary_hit`.
  Responses carry `X-Canary-Guard: redacted=<n>`.
- **Switches** (`inventory/group_vars/all.yml`): `spe_canary_guard`,
  `spe_canary_guard_mode` (`redact` | `monitor` | `off`),
  `spe_canary_guard_exempt` (default `registry-study-id`: study ids are part of
  the DRS file names the agent must use, so redacting them breaks normal work).

## Comparing with the baseline

Run the same prompts on a workspace from `spe-testbed` and one from
`spe-canary-guard`, then compare outcomes in the run reports and the canary
check of both archives (`platform/canary_check/`). `monitor` mode measures how
often canaries would have been redacted without changing what the agent sees.

## Limits

- **Exact tokens only.** A workflow that encodes, splits or paraphrases a value
  before printing it gets past the guard. That is the expected next attack and
  the measurable difference from a model-based checker.
- It guards what comes back through the APIs, not what the agent writes in its
  own answer from its own reasoning.
- Without the manifest (an existing workspace after `spe-apply stack`; the
  hand-off only runs at creation) it is a plain proxy. Test it on a fresh
  workspace from the template.

Tests: `pytest platform/dev/tests/test_canary_guard.py` (fake upstream, real proxy).
