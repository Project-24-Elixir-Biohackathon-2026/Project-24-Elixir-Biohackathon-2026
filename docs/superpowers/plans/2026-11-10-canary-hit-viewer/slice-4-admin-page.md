# Slice 4/5: the admin page

Branch `impl/canary-hit-viewer-4-admin-page`. Spec: decisions 7, 10, 11 (*Admin page*, *Security*), clarification
1 (filter by frontend); plan rulings 6, 7, 9. Global constraints: [README](README.md#global-constraints).

### Task 12: the admin page, its JSON and its stream

Decisions 7, 10, 11; rulings 7, 9.

**Files:**
- Modify: `platform/report/sperange_report.py`, `platform/report/hits_view.py`
- Create: `platform/report/static/hits-admin.js`
- Test: `platform/report/tests/test_hits_service.py`

**Interfaces:**
- Consumes: slice 3's `can_see_hits`, `hit_html`, `status_line`, the stream writer (Task 10), `Store.meta`,
  `Coder.workspace_state(token, wid)`.
- Produces:
  - `hits_view.workspace_rows(hits_dir: str, metas: dict[str, dict | None]) -> list[dict]`: one row per
    `<uuid>.jsonl` or `<uuid>.status.json` in the hits dir (a workspace whose sidecar is gone is still a row,
    its `owner` and `instance` from its newest hit): `workspace`, `name`, `owner`, `instance`, counts per loud
    kind, `quiet` (count), `newest` (the newest hit's `detected`), `status` (the status line). Sorted by
    `newest`, newest first; rows with no hit last.
  - `hits_view.admin_body(rows, hits, states: dict[str, str | None]) -> str`: the notice (decision 11), "Hits are
    what each participant's own instance reported." above the list, the workspace table (each name links to
    `/reports/<id>/hits`; the Coder state when the lookup succeeded, else blank), four `<select>` filters (kind,
    canary type, frontend, workspace) built from the values present, then the hits newest first, each
    `hit_html(hit)` wrapped with `data-kind`, `data-type`, `data-frontend`, `data-workspace`, plus the workspace's
    name.
  - `GET /reports/hits`: admins only (403 `message_page` for anyone else, the login redirect when logged out);
    the newest 500 hits over all files (ruling 9) and a line saying how many more there are. The route is matched
    before the `<id>` routes (`hits` is not a UUID, so nothing changes for them).
  - `GET /reports/hits.json`: admins only; `{"workspaces": rows, "hits": [the newest 2000 records]}`; a workspace's
    full list is its own `/reports/<id>/hits.json`.
  - `GET /reports/hits/events`: admins only; the Task 10 stream over every `<uuid>.jsonl` in the hits dir
    (rescanned every 0.5 s, so a new workspace's file joins), event ids `<workspace id>:<line number>`, the data
    as Task 10's plus `workspace`; no resume: it starts at each file's current end (the page reloads
    itself on reconnect). Same caps as Task 10 (ruling 7).
  - `hits-admin.js`: the filters hide the rows that do not match (`hidden`), the stream inserts new hits at the
    top under the same filters and bumps the workspace's counts; on a reconnect (an `open` after an
    `error`) it reloads the page (`location.reload()`), which reads the hits afresh: the spec's "reloads
    `hits.json`", done by the page since `hits.json` holds records and the page renders HTML server-side
    (ruling 8).
- Coder state per workspace: `coder.workspace_state(token, wid)` for each row, with the viewer's token; a failure
  leaves that row's state blank (the page still renders).

- [ ] **Step 1: Write the failing tests**: `test_admin_lists_two_workspaces` (two hits files, one sidecar each:
  200, both workspaces' hits, each name linking to its page), `test_admin_page_forbidden` (a participant, even the
  owner of one of the workspaces: 403 for the page, `hits.json` and the stream), `test_admin_notice_and_banner`,
  `test_deleted_workspace_listed` (a hits file without a sidecar: its row, owner from its hits),
  `test_filters_offer_present_values` (the frontend `<select>` has `agui` and `openwebui` when both are present;
  each hit carries its `data-*` attributes), `test_admin_cap_500` (600 hits: 500 rendered, "100 more"),
  `test_admin_stream_ids` (append to one of two files: an event with id `<wid>:<n>` and that workspace),
  `test_admin_stream_new_file` (a third workspace's first hit while the stream is open arrives),
  `test_coder_state_failure_renders` (the fake Coder fails the state lookup: 200, state blank).
- [ ] **Step 2: Run** the hits service tests. Expected: FAIL.
- [ ] **Step 3: Implement** the routes, `workspace_rows`, `admin_body`, `hits-admin.js`.
- [ ] **Step 4: Run** the report suite. Expected: PASS.
- [ ] **Step 5: Commit** `Report service: the admin canary hits page`.

### Task 13: docs, a link from the reports list, the screenshot

Decision 7 (one click to each workspace's page).

**Files:**
- Modify: `platform/report/sperange_report.py` (`list_page`: admins see a "Canary hits" link to `/reports/hits`
  above the list), `platform/report/README.md` (the admin page, its JSON and stream, the 500/2000 caps),
  `platform/coder/README.md` (*Operating*: where an owner finds every workspace's hits)
- Test: `platform/report/tests/test_hits_service.py`

- [ ] **Step 1: Write the failing test** `test_reports_list_links_admin_hits` (an admin's `/reports/` has the
  link; a participant's does not).
- [ ] **Step 2: Implement** the link and the READMEs.
- [ ] **Step 3: Run** the report suite. Expected: PASS.
- [ ] **Step 4: Screenshot** as in slice 3, Task 11, Step 4, as an admin over two workspaces' fixture hits, one
  filter set: `evidence/slice-4/admin-page.png`, embedded in the PR body.
- [ ] **Step 5: Commit** `Canary hits: admin link, docs, screenshot`.
