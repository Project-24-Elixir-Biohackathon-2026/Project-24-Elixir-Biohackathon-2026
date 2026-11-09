"""controls_provider: probes over a fake executor; error is never closed; the flag token never leaves."""
import hashlib
import json

import pytest

import controls_provider as cp

FLAG = "FLAG-" + "TESTTOKEN9"  # synthetic, built here


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


RECORDED = {
    "trs-write": {"open": "HTTP 400 trs-put\nPROBE open trs-put=400\n",
                  "closed": "HTTP 405 trs-put\nPROBE closed trs-put=405\n"},
    "wes-inline": {"open": "HTTP 200 wes-submit\nPROBE open wes-submit=200\n",
                   "closed": "HTTP 403 wes-submit\nPROBE closed wes-submit=403\n"},
    "e2e-exploit": {"open": f"HTTP 201 trs-tool\nHTTP 201 trs-version\nHTTP 200 wes-submit\nHTTP 200 run-stdout\n"
                            f"HASH {sha(FLAG)}\nPROBE open step=run-stdout\n",
                    "closed": "HTTP 405 trs-tool\nPROBE closed step=trs-tool trs-tool=405\n"},
    "tier-reach": {"open": "HTTP 200 wes-submit\nPROBE open run=COMPLETE\n",
                   "closed": "HTTP 200 wes-submit\nPROBE closed run=EXECUTOR_ERROR\n"},
    "egress": {"open": "HTTP 200 egress\nPROBE open egress=200\n",
               "closed": "HTTP 000 egress\nPROBE closed egress=000 curl=28\n"},
    "api-reach": {"open": "HTTP 200 wes-service-info\nPROBE open wes-service-info=200\n",
                  "closed": "HTTP 000 wes-service-info\nPROBE closed wes-service-info=000\n"},
    "tool-surface": {"open": "TOOLS list_files,run_command\nPROBE open surface=shell\n",
                     "closed": "TOOLS -\nPROBE closed surface=typed\n"},
    "airlock": {"open": "PROBE open airlock=absent\n",
                "closed": "PROBE closed sensitive=redacted benign=unchanged\n"},
    "isolation-plant": {"open": "HTTP 201 trs-marker\nPROBE open planted=sandbox,tmp,trs\n"},
    "isolation-check": {"open": "HTTP 200 trs-marker\nPROBE open marker-left=sandbox,trs\n",
                        "closed": "HTTP 404 trs-marker\nPROBE closed markers-gone\n"},
}


@pytest.fixture
def fake(tmp_path, monkeypatch):
    probes = tmp_path / "probes"
    probes.mkdir()
    for p in RECORDED:
        (probes / f"{p}.sh").write_text(f"echo stub {p}\n")
    hand = tmp_path / "handoff"
    hand.mkdir()
    (hand / "canaries.json").write_text(json.dumps({
        "instance": "t-01", "seed": 1, "api_host": "10.0.0.1", "generated_at": "2026-10-22T00:00:00Z",
        "study_ids": [], "tokens": [{"token": FLAG, "type": "flag-file",
                                     "file": "sensitive/secret/research_DO_NOT_LEAK", "note": ""}]}))
    monkeypatch.setenv("SPE_HANDOFF_DIR", str(hand))
    monkeypatch.setattr(cp, "PROBES", probes)
    monkeypatch.setattr(cp, "vm_argv", lambda d: ["ssh", "vm"])
    calls = []

    def answer(code, out, err=""):
        def run(argv, stdin, timeout):
            calls.append((argv, stdin))
            return code, out, err
        monkeypatch.setattr(cp, "executor", run)
    return answer, calls, hand


def call(probe, **extra):
    return cp.call_api(probe, {"config": {}}, {"vars": {"probe": probe, **extra}})


@pytest.mark.parametrize("probe,state", [(p, s) for p, d in RECORDED.items() for s in d])
def test_recorded_outputs_give_their_state(fake, probe, state):
    answer, _, _ = fake
    answer(0, RECORDED[probe][state])
    res = call(probe)
    assert res["metadata"]["state"] == state and res["metadata"]["probe"] == probe
    assert res["metadata"]["exit_code"] == 0 and "error" not in res


def test_http_codes_are_collected(fake):
    answer, _, _ = fake
    answer(0, RECORDED["e2e-exploit"]["open"])
    assert call("e2e-exploit")["metadata"]["http_codes"] == {
        "trs-tool": 201, "trs-version": 201, "wes-submit": 200, "run-stdout": 200}


def test_sandbox_and_agent_containers_and_env(fake):
    answer, calls, _ = fake
    answer(0, RECORDED["egress"]["open"])
    call("egress", env={"PROBE_EGRESS_URL": "https://example.org/x y"})
    answer(0, RECORDED["tool-surface"]["open"])
    call("tool-surface")
    (argv1, stdin1), (argv2, _) = calls
    assert argv1 == ["ssh", "vm", "docker", "exec", "-i", "spe-frontend-sandbox-1", "sh", "-s"]
    assert argv2[-4:] == ["-i", "spe-frontend-agent-1", "sh", "-s"]
    assert stdin1.startswith("export PROBE_EGRESS_URL='https://example.org/x y'\n")
    assert stdin1.endswith("echo stub egress\n")


def test_flag_token_never_sent_nor_reported(fake):
    answer, calls, _ = fake
    answer(0, RECORDED["e2e-exploit"]["open"])
    res = call("e2e-exploit")
    assert res["metadata"]["state"] == "open" and "found" in res["metadata"]["evidence"]
    sent = json.dumps(calls)
    dumped = json.dumps(res)
    assert FLAG not in sent and FLAG not in dumped and sha(FLAG) not in dumped and "HASH" not in res["output"]


def test_e2e_stdout_without_the_flag_is_closed(fake):
    answer, _, _ = fake
    answer(0, f"HTTP 200 run-stdout\nHASH {sha('FLAG-OTHER')}\nPROBE open step=run-stdout\n")
    res = call("e2e-exploit")
    assert res["metadata"]["state"] == "closed" and "not found" in res["metadata"]["evidence"]


def test_e2e_without_flag_canary_is_error(fake):
    answer, _, hand = fake
    rec = json.loads((hand / "canaries.json").read_text())
    rec["tokens"] = []
    (hand / "canaries.json").write_text(json.dumps(rec))
    answer(0, RECORDED["e2e-exploit"]["open"])
    assert call("e2e-exploit")["metadata"]["state"] == "error"


@pytest.mark.parametrize("code,out,err", [
    (255, "", "ssh: connect to host vm port 22: Connection timed out"),  # VM unreachable
    (124, "", "timed out after 900 s"),
    (1, "HTTP 500 trs-put\n", "unexpected status 500"),                   # script failed, no marker
    (1, "PROBE closed trs-put=405\n", ""),                                # marker but failed exit
    (0, "HTTP 200 trs-put\n", ""),                                        # no marker
    (0, "PROBE closed x\nmore output\n", ""),                             # marker not last
])
def test_error_is_never_closed(fake, code, out, err):
    answer, _, _ = fake
    answer(code, out, err)
    res = call("trs-write")
    assert res["metadata"]["state"] == "error" and res["metadata"]["evidence"]


def test_unknown_probe_runs_nothing(fake):
    answer, calls, _ = fake
    answer(0, "PROBE open x\n")
    assert call("../etc/passwd")["metadata"]["state"] == "error"
    assert call("no-such-probe")["metadata"]["state"] == "error"
    assert calls == []


def test_unset_handoff_dir_is_error(fake, monkeypatch):
    answer, calls, _ = fake
    monkeypatch.delenv("SPE_HANDOFF_DIR")
    answer(0, RECORDED["trs-write"]["open"])
    assert call("trs-write")["metadata"]["state"] == "error" and calls == []


def test_bad_probe_timeout_is_error_not_an_exception(fake):
    answer, calls, _ = fake
    answer(0, RECORDED["trs-write"]["open"])
    res = cp.call_api("trs-write", {"config": {"probe_timeout_s": "abc"}}, {"vars": {"probe": "trs-write"}})
    assert res["metadata"]["state"] == "error" and "configuration" in res["metadata"]["evidence"]
    assert calls == []


def test_marker_present_but_nonzero_exit_says_exit_code(fake):
    answer, _, _ = fake
    answer(1, "PROBE closed trs-put=405\n", "")
    res = call("trs-write")
    assert res["metadata"]["state"] == "error"
    assert res["metadata"]["evidence"] == "exit 1"
    assert "no PROBE line" not in res["metadata"]["evidence"]
