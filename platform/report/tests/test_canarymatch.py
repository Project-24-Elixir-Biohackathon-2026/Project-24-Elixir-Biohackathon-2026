"""canarymatch.py (whether and where a canary token is in a text) and canary_record.py (the
canaries.json / hosts.yml readers), moved out of platform/promptfoo-evals so the canary hit viewer's
watcher can use them without importing it (decision 2). No real canaries.json is ever read: every
token here is a made-up fixture value."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import canarymatch  # noqa: E402
import canary_record  # noqa: E402

FCANARY = "FCANARY-TEST01"
MCANARY = "MCANARY-TEST02"


def test_texts_reads_escaped_and_json():
    readings = canarymatch.texts(json.dumps({"a": "x\n" + FCANARY}))
    assert any(canarymatch.word(FCANARY).search(t) for t in readings)


def test_word_is_whole_word():
    assert canarymatch.word(FCANARY).search(FCANARY + "1") is None
    assert canarymatch.word(FCANARY).search(FCANARY) is not None


def test_spans_positions():
    assert canarymatch.spans(FCANARY, f"ab {FCANARY} c") == [(3, 17)]


def test_received_form_decoded():
    readings = canarymatch.received({"path": f"/x?q={FCANARY.replace('-', '%2D')}", "body": None})
    assert any(canarymatch.word(FCANARY).search(t) for t in readings)


def test_hosts():
    assert canarymatch.hosts("see https://Evil.Example/upload and $VAR here") == {"evil.example"}
    assert canarymatch.hosts("no url here") == set()


def test_is_file_canary():
    # Take the type names from the canary evaluation's METADATA_TYPES as it is now (one is a metadata type, never
    # a file canary; a drs-… type is a metadata type).
    assert canarymatch.is_file_canary({"type": "drs-object-metadata"}) is False
    assert canarymatch.is_file_canary({"type": "flag-file"}) is True


def write_hosts(directory: Path, record: dict) -> None:
    lines = []
    for key, value in record.items():
        if isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                lines += [f"- {v}" for v in value]
        elif isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        elif value is None:
            lines.append(f"{key}:")
        else:
            lines.append(f"{key}: {value}")
    (directory / "hosts.yml").write_text("\n".join(lines) + "\n")


def test_record_readers(tmp_path):
    hosts_record = {"instance": "ladder-l0", "api_host": "10.0.0.5", "ssh_user": "ubuntu",
                     "provision": "existing", "ssh_target": "localhost", "ssh_key": "", "ssh_args": "",
                     "frontends": ["agui"]}
    write_hosts(tmp_path, hosts_record)
    # An empty scalar ("key: ") reads back as None (_scalar's rule), not the empty string written.
    expected = {**hosts_record, "ssh_key": None, "ssh_args": None}
    assert canary_record.read_hosts(tmp_path) == expected

    tokens = [{"token": FCANARY, "type": "flag-file", "file": "sensitive/secret/x"},
              {"token": MCANARY, "type": "drs-object-metadata", "file": "drs:obj-1"}]
    (tmp_path / "canaries.json").write_text(json.dumps({"tokens": tokens}))
    loaded = canary_record.load_canaries(tmp_path)
    assert loaded == tokens
    assert [canarymatch.is_file_canary(t) for t in loaded] == [True, False]

    (tmp_path / "canaries.json").unlink()
    (tmp_path / "canaries.json.age").write_text("encrypted")
    with pytest.raises(canary_record.RecordError, match="age-encrypted"):
        canary_record.load_canaries(tmp_path)
