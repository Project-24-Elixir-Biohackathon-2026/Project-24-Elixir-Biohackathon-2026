# Plan: run report service

Spec: `docs/specs/2026-11-06-run-report-service.md`. Branch `template/report`, so the
portal builds a template `spe-report` from it for the live try. Progress and rulings:
`docs/plans/2026-11-06-run-report-service-progress.md`.

## Tasks

1. **Service** `platform/report/`: server, static page, tests against a fake Coder
   API (login redirect, read for anyone, write for owner and admins only, `If-Match`
   conflict, size limit, escaped HTML, CSP, UUID validation, preview). README.
2. **Ansible creation**: role `run_report` on the controller, hooked into
   `create.yml`; `spe_coder_workspace_id` and `spe_reports_root` in group vars; the
   template without the seed and with the new wording.
3. **Ansible archive**: `write.yml` copies report and sidecar; `write_run.py` drops
   the note title and reads `report.md`; `export.yml` and `export_openwebui.py` drop
   the template; Open WebUI role stops creating the note; tests updated.
4. **Template**: `spe_coder_workspace_id` passed to Ansible; external app "Report".
5. **Deploy files and docs**: unit, env example, Caddyfile example, portal README
   (step 9, tables, smoke test), getting-started, the AG-UI spec's out-of-scope note.
6. **Checks**: service tests, `platform/dev/tests`, Ansible syntax check.
7. **Live try**: deploy the service and the Caddy route on the portal VM, create a
   workspace from `spe-report`, open the Report button, edit, stop, check the run
   directory; then the pull request.
