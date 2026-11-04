# 2026-11-04: AG-UI via Coder, step 2: end to end in a portal workspace

**Unit: `change/agui-coder-e2e-2026-11-04`**, step (2) of `BACKLOG.md` *Next*, *AG-UI via Coder* (its checklist and
pass criteria are there; don't copy them). Then step (3) (archive on stop, `create.yml`/`destroy.yml` from our
checkout), then the *Upstream PR for the AG-UI package* item. Approved already: instances and paid calls for this
test, one instance at a time (a workspace counts; stop it before step 3's `create.yml`).

**State.** Step 1 passed in #36: `denbi-agui-01` runs `main`'s tree on the clone-on-VM layout (`~/sperange` at
`c1d9411`, identical to `main` `52cdc2c`); all-features check 17/17; `archive.yml` live wrote 12 sessions that agree
with the chat. Deploying from our fork first needed #37 (`docs/knowledge/instance-clone-private-submodule.md`).
`denbi-agui-01` is idle; leave it running.

**How.**
- Workspace from the portal's main template with the `agui` frontend (`platform/coder/README.md`; Coder CLI as in
  `docs/knowledge/denbi-llm-key.md`). `theo/theo-workspace` is `spe-ga4gh-baseline` and outdated: stop it first if
  a new workspace is needed. Never touch another user's workspace.
- In it: `~/sperange` fetches our fork (`https://github.com/thodkatz/elixir-biohackathon-2026-test.git`, `main`),
  `spe-apply all` (`platform/instance/workspace/AGENTS.md`).
- The scripted part: `docs/knowledge/agui-all-features-check.py` through a tunnel (via `coder port-forward` or
  `coder ssh -L`), extended for the checklist's multi-session, mid-run switching and stop-and-resend items, and for
  several compactions per session. Compare chat, rebuilt journal, live archive and final archive run for run.
- A failure is fixed in its own PR before the step completes.

**Screenshots for the upstream PR** (the user, 2026-11-04): the kraatz PR's body embeds them, from the contrib
branch's checkout, on prompts that show no canary names (`docs/guides/contributing-upstream.md`, step 5). The
PR text then goes in an issue on our fork (issues enabled for it) for the user to copy.
