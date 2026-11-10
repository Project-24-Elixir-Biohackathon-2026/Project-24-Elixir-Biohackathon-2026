"""hits_view.py: the participant page's body and a standalone HTML document (spec *Participant
page*; decisions 4, 5, 11). Hit dicts here are hand-built to the schema in canary_hits.hits_for,
not read from fixtures, since these tests check rendering only. Tokens are made-up
(FCANARY-TEST01)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hits_view  # noqa: E402
from hits_view import NOTICE, participant_body, standalone  # noqa: E402

META = {"workspace": "6f1c2a9e-3b7d-4e1a-9c2f-0a1b2c3d4e5f", "instance": "fixture", "owner": "alice"}


def hit(kind: str, place: str, **fields) -> dict:
    base = {
        "id": 1, "detected": "2026-11-10T14:03:07Z", "at": "2026-11-10T14:03:05Z",
        "workspace": META["workspace"], "instance": META["instance"], "owner": META["owner"],
        "frontend": "agui", "source": "agui-journal",
        "session": {"id": "s1", "title": "Variant QC"}, "run": "r1",
        "prompt": "Summarise the variants", "kind": kind, "place": place, "tool": None,
        "canary": {"type": "vcf-canary-variant", "file": "sensitive/genomes/truth.vcf.gz",
                   "token": "FCANARY-TEST01"},
        "excerpt": {"text": "chr1 10583 FCANARY-TEST01 G A", "start": 11, "end": 25},
    }
    return base | fields


def test_notice_on_participant_page():
    body = participant_body(META, [], None)
    assert NOTICE in body


def test_counts_loud_and_quiet():
    hits = (
        [hit("touched", "tool_result") for _ in range(2)]
        + [hit("answer", "answer")]
        + [hit("seen", "tool_result") for _ in range(3)]
    )
    body = participant_body(META, hits, None)
    assert "3 leaks" in body
    assert "also seen: 3" in body


def test_frontend_labels():
    hits = [hit("touched", "tool_result", frontend="agui"),
            hit("touched", "tool_result", frontend="openwebui")]
    body = participant_body(META, hits, None)
    assert "AG-UI" in body
    assert "Open WebUI" in body


def test_value_marked():
    body = participant_body(META, [hit("touched", "tool_result")], None)
    assert "<mark>FCANARY-TEST01</mark>" in body


def test_escapes_fields():
    hits = [hit("answer", "answer", session={"id": "s1", "title": "<script>x</script>"})]
    body = participant_body(META, hits, None)
    assert "<script>x</script>" not in body
    assert "&lt;script&gt;x&lt;/script&gt;" in body


def test_standalone_has_no_script_and_inlines_css():
    body = participant_body(META, [hit("touched", "tool_result")], None)
    doc = standalone("Canary hits", body)
    assert "<script" not in doc
    assert "<style>" in doc
    assert "<mark>FCANARY-TEST01</mark>" in doc


def test_archived_status_none_says_archived():
    body = participant_body(META, [], None)
    assert "archived" in body.lower()


def _also_seen_block(body: str) -> str:
    start = body.index('<details class="also-seen">')
    end = body.index("</details></section>", start)
    return body[start:end]


def test_quiet_kinds_listed_under_also_seen():
    hits = [hit("touched", "tool_result", at="2026-11-10T14:00:00Z"),
            hit("seen", "tool_result", at="2026-11-10T14:05:00Z", run="rQUIET")]
    body = participant_body(META, hits, None)
    assert "<summary>also seen (1)</summary>" in body
    block = _also_seen_block(body)
    assert "run rQUIET" in block
    assert body.count("run rQUIET") == 1  # only inside the block
    # loud hits come first, before the block
    assert body.index("kind-touched") < body.index('<details class="also-seen">')


def test_no_also_seen_block_without_quiet_hits():
    body = participant_body(META, [hit("touched", "tool_result")], None)
    assert 'class="also-seen"><summary>' not in body
    assert "<details class=\"also-seen\"" not in body


def test_quiet_hits_newest_first():
    hits = [hit("args", "tool_args", at="2026-11-10T14:00:00Z", run="rOLD"),
            hit("prompt", "prompt", at="2026-11-10T14:09:00Z", run="rNEW")]
    block = _also_seen_block(participant_body(META, hits, None))
    assert block.index("run rNEW") < block.index("run rOLD")


def test_headline_labels_seen_as_metadata():
    hits = [hit("seen", "tool_result"), hit("args", "tool_args"), hit("prompt", "prompt")]
    body = participant_body(META, hits, None)
    assert "also seen: 3 (metadata, args, prompt)" in body


def test_unknown_or_null_kind_counted_under_also_seen():
    hits = [hit("touched", "tool_result"), hit("bogus", "x", run="rBOGUS"), hit(None, "x", run="rNULL")]
    body = participant_body(META, hits, None)
    assert "1 leak" in body
    assert "also seen: 2" in body
    assert "<summary>also seen (2)</summary>" in body
    block = _also_seen_block(body)
    assert "run rBOGUS" in block and "run rNULL" in block


def test_status_text_escaped_once():
    body = participant_body(META, [], "a & b")  # not a dict: the fallback
    assert "a &amp; b" in body
    assert "&amp;amp;" not in body


def test_placeholder_class_on_no_hits_and_not_watched_only():
    # NO_HITS: hits.js removes this on the first live hit (p.placeholder).
    archived = participant_body(META, [], None)
    assert 'class="muted placeholder"' in archived
    # NOT_WATCHED: a dict status with no state yet.
    not_watched = participant_body(META, [], {})
    assert 'class="muted placeholder"' in not_watched
    # The encrypted notice is never removed by a live hit, so it stays plain "muted".
    encrypted = participant_body(META, [], {"state": "encrypted"})
    assert 'class="muted placeholder"' not in encrypted
    assert 'class="muted">' in encrypted


HOSTILE = "<img src=x onerror=alert(1)>"


def test_hostile_fields_escaped_everywhere():
    text = f"{HOSTILE} FCANARY-TEST01 {HOSTILE}"
    start = text.index("FCANARY")
    h = hit("touched", "tool_result", prompt=HOSTILE,
            tool={"name": "read_file", "call_id": "c1", "args": HOSTILE, "result": HOSTILE},
            canary={"type": "vcf-canary-variant", "file": HOSTILE, "token": "FCANARY-TEST01"},
            excerpt={"text": text, "start": start, "end": start + len("FCANARY-TEST01")})
    for kind in ("touched", "seen"):
        doc = standalone("Canary hits", participant_body(META, [h | {"kind": kind}], None))
        assert "<img" not in doc
        assert "&lt;img src=x onerror=alert(1)&gt;" in doc
        assert doc.count("&lt;img") >= 6  # excerpt x2, prompt, args, result, file
        assert "<mark>FCANARY-TEST01</mark>" in doc


# --- hit_html, LOUD, status_line (the event stream renders each hit as the page does) ---

import calendar  # noqa: E402
import time  # noqa: E402

import pytest  # noqa: E402


def test_loud_kinds():
    assert hits_view.LOUD == {"answer", "sent", "delivered", "touched"}


def test_hit_html_data_attributes_escaped():
    h = hit("touched", "tool_result", id=7, session={"id": 's"1<', "title": "t"}, run='r"&1')
    out = hits_view.hit_html(h)
    assert out.startswith('<details class="hit loud" data-id="7" data-kind="touched" '
                          'data-session="s&quot;1&lt;" data-run="r&quot;&amp;1">')
    assert hits_view.hit_html(hit("seen", "tool_result")).startswith('<details class="hit quiet"')


def test_participant_body_uses_hit_html():
    hits = [hit("touched", "tool_result", id=1), hit("seen", "tool_result", id=2, at="2026-11-10T14:03:01Z")]
    body = participant_body(META, hits, {})
    for h in hits:
        assert hits_view.hit_html(h) in body


NOW = calendar.timegm(time.strptime("2026-11-10T14:03:10Z", "%Y-%m-%dT%H:%M:%SZ"))


@pytest.mark.parametrize("status, line", [
    ({"state": "running", "last_poll": "2026-11-10T14:03:07Z"}, "running · watched 3 s ago"),
    ({"state": "running"}, "running"),
    ({"state": "unreachable", "since": "2026-11-10T14:02:00Z"}, "not reachable since 14:02"),
    ({"state": "unreachable"}, "not reachable"),
    ({"state": "capped"}, "hits file full"),
    ({"state": "capped", "note": "10 MB"}, "hits file full · 10 MB"),
    ({"state": "capped", "note": "hits file full"}, "hits file full"),  # the watcher's own note
    ({"state": "stopped", "note": "archive incomplete"}, "stopped · archive incomplete"),
    ({"state": "encrypted"}, "canary record is encrypted"),
    ({}, "not watched yet"),
    (None, "not watched yet"),
])
def test_status_line(status, line):
    assert hits_view.status_line(status, NOW) == line


@pytest.mark.parametrize("status, text", [
    ({"state": "encrypted"}, hits_view.ENCRYPTED_NOTICE),
    ({"state": "running"}, hits_view.NO_HITS),
    ({"state": "stopped", "note": "archive incomplete"}, hits_view.NO_HITS),
    ({}, hits_view.NOT_WATCHED),  # discovered but never polled
    (None, hits_view.NO_HITS),  # the early output: an archived run, never live
])
def test_empty_text(status, text):
    assert hits_view.empty_text(status) == text
