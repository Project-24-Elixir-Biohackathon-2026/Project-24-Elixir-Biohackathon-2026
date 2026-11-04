# 2026-11-04: Upstream AG-UI package: what changed since the start handoff

**Unit: the `contrib/<slug>` branch for the *Upstream PR for the AG-UI package* item (`BACKLOG.md`).** Start from
`docs/handoffs/2026-11-04T1111Z-upstream-package-start.md` (the cut, the PR text draft, the #9 steps), with these
updates from #40 and #41:

- **"The e2e checklist"** (1111Z, line 22) was the *AG-UI via Coder* BACKLOG item, now removed: the checks to
  re-run on the branch's checkout are #36, #38 and #40, written up in `docs/knowledge/agui-coder-e2e-check.md`
  (the workspace e2e and *The final archive*) and `docs/knowledge/agui-all-features-check.md`.
- **The TODO about an open failure** (1111Z, around line 146: tab B on session A shows 0 user messages) is
  resolved: CopilotChat virtualizes long chats, so the count was 0 by construction (`chat_rows` in the e2e note);
  #38 and #40 passed every check.
- **The PR text's testing list** also covers #40: the final archive on denbi-agui-01 from our checkout, both
  frontends (2 Open WebUI chats, 17 AG-UI sessions, chat, journals and archive in agreement), and #41's fix.
- **#41's fix goes upstream in the package**: `spe_preflight.py` (the reset hands Compose the compose link) and
  `destroy.yml`'s `COMPOSE_PROFILES='*'`, with their tests in `platform/dev/tests/test_spe_preflight.py`.
  `docs/knowledge/compose-symlink-env.md` is fork-only.
- No instance is up and every workspace is stopped; the re-run needs one (pre-approved, one at a time).
