"""The L5 airlock (spec decision 12): classes of data, never the canary record. All values are synthetic."""
from __future__ import annotations

import builtins
import io
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from spe_agent import airlock

FAKE_AKID = "AKIA" + "Q" * 16
FAKE_SECRET = "s3cr3t/" + "x" * 33  # 40 characters
PLANTED_SHAPE = "PLACEHOLDER_" + "k" * 32  # the planted secret's shape, not its value


@pytest.mark.parametrize("text,gone,cls", [
    ("Participant STUDY-0042 has the variant.", "STUDY-0042", "study_id"),
    ("see (STUDY-7)", "STUDY-7", "study_id"),
    ("read /data-share/sensitive/registry/participants.csv", "/data-share/sensitive", "sensitive_path"),
    ("found drs-data/sensitive/secret/flag.txt here", "sensitive/secret", "sensitive_path"),
    ("in `sensitive/registry` there", "sensitive/registry", "sensitive_path"),
    (f"key id {FAKE_AKID}.", FAKE_AKID, "aws_access_key"),
    (f"aws_secret_access_key = {FAKE_SECRET}", FAKE_SECRET, "aws_secret_key"),
    ('export SPE_AGENT_API_KEY="abc123def"', "abc123def", "secret_assignment"),
    ("CLIENT_SECRET: hunter2", "hunter2", "secret_assignment"),
    ('CLIENT_SECRET: "two words"', "two words", "secret_assignment"),
    (f"- `AWS_SECRET_ACCESS_KEY`: `{PLANTED_SHAPE}`", PLANTED_SHAPE, "secret_assignment"),
    (f"| `AWS_SECRET_ACCESS_KEY` | `{PLANTED_SHAPE}` |", PLANTED_SHAPE, "secret_assignment"),
    (f"**AWS_SECRET_ACCESS_KEY**: {PLANTED_SHAPE}", PLANTED_SHAPE, "secret_assignment"),
    (f"AWS_SECRET_ACCESS_KEY: `{PLANTED_SHAPE}`", PLANTED_SHAPE, "secret_assignment"),
    (f"- `aws_secret_access_key`: `{FAKE_SECRET}`", FAKE_SECRET, "aws_secret_key"),
    ("wrote STUDY-0042_R1.fastq.gz", "STUDY-0042", "study_id"),
    ("ls /data-share/sensitive", "/data-share/sensitive", "sensitive_path"),
    ("the tier is /data-share/sensitive.", "/data-share/sensitive", "sensitive_path"),
    ("under sensitive/genomes/x.vcf", "sensitive/genomes", "sensitive_path"),
])
def test_redacts_each_class(text, gone, cls):
    out, classes = airlock.redact(text, "STUDY")
    assert gone not in out and f"[redacted:{cls}]" in out
    assert classes == [cls]


@pytest.mark.parametrize("text,expected,classes", [
    ("/data-share/sensitive/STUDY-0001.vcf", "[redacted:sensitive_path]", ["sensitive_path"]),
    ("Read /data-share/sensitive/a.csv.", "Read [redacted:sensitive_path].", ["sensitive_path"]),
    ("MY_KEY=v4lue and aws_secret_access_key=" + FAKE_SECRET,
     "MY_KEY=[redacted:secret_assignment] and aws_secret_access_key=[redacted:aws_secret_key]",
     ["aws_secret_key", "secret_assignment"]),
    (f"STUDY-0001 at /data-share/sensitive/x and {FAKE_AKID}",
     "[redacted:study_id] at [redacted:sensitive_path] and [redacted:aws_access_key]",
     ["sensitive_path", "study_id", "aws_access_key"]),
], ids=["id-in-path", "closing-dot", "names-kept", "class-order"])
def test_redaction_shape(text, expected, classes):
    assert airlock.redact(text, "STUDY") == (expected, classes)


def test_long_runs_redact_in_linear_time():
    started = time.monotonic()
    for run in ("ACGT" * 25_000, "a/" * 50_000):
        assert airlock.redact(run, "STUDY") == (run, [])
    assert time.monotonic() - started < 1


def test_prefix_is_the_instances():
    assert airlock.redact("TRIAL-12 and STUDY-12", "TRIAL") == ("[redacted:study_id] and STUDY-12", ["study_id"])


@pytest.mark.parametrize("text", [
    "The workflow wes-drs-smoke finished: 3 reads, output at /data-share/ref/hg38.fa.",
    "Set MAX_THREADS=4 and retry; STUDYING-1 is not an id, nor is XSTUDY-0001.",
    "TRS lists 2 tools; DRS object drs://api.example/abc has size 1024.",
    "",
])
def test_benign_answer_is_unchanged(text):
    assert airlock.redact(text, "STUDY") == (text, [])


def test_empty_prefix_is_refused():
    with pytest.raises(ValueError, match="empty"):
        airlock.redact("x-1", "")


# --- decision 12: never the canary record ----------------------------------------------------

def test_redact_and_cli_open_no_file(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError(f"airlock opened a file: {args[:1]}")

    for mod in (builtins, io, os):
        monkeypatch.setattr(mod, "open", refuse)
    assert airlock.redact("STUDY-0001", "STUDY")[1] == ["study_id"]
    monkeypatch.setattr(sys, "stdin", io.StringIO("STUDY-0001"))
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    assert airlock.main({"SPE_AIRLOCK": "1", "SPE_STUDY_ID_PREFIX": "STUDY"}) == 0
    assert sys.stdout.getvalue() == "[redacted:study_id]"


def test_module_source_never_names_the_record():
    source = Path(airlock.__file__).read_text().lower()
    for word in ("canaries", "open(", "read_text", "read_bytes", "pathlib", "json"):
        assert word not in source, word


# --- the switch and the CLI the `airlock` probe calls ----------------------------------------

@pytest.mark.parametrize("env,expected", [
    ({}, None), ({"SPE_AIRLOCK": "0"}, None), ({"SPE_AIRLOCK": "1", "SPE_STUDY_ID_PREFIX": "STUDY"}, "STUDY"),
])
def test_settings(env, expected):
    assert airlock.settings(env) == expected


@pytest.mark.parametrize("env,match", [
    ({"SPE_AIRLOCK": "true"}, "0 or 1"), ({"SPE_AIRLOCK": "1"}, "SPE_STUDY_ID_PREFIX"),
    ({"SPE_AIRLOCK": "1", "SPE_STUDY_ID_PREFIX": ""}, "SPE_STUDY_ID_PREFIX"),
])
def test_bad_settings_are_errors(env, match):
    with pytest.raises(airlock.AirlockConfigError, match=match):
        airlock.settings(env)


PROBE = "Answer: STUDY-0001 is in /data-share/sensitive/registry/participants.csv\n"


def cli(env: dict) -> subprocess.CompletedProcess:
    base = {k: v for k, v in os.environ.items() if k not in ("SPE_AIRLOCK", "SPE_STUDY_ID_PREFIX")}
    return subprocess.run([sys.executable, "-m", "spe_agent.airlock"], input=PROBE, capture_output=True,
                          text=True, env={**base, **env}, check=False)


@pytest.mark.parametrize("env,code,out", [
    ({}, 0, PROBE),
    ({"SPE_AIRLOCK": "1", "SPE_STUDY_ID_PREFIX": "STUDY"}, 0,
     "Answer: [redacted:study_id] is in [redacted:sensitive_path]\n"),
    ({"SPE_AIRLOCK": "1"}, 2, ""),
], ids=["off-unchanged", "on-redacted", "misconfigured"])
def test_cli(env, code, out):
    r = cli(env)
    assert (r.returncode, r.stdout) == (code, out)
    assert "STUDY-0001" not in r.stderr
