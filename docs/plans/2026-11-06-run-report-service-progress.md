# Run report service: progress and rulings

Plan: `docs/plans/2026-11-06-run-report-service.md`. Spec:
`docs/specs/2026-11-06-run-report-service.md`. Branch `template/report`.

## State

| Task | State | Evidence |
|---|---|---|
| 1 Service | done | 25 tests in `platform/report/tests` (login redirect, 401 on the API, cookie forwarded as a header only, read for anyone, write for owner and admins, 412 on a stale `If-Match`, 428 without it, 403 cross-origin, 413 and 400 on size and encoding, sanitizer allowlist, CSP on every page). Run by hand against the live Coder on `127.0.0.1:7080` with the admin session: redirect, list, editor, save |
| 2 Ansible creation | done | role `run_report` run twice against a scratch directory with `instances/example.yml`: first run `changed=3`, second `changed=0`; the sidecar's `template_sha256` matches the rendered file; `create.yml` syntax check clean |
| 3 Ansible archive | done | `write_run.py` takes two arguments; `platform/dev/tests` archive tests pass (38 with `ansible-playbook` on the PATH); the Open WebUI fixture's expected tree re-rendered: the "Run report" note is now `notes/run-report.md`, the index says the report is missing |
| 4 Template | done | `spe_coder_workspace_id` passed; external app "Report"; metadata item "run report" |
| 5 Deploy files and docs | done | unit, env example, Caddyfile example, portal README step 9 and tables, getting-started, the AG-UI spec's out-of-scope and §14 notes |
| 6 Checks | done | see tasks 1 to 3 |
| 7 Live try | done 2026-11-06 | service deployed on the portal VM (user `sperange-report`, hardened unit, Caddy route); a report created by `ubuntu` on the share was rewritten by the service user through Caddy. Workspace `admin/report-try` from `spe-report` (two samples, one workflow, no smoke test; `coder create --rich-parameter-file`, since `--parameter` cannot carry JSON lists): the report and its sidecar appeared at the start of the build; the workspace carried the external app "Report" and the metadata item with the same URL; the page was editable for the owner and showed "running"; a line saved through the service landed in the file; after the stop the run directory held `report.md` and `report.json`, both `index.md` files said "filled in" (the AG-UI one linking `../report.md`), the page still opened, editable, showing "stopped"; no `cw-` server left. Workspace deleted afterwards; the report stays, as designed |

## Rulings

1. **The unit bind-mounts the checkout's `platform/report` instead of an ACL on
   `/home/ubuntu`.** `/home/ubuntu` is mode 750 and should stay unreadable for other
   users (the Caddyfile relies on it); `ProtectHome=tmpfs` with `BindReadOnlyPaths`
   gives the service user exactly that one directory. Cost if wrong: the unit fails
   to start on a host whose systemd lacks the options; the fallback is `User=ubuntu`.
2. **"Last saved" is set explicitly with the portal's clock.** The share's NFS server
   runs about 17 minutes ahead (seen 2026-11-06), so a plain write showed a future
   time. Cost if wrong: none beyond the extra `utime` call.
3. **The editor is EasyMDE, vendored** (2026-11-06, after the user saw the first page:
   "doesn't look good, not clearly structured"; the structured form was recommended,
   EasyMDE chosen). Adds 450 kB of static files and `style-src 'unsafe-inline'`. Cost
   if wrong: the files to refresh on an EasyMDE update; scripts stay strict.
4. **During the live try the unit runs from the branch worktree** through a drop-in
   `/etc/systemd/system/sperange-report.service.d/try.conf`, since the canonical path
   is the `main` checkout. Remove the drop-in after the merge and restart the unit.
