# Compose on a resolved symlink sees no services

**Symptom.** `destroy.yml -e spe_confirm_reset=<instance>` on an existing host (denbi-agui-01, 2026-11-04) passed
*Compose stacks down, with their volumes* (changed) and then failed *No containers left in this instance's compose
projects*: every `spe-frontend` container was still there.

**Cause.** `~/spe-frontend/docker-compose.yml` is a link to the clone's `platform/instance/compose.yml`, and its
services all have profiles. Compose reads `.env` (`COMPOSE_PROFILES`, the `${VAR}` values) from the directory of
the path it is given, the link's, not the target's. The reset handed it the resolved path, so no profile was on
and `down` saw nothing to take down:

```bash
docker compose -p spe-frontend -f ~/sperange/platform/instance/compose.yml config --services   # nothing
docker compose -p spe-frontend -f ~/spe-frontend/docker-compose.yml config --services          # all four
```

**Fix** (#41). Give Compose the link path: `spe_preflight.py`'s reset plan keeps it, and `spe-apply` passes it with
`--project-directory`. `destroy.yml`'s `down` also runs with `COMPOSE_PROFILES='*'`, so a service started under
a profile the `.env` lacks goes too. With an older checkout, finish a half-done reset from a checkout with the fix,
using `-e spe_archive_skip=true` if the archive already ran.
