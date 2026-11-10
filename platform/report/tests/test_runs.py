"""The runs browser and its API against a fake Coder API and an archive directory laid out like
playbooks/archive.yml writes it: login (cookie or header), the listing without e-mails, one run with
its report and chats, a chat as turns, the raw files, and ids that must not reach the filesystem."""
from __future__ import annotations

import hashlib
import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sperange_report as sr  # noqa: E402
from test_report import FakeCoder, NoRedirect, ThreadingHTTPServer, WID  # noqa: E402

RUN = "2026-11-10T084305Z_cw-tammy-coffee-wildfowl-87"
OLD = "2026-11-01T120000Z_cw-bob-old-run"
JOURNAL = "0584247b-5273-4a8e-a7a3-3fcc1877de45"
TEMPLATE = "# Run report\n\n## Goal\n\n*What did you try?*\n"

OWUI_MD = """# Available Data

- Created: 2026-11-09 14:54 UTC
- Updated: 2026-11-09 15:09 UTC
- Tags: -
- Archived in OpenWebUI: no

## user · 2026-11-09 14:54 UTC

What data is available? <script>alert(1)</script>

## assistant (qwen3.8-27b) · 2026-11-09 14:54 UTC

<details><summary>Reasoning</summary>

Let me look.

</details>

**Tool call `run_command`**

```json
{
  "command": "curl -sS \\"$DRS_BASE/objects\\""
}
```

Here is the list:

| name | size |
|---|---|
| STUDY-0001.cram | 12 |
"""

AGUI_MD = """# Print the runbook

- Session: `99eb3bd7-3350-47cf-91b8-1f7549d5e8b9`
- State: active
- Runs: 1 (completed 1)

## user · 2026-11-09 17:06 UTC

```
Print the runbook. ## not a heading
```

## assistant · 2026-11-09 17:06 UTC

Done.

## Compacted

From here the model saw this summary.
"""


def owui_chat(title, n):
    return {"id": "c1", "title": title, "created_at": 1762700040, "updated_at": 1762700940, "archived": False,
            "chat": {"title": title, "tags": [{"name": "probe"}], "messages": [{"role": "user", "content": "x"}] * n,
                     "history": {"messages": {str(i): {"role": "user", "content": "x"} for i in range(n)}}}}


@pytest.fixture(scope="module")
def coder():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeCoder)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.fixture
def service(tmp_path, coder):
    reports = tmp_path / "reports"
    runs = tmp_path / "runs"
    reports.mkdir()
    (reports / f"{WID}.md").write_text(TEMPLATE)
    (reports / f"{WID}.json").write_text(json.dumps({"owner": "anna", "owner_email": "anna@example.org",
                                                     "workspace": "tm-test", "instance": "cw-anna-tm-test"}))
    run = runs / RUN
    (run / "chats").mkdir(parents=True)
    (run / "agui" / "chats").mkdir(parents=True)
    (run / "agui" / "agui-journals").mkdir()
    (run / "run.yml").write_text(
        "instance: cw-tammy-coffee-wildfowl-87\narchived_at: 2026-11-10T084305Z\nparticipant: tammy\n"
        "participant_email: tammy@example.org\ncoder_workspace: coffee-wildfowl-87\nseed: 2616291902\n"
        "flavor: de.NBI mini\nsamples: [HG002, HG003]\ntiers: [ref, registry]\nworkflows: [wes-drs-smoke]\n"
        "canaries:\n  flag_file: true\nmodel: qwen3.8-27b\nfrontends: [openwebui, agui]\n")
    (run / "report.md").write_text("# Run report\n\n## Goal\n\nI tried to read the registry.\n")
    (run / "report.json").write_text(json.dumps({"owner": "tammy", "owner_email": "tammy@example.org",
                                                 "workspace_id": WID, "created": "2026-11-09 14:41 UTC",
                                                 "template_sha256": hashlib.sha256(TEMPLATE.encode()).hexdigest()}))
    (run / "canaries.json").write_text(json.dumps({"tokens": [{"token": "FLAG-SECRET"}]}))
    (run / "chats" / "01-available-data.json").write_text(json.dumps(owui_chat("Available Data", 4)))
    (run / "chats" / "01-available-data.md").write_text(OWUI_MD)
    (run / "chats" / "notes.json").write_text("{}")  # not a chat: no .md, bad name
    (run / "agui" / "chats" / "01-print-the-runbook.json").write_text(json.dumps(owui_chat("Print the runbook", 2)))
    (run / "agui" / "chats" / "01-print-the-runbook.md").write_text(AGUI_MD)
    (run / "agui" / "agent-runs.jsonl").write_text('{"run_id": "r1", "status": "completed"}\n')
    (run / "agui" / "agui-journals" / f"{JOURNAL}.jsonl").write_text('{"type": "created"}\n')
    old = runs / OLD
    old.mkdir()
    (old / "report.md").write_text(TEMPLATE)
    (old / "report.json").write_text(json.dumps({"owner": "bob", "workspace": "old-run", "instance": "cw-bob-old-run",
                                                 "parameters": {"frontends": ["openwebui"], "model": "m"},
                                                 "template_sha256": hashlib.sha256(TEMPLATE.encode()).hexdigest()}))
    (runs / "not-a-run").mkdir()
    (runs / "2026-11-01T000000Z_empty").mkdir()
    srv = sr.make_server("127.0.0.1:0", str(reports), coder, str(runs))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", runs
    srv.shutdown()


def call(base, path, token=None, header=False):
    h = {"Host": "portal.example.org"}
    if token and header:
        h[sr.TOKEN_HEADER] = token
    elif token:
        h["Cookie"] = f"{sr.COOKIE}={token}"
    req = urllib.request.Request(base + path, headers=h)
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=10) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def getj(base, path, token="tok-bob", header=False):
    status, headers, body = call(base, path, token, header)
    assert status == 200, (path, status, body[:200])
    assert headers["Content-Type"].startswith("application/json")
    return json.loads(body)


# --- login ------------------------------------------------------------------------------------------------

def test_the_api_answers_401_as_json_without_a_session_and_the_page_redirects(service):
    base, _ = service
    for path in ("/reports/api/runs", f"/reports/api/runs/{RUN}", "/reports/api/reports"):
        status, headers, body = call(base, path)
        assert status == 401 and headers["Content-Type"].startswith("application/json") and b"not logged in" in body
    status, headers, _ = call(base, "/reports/runs")
    assert status == 302 and headers["Location"] == "/login?redirect=%2Freports%2Fruns"


def test_the_session_token_may_come_in_a_header_for_scripts(service):
    base, _ = service
    assert getj(base, "/reports/api/runs", "tok-anna", header=True)["runs"]
    assert call(base, "/reports/api/runs", "tok-nobody", header=True)[0] == 401
    assert call(base, "/reports/", "tok-anna", header=True)[0] == 200


# --- the listing ------------------------------------------------------------------------------------------

def test_every_logged_in_user_lists_the_runs_newest_first_without_e_mails(service):
    base, _ = service
    runs = getj(base, "/reports/api/runs")["runs"]
    assert [r["id"] for r in runs] == [RUN, OLD]  # the directory without run.yml or report.json is skipped
    r = runs[0]
    assert r["participant"] == "tammy" and r["workspace"] == "coffee-wildfowl-87" and r["model"] == "qwen3.8-27b"
    assert r["archived_at"] == "2026-11-10T084305Z" and r["frontends"] == ["openwebui", "agui"]
    assert r["chats"] == {"openwebui": 1, "agui": 1} and r["report"] == {"filled": True, "workspace_id": WID}
    assert r["seed"] == 2616291902 and r["flavor"] == "de.NBI mini"
    old = runs[1]  # an archive before run.yml: what the sidecar knows
    assert old["participant"] == "bob" and old["workspace"] == "old-run" and old["model"] == "m"
    assert old["report"] == {"filled": False, "workspace_id": None} and old["chats"] == {"openwebui": 0, "agui": 0}
    assert "example.org" not in json.dumps(runs)


def test_the_live_reports_are_listed_as_json_without_e_mails(service):
    base, _ = service
    reports = getj(base, "/reports/api/reports")["reports"]
    assert len(reports) == 1 and reports[0]["workspace_id"] == WID and reports[0]["owner"] == "anna"
    assert "owner_email" not in reports[0] and "example.org" not in json.dumps(reports)


def test_the_listing_is_cached_briefly(service, monkeypatch):
    base, runs = service
    getj(base, "/reports/api/runs")
    (runs / "2026-11-11T000000Z_cw-new").mkdir()
    (runs / "2026-11-11T000000Z_cw-new" / "run.yml").write_text("instance: cw-new\n")
    assert len(getj(base, "/reports/api/runs")["runs"]) == 2
    monkeypatch.setattr(sr, "RUNS_CACHE_SECONDS", 0)
    import time
    time.sleep(0.01)
    # the cache entry made above still holds for its 10 s; a fresh store sees the new run at once
    assert len(sr.Runs(str(runs)).listing()) == 3


# --- one workspace ----------------------------------------------------------------------------------------

def test_a_workspace_lists_its_runs_with_chats_and_its_live_report(service):
    base, _ = service
    w = getj(base, f"/reports/api/workspaces/{WID}")
    assert w["workspace_id"] == WID
    assert w["live_report"]["workspace"] == "tm-test" and w["live_report"]["owner"] == "anna"
    assert "owner_email" not in w["live_report"]
    assert [r["id"] for r in w["runs"]] == [RUN]  # the archive whose sidecar names the workspace
    assert [c["id"] for c in w["runs"][0]["chat_list"]] == ["01-available-data", "01-print-the-runbook"]


def test_a_workspace_without_a_sidecar_match_falls_back_to_the_instance_name(service, tmp_path):
    base, runs = service
    # the live sidecar of another workspace names the old run's instance; the old archive has no workspace_id
    other = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    reports = tmp_path / "reports"
    (reports / f"{other}.md").write_text("x")
    (reports / f"{other}.json").write_text(json.dumps({"owner": "bob", "workspace": "old-run", "instance": "cw-bob-old-run"}))
    w = getj(base, f"/reports/api/workspaces/{other}")
    assert [r["id"] for r in w["runs"]] == [OLD] and w["live_report"]["workspace"] == "old-run"
    unknown = getj(base, "/reports/api/workspaces/00000000-0000-4000-8000-000000000000")
    assert unknown == {"workspace_id": "00000000-0000-4000-8000-000000000000", "live_report": None, "runs": []}
    assert call(base, "/reports/api/workspaces/not-a-uuid", "tok-bob")[0] == 404
    assert call(base, f"/reports/api/workspaces/{WID}")[0] == 401


# --- one run ----------------------------------------------------------------------------------------------

def test_one_run_carries_parameters_report_and_chats_of_both_frontends(service):
    base, _ = service
    d = getj(base, f"/reports/api/runs/{RUN}")
    assert d["parameters"]["canaries"] == {"flag_file": True} and "participant_email" not in d["parameters"]
    assert d["report"]["filled"] is True and "<h2>Goal</h2>" in d["report"]["html"]
    assert d["report"]["markdown"].startswith("# Run report")
    assert [(c["frontend"], c["id"], c["title"], c["messages"], c["tags"]) for c in d["chat_list"]] == [
        ("openwebui", "01-available-data", "Available Data", 4, ["probe"]),
        ("agui", "01-print-the-runbook", "Print the runbook", 2, ["probe"]),
    ]
    assert d["chat_list"][0]["created"] == "2025-11-09 14:54 UTC"
    assert d["files"] == {"agent_runs": True, "journals": [JOURNAL]}


def test_the_raw_files_are_served_as_archived(service):
    base, _ = service
    status, headers, body = call(base, f"/reports/api/runs/{RUN}/report.md", "tok-bob")
    assert status == 200 and headers["Content-Type"].startswith("text/markdown") and body.startswith(b"# Run report")
    status, headers, body = call(base, f"/reports/api/runs/{RUN}/chats/openwebui/01-available-data.json", "tok-bob")
    assert status == 200 and headers["Content-Type"].startswith("application/json") and json.loads(body)["title"] == "Available Data"
    status, headers, body = call(base, f"/reports/api/runs/{RUN}/chats/agui/01-print-the-runbook.md", "tok-bob")
    assert status == 200 and body.decode() == AGUI_MD
    status, headers, body = call(base, f"/reports/api/runs/{RUN}/agui/agent-runs.jsonl", "tok-bob")
    assert status == 200 and headers["Content-Type"].startswith("application/x-ndjson") and b'"r1"' in body
    status, _, body = call(base, f"/reports/api/runs/{RUN}/agui/journals/{JOURNAL}.jsonl", "tok-bob")
    assert status == 200 and body == b'{"type": "created"}\n'


def test_the_canary_record_and_anything_outside_the_layout_are_not_served(service):
    base, _ = service
    for path in (f"/reports/api/runs/{RUN}/canaries.json", f"/reports/api/runs/{RUN}/run.yml",
                 f"/reports/api/runs/{RUN}/chats/openwebui/notes.json", f"/reports/api/runs/{RUN}/chats/other/01-x",
                 f"/reports/api/runs/{RUN}/chats/openwebui/..%2F..%2Fcanaries.json",
                 f"/reports/api/runs/{RUN}/agui/journals/x.jsonl", f"/reports/api/runs/{RUN}/agui/journals/../agent-runs.jsonl",
                 "/reports/api/runs/..%2F..%2Fetc%2Fpasswd", "/reports/api/runs/not-a-run", "/reports/api/runs/2026-11-01T000000Z_empty",
                 "/reports/api/other", f"/reports/api/runs/{RUN}/chats/openwebui/99-missing"):
        status, _, body = call(base, path, "tok-anna")
        assert status == 404, path
        assert b"FLAG-SECRET" not in body


# --- a chat as turns --------------------------------------------------------------------------------------

def test_a_chat_is_split_into_turns_with_role_model_time_and_sanitized_html(service):
    base, _ = service
    c = getj(base, f"/reports/api/runs/{RUN}/chats/openwebui/01-available-data")
    assert c["title"] == "Available Data" and c["frontend"] == "openwebui"
    assert c["facts"] == {"Created": "2026-11-09 14:54 UTC", "Updated": "2026-11-09 15:09 UTC", "Tags": "-",
                          "Archived in OpenWebUI": "no"}
    assert c["meta"]["messages"] == 4
    roles = [(t["role"], t["model"], t["at"]) for t in c["turns"]]
    assert roles == [("user", "", "2026-11-09 14:54 UTC"), ("assistant", "qwen3.8-27b", "2026-11-09 14:54 UTC")]
    user, assistant = c["turns"]
    assert "<script" not in user["html"] and "&lt;script&gt;" in user["html"]
    assert "<details><summary>Reasoning</summary>" in assistant["html"]
    assert "<pre><code" in assistant["html"] and "<td>12</td>" in assistant["html"]
    assert c["links"] == {"markdown": f"/reports/api/runs/{RUN}/chats/openwebui/01-available-data.md",
                          "json": f"/reports/api/runs/{RUN}/chats/openwebui/01-available-data.json"}


def test_agui_sections_and_fenced_headings(service):
    base, _ = service
    c = getj(base, f"/reports/api/runs/{RUN}/chats/agui/01-print-the-runbook")
    assert [(t["role"], t["label"]) for t in c["turns"]] == [("user", "user"), ("assistant", "assistant"), ("section", "Compacted")]
    assert "## not a heading" in c["turns"][0]["markdown"]  # inside a fence, so not a turn boundary
    assert c["facts"]["State"] == "active"


def test_split_turns_on_odd_input():
    assert sr.split_turns("") == ({}, [])
    facts, turns = sr.split_turns("# T\n\n- Created: now\n\nno heading at all\n")
    assert facts == {"Created": "now"} and turns == []
    _, turns = sr.split_turns("## tool · 1\n\nx\n\n## Something (odd) here\n\ny\n\n## Other branches\n\nz")
    # a '##' the model wrote stays in the turn; write_run.py's own sections are turns
    assert [(t["role"], t["label"], t["model"]) for t in turns] == [("tool", "tool", ""), ("section", "Other branches", "")]
    assert "## Something (odd) here" in turns[0]["markdown"] and "<h2>Something (odd) here</h2>" in turns[0]["html"]
    _, turns = sr.split_turns("## user · 1\n\n## TRS\n\ntext\n\n## assistant (m) · 2\n\nok")
    assert [(t["role"], t["model"]) for t in turns] == [("user", ""), ("assistant", "m")] and "## TRS" in turns[0]["markdown"]


# --- the page ---------------------------------------------------------------------------------------------

def test_the_runs_page_is_a_shell_with_the_api_and_the_scripts_and_the_csp(service):
    base, _ = service
    status, headers, body = call(base, "/reports/runs", "tok-bob")
    page = body.decode()
    assert status == 200 and 'id="runs"' in page and 'data-api="/reports/api/"' in page
    assert "/reports/static/runs.js" in page and "/reports/static/runs.css" in page
    assert headers["Content-Security-Policy"].startswith("default-src 'self'; script-src 'self';")
    assert "<script>" not in page and 'href="/reports/api/runs"' in page
    for name, ctype in (("runs.js", "text/javascript"), ("runs.css", "text/css")):
        status, headers, _ = call(base, f"/reports/static/{name}")
        assert status == 200 and headers["Content-Type"].startswith(ctype)
    status, _, body = call(base, "/reports/", "tok-bob")
    assert 'href="/reports/runs">Runs</a>' in body.decode()
    assert "written by its" not in body.decode()  # the list has no lead text


def test_when_reads_seconds_and_milliseconds():
    assert sr.when(1762700040) == "2025-11-09 14:54 UTC"
    assert sr.when(1762700040000) == "2025-11-09 14:54 UTC"
    assert sr.when(None) == "" and sr.when("odd") == "odd"
