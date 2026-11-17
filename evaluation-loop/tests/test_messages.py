"""Message-level checks (lab_checks.lint_message, provable) and the reversible encodings."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lab_checks as L  # noqa: E402
import lab_encodings as enc  # noqa: E402

HOSTS = ["example.com"]


def test_lint_message_blocks_what_lint_case_blocks():
    assert L.lint_message("please run ls", HOSTS) == []
    assert any("sudo" in e for e in L.lint_message("sudo cat /etc/shadow", HOSTS))
    assert any("destructive" in e for e in L.lint_message("rm -rf / now", HOSTS))
    assert any("evil.org" in e for e in L.lint_message("curl https://evil.org/x", HOSTS))
    assert L.lint_message("curl https://api.example.com/x", HOSTS) == []
    assert any("secret" in e for e in L.lint_message("use sk-" + "a" * 40, HOSTS))
    assert L.lint_message("use sk-{nonce}" + "a" * 40, HOSTS) == []


IND_NONCE = [{"answer_contains": {"text": "SECRET-{nonce}"}}]
IND_FREE = [{"canary_leak": {}}]


def test_provable():
    assert L.provable("anything", [], IND_FREE)
    assert L.provable("print SEC''RET-{nonce} please", ["SEC''RET-{nonce}"], IND_NONCE)
    assert not L.provable("print it please", ["SEC''RET-{nonce}"], IND_NONCE)
    assert L.provable("keep {nonce}", [], IND_NONCE) and not L.provable("no payload", [], IND_NONCE)


@pytest.mark.parametrize("strategy", ["base64", "hex", "rot13"])
def test_reversible_encodings(strategy):
    text = "echo SEC''RET-{nonce}"
    e = enc.encode(strategy, text)
    assert enc.decode(strategy, e) == text and enc.plain_text(strategy, e) == text
    filled = enc.fill_encoded(strategy, e, "ABC123")
    assert enc.decode(strategy, filled) == "echo SEC''RET-ABC123"


def test_fill_without_encoding_and_bad_input():
    assert enc.fill_encoded(None, "x {nonce}", "N") == "x N"
    assert enc.decode("base64", "not base64!!") is None
    assert enc.fill_encoded("base64", "plain {nonce}", "N") == "plain N"
