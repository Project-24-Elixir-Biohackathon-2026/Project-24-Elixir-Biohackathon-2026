"""trs_install.py: canaries and injections planted from tool.yml, idempotently, against a fake TRS."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

PLATFORM = Path(__file__).resolve().parents[2]
SCRIPT = PLATFORM / "ansible" / "roles" / "trs_install" / "files" / "trs_install.py"
CATALOG = PLATFORM / "ansible" / "catalog" / "workflows"
INJECTIONS = PLATFORM / "ansible" / "catalog" / "injections"
DESC = INJECTIONS / "registry-preflight.txt"
COMMENT = INJECTIONS / "workflow-preflight.txt"


def load():
    spec = importlib.util.spec_from_file_location("trs_install", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def tr(monkeypatch):
    mod = load()
    mod.calls = {}
    monkeypatch.setattr(mod, "put", lambda base, path, body: mod.calls.__setitem__(path, body) or 200)
    return mod


def run(tr, monkeypatch, capsys, *extra, canaries=True):
    argv = ["trs_install.py", "--catalog", str(CATALOG), "--api", "https://h/ga4gh/trs/v2", "--seed", "11",
            "--workflow", "wes-drs-smoke", "--workflow", "gatk-hc-chr20", *extra]
    if canaries:
        argv += ["--canary-descriptions", "--canary-comments"]
    monkeypatch.setattr(sys, "argv", argv)
    tr.calls.clear()
    assert tr.main() == 0
    return json.loads(capsys.readouterr().out), dict(tr.calls)


def descriptor(calls, tool):
    return calls[f"/tools/{tool}/versions/v1"]["files"][0]["file_wrapper"]["content"]


def strip_comments(text):
    return [line for line in text.splitlines() if not line.startswith("//")]


def test_all_off_keeps_todays_fields(tr, monkeypatch, capsys):
    out, calls = run(tr, monkeypatch, capsys)
    assert out["injections"] == []
    meta = yaml.safe_load((CATALOG / "gatk-hc-chr20" / "tool.yml").read_text())
    token = next(c["token"] for c in out["canaries"] if c["file"] == "trs:gatk-hc-chr20")
    assert calls["/tools/gatk-hc-chr20"]["description"] == f"{meta['description']} [ref {token}]"
    original = (CATALOG / "gatk-hc-chr20" / "main.nf").read_text().splitlines()
    lines = descriptor(calls, "gatk-hc-chr20").splitlines()
    assert lines[0] == original[0] == "nextflow.enable.dsl=2"
    assert lines[1].startswith("// provenance-id: WFCANARY-")
    assert lines[2:] == original[1:]


def test_description_injection_lands_only_in_the_selected_tool(tr, monkeypatch, capsys):
    out, calls = run(tr, monkeypatch, capsys, "--inject-description", "desc-1", str(DESC), "gatk-hc-chr20")
    payload = DESC.read_text().strip()
    description = calls["/tools/gatk-hc-chr20"]["description"]
    assert description.endswith("\n\n" + payload) and description.count(payload) == 1
    assert "[ref TRSMETA-" in description
    assert payload not in calls["/tools/wes-drs-smoke"]["description"]
    assert payload not in descriptor(calls, "gatk-hc-chr20")
    assert out["injections"] == [{"id": "desc-1", "surface": "trs-description",
                                  "payload_sha256": hashlib.sha256(DESC.read_bytes()).hexdigest(),
                                  "location": {"tool_id": "gatk-hc-chr20", "field": "description"}}]


def test_comment_injection_wraps_every_line_and_keeps_the_code(tr, monkeypatch, capsys):
    out, calls = run(tr, monkeypatch, capsys, "--inject-comment", "comment-1", str(COMMENT), "gatk-hc-chr20")
    text = descriptor(calls, "gatk-hc-chr20")
    lines = text.splitlines()
    assert lines[0] == "nextflow.enable.dsl=2"
    for line in COMMENT.read_text().strip().splitlines():
        assert f"// {line}" in lines
    assert strip_comments(text) == strip_comments((CATALOG / "gatk-hc-chr20" / "main.nf").read_text())
    assert COMMENT.read_text().strip() not in descriptor(calls, "wes-drs-smoke")
    assert out["injections"] == [{"id": "comment-1", "surface": "workflow-comment",
                                  "payload_sha256": hashlib.sha256(COMMENT.read_bytes()).hexdigest(),
                                  "location": {"tool_id": "gatk-hc-chr20", "version": "v1",
                                               "descriptor_type": "NFL", "path": "main.nf"}}]


def test_two_description_injections_on_one_tool_both_land_in_order(tr, monkeypatch, capsys):
    out, calls = run(tr, monkeypatch, capsys, "--inject-description", "desc-1", str(DESC), "gatk-hc-chr20",
                     "--inject-description", "desc-2", str(COMMENT), "gatk-hc-chr20")
    description = calls["/tools/gatk-hc-chr20"]["description"]
    desc_payload, comment_payload = DESC.read_text().strip(), COMMENT.read_text().strip()
    assert description.endswith(f"\n\n{desc_payload}\n\n{comment_payload}")
    assert [i["id"] for i in out["injections"]] == ["desc-1", "desc-2"]
    assert all(i["surface"] == "trs-description" for i in out["injections"])


def test_both_on_keep_canaries_and_rerun_is_identical(tr, monkeypatch, capsys):
    off, _ = run(tr, monkeypatch, capsys)
    flags = ["--inject-description", "desc-1", str(DESC), "gatk-hc-chr20",
             "--inject-comment", "comment-1", str(COMMENT), "gatk-hc-chr20"]
    first, calls1 = run(tr, monkeypatch, capsys, *flags)
    second, calls2 = run(tr, monkeypatch, capsys, *flags)
    assert first["canaries"] == off["canaries"]
    assert calls1 == calls2 and first == second
    assert [i["surface"] for i in first["injections"]] == ["trs-description", "workflow-comment"]
    assert all(t["token"] in json.dumps(calls1) for t in first["canaries"])


def test_unknown_tool_fails_before_any_put(tr, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["trs_install.py", "--catalog", str(CATALOG), "--api", "https://h",
                                      "--seed", "1", "--workflow", "wes-drs-smoke",
                                      "--inject-description", "desc-1", str(DESC), "gatk-hc-chr20"])
    tr.calls.clear()
    with pytest.raises(RuntimeError, match="desc-1.*gatk-hc-chr20"):
        tr.main()
    assert tr.calls == {}


def test_inject_flags_need_exactly_id_payload_tool_id(tr, monkeypatch):
    # --inject-description/--inject-comment take exactly ID PAYLOAD TOOL_ID (nargs=3, module
    # docstring): an --inject-comment given only a payload, with no id or tool, is refused by
    # argparse instead of being accepted with the wrong arity.
    monkeypatch.setattr(sys, "argv", ["trs_install.py", "--catalog", str(CATALOG), "--api", "https://h",
                                      "--seed", "1", "--inject-comment", str(COMMENT)])
    with pytest.raises(SystemExit):
        tr.main()


def test_inject_description_with_two_args_is_also_refused(tr, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["trs_install.py", "--catalog", str(CATALOG), "--api", "https://h",
                                      "--seed", "1", "--inject-description", "desc-1", str(DESC)])
    with pytest.raises(SystemExit):
        tr.main()


def test_empty_payload_fails(tr, tmp_path):
    empty = tmp_path / "empty.txt"
    empty.write_text("\n")
    with pytest.raises(ValueError, match="empty"):
        tr.read_payload(str(empty))


def test_wrapping_keeps_shebang_and_directives(tr):
    src = "#!/usr/bin/env nextflow\nnextflow.enable.dsl=2\nnextflow.preview.topic=true\nworkflow { run() }\n"
    out = tr.build_descriptor(src, "NFL", token="WFCANARY-AAAAAAAA", payloads=["line one\n\nline two"])
    assert out.splitlines() == ["#!/usr/bin/env nextflow", "nextflow.enable.dsl=2", "nextflow.preview.topic=true",
                                "// provenance-id: WFCANARY-AAAAAAAA", "// line one", "//", "// line two",
                                "workflow { run() }"]
    assert tr.build_descriptor("rule all:\n  input: 'x'\n", "SMK", payloads=["p"]).splitlines() == [
        "# p", "rule all:", "  input: 'x'"]
    assert tr.build_descriptor("rule all:\n  input: 'x'\n", "SMK", payloads=["p", "q"]).splitlines() == [
        "# p", "# q", "rule all:", "  input: 'x'"]
