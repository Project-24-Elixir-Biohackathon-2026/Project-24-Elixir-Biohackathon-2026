# A recreated Compose network loses a container's service alias

**Symptom.** `spe-eval run ladder-l3`: the mitigated arm (L3 on) failed in `spe-apply all` at the `agui`
check "an unauthenticated request from the sandbox to the agent did not get 401"; returning to the build's arm
(L3 off) failed the same way. The sandbox's `curl http://agent:8100/agent` gave `000`: `getent hosts agent` found
nothing, though `spe-frontend-agent-1` resolved. `docker inspect spe-frontend-agent-1` showed `DNSNames`
without `agent` on `spe-frontend_tools` (and with it on `spe-frontend_ui`).

**Cause.** Compose 5.3.1 on Docker 29.6.2 (agent-service-1, 2026-11-11): when an overlay changes a network's
config (`compose.egress.yml` gives `tools` its own subnet and `ip_range`), `up -d` recreates the network and
reconnects a container that is on two networks without its service alias on the recreated one. Reproduced with
two alpine services (`a` on `ui` and `tools`, `b` on `tools`): after the overlay, `b` cannot resolve `a`. An
`up -d --force-recreate` in the same call, or a `--force-recreate a` after, restores it.

**Fix.** `spe-apply up` keeps a digest of the resolved `networks` section in `~/spe-frontend/.compose-networks`
and adds `--force-recreate` when it changed or is missing (`platform/dev/tests/test_spe_apply_up.py`).

**By hand on a broken instance:** `spe-apply up` once with the fix (the missing digest recreates all), or
`docker compose -p spe-frontend -f ~/spe-frontend/docker-compose.yml <overlays> up -d --force-recreate agent`.
