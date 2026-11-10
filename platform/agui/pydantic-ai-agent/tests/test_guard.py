"""The guard: canaries and protected file names are kept out of what the agent sends on.

Offline, as in test_app: a scripted FunctionModel, a fake sandbox, a hash manifest written per
test, and the shared matcher (`platform/canary_check/canary_check.py`, or the copy baked into the
image). Synthetic tokens only. Every assertion about the answer is made on the reassembled text,
because a token split across two deltas is no safer than one sent whole.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest
from ag_ui.core import EventType
from pydantic_ai.messages import ModelResponse, TextPart, ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from spe_agent import guard as guard_module
from test_app import (
    AUTH, FakeSandbox, build, events, log_records, post_run, running, terminal, tool_call_violations, until_status,
)

TOKEN = "HPCANARY-TEST23"
OTHER = "VCANARY-GUARD99"
STUDY = "STUDY-0007"
LONG = "PLACEHOLDER_" + "A1b2C3d4" * 4     # longer than its redaction
TYPES = {TOKEN: "honeypot-test", OTHER: "vcf-test", STUDY: "registry-study-id", LONG: "aws-key-test"}
NAME = "linkage.csv"


def matcher_path() -> Path:
    """The repository's platform/canary_check, or the copy the image build puts at /app/matcher."""
    here = Path(__file__).resolve()
    for path in [p / "canary_check" / "canary_check.py" for p in here.parents] + [Path("/app/matcher/canary_check.py")]:
        if path.is_file():
            return path
    raise AssertionError("canary_check.py not found: the guard tests need the shared matcher")


def manifest(tmp_path) -> Path:
    path = tmp_path / "canaries" / "canaries.manifest.sha256"
    path.parent.mkdir(exist_ok=True)
    path.write_text("".join(f"{hashlib.sha256(t.encode()).hexdigest()}\t{ty}\n" for t, ty in TYPES.items()))
    return path


def guarded(tmp_path, mode="enforce", **over):
    return {"guard": {"mode": mode, "matcher": str(matcher_path()), "manifest": str(manifest(tmp_path)),
                      "sensitive_names": [NAME], **over}}


def answering(*chunks):
    """Streams `chunks` as the answer, with no tool call."""

    async def stream(messages, info):
        for chunk in chunks:
            yield chunk

    return FunctionModel(stream_function=stream)


def calling(command: str, seen: list | None = None):
    """Calls run_command once with `command`, then answers with the tool's result."""

    async def stream(messages, info):
        if seen is not None:
            seen.append(messages)
        last = messages[-1].parts[-1]
        if isinstance(last, ToolReturnPart):
            yield "done: " + str(last.content)
        else:
            yield {0: DeltaToolCall(name="run_command", json_args=json.dumps({"command": command}),
                                    tool_call_id="call-1")}

    return FunctionModel(stream_function=stream)


class Printing(FakeSandbox):
    """A sandbox whose command output is fixed: what a workflow log or a file listing could hold."""

    def __init__(self, output: str):
        super().__init__()
        self.output = output

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/execute":
            self.calls.append(request)
            return httpx.Response(200, json={"id": "p1", "status": "done", "output": self.output})
        return super().__call__(request)


class Chunked(FakeSandbox):
    """A sandbox answering as open-terminal does: one output entry per PTY read, cut wherever the read ended."""

    def __init__(self, *chunks: str):
        super().__init__()
        self.chunks = chunks

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/execute":
            self.calls.append(request)
            return httpx.Response(200, json={"id": "p1", "status": "done",
                                             "output": [{"type": "output", "data": c} for c in self.chunks]})
        return super().__call__(request)


def to_model(seen) -> str:
    return json.dumps([str(p.content) for m in seen for p in m[-1].parts if isinstance(p, ToolReturnPart)])


def answer(evs) -> str:
    return "".join(e["delta"] for e in evs if e["type"] == "TEXT_MESSAGE_CONTENT")


def everything_sent(evs) -> str:
    return json.dumps(evs)


async def run(tmp_path, model, sandbox=None, mode="enforce", **kw):
    app, sandbox = build(tmp_path, model=model, sandbox=sandbox, **guarded(tmp_path, mode))
    async with running(app) as c:
        await until_status(c, 200)
        evs = await post_run(c, **kw)
    return evs, sandbox


# --- the answer --------------------------------------------------------------------------------


async def test_a_canary_in_the_answer_is_redacted_before_the_client(tmp_path):
    evs, _ = await run(tmp_path, answering(f"the reference is {TOKEN}, see above"))
    assert TOKEN not in everything_sent(evs)
    assert answer(evs) == "the reference is [REDACTED:honeypot-test], see above"
    assert terminal(evs) == ["RUN_FINISHED"]


async def test_a_canary_split_across_deltas_never_reaches_the_client_in_part(tmp_path):
    evs, _ = await run(tmp_path, answering("value: HPCANARY-", "TEST23 and more"))
    assert "HPCANARY" not in everything_sent(evs)
    assert answer(evs) == "value: [REDACTED:honeypot-test] and more"


async def test_a_canary_at_the_very_end_of_the_answer_is_redacted(tmp_path):
    evs, _ = await run(tmp_path, answering("it ends with ", TOKEN[:4], TOKEN[4:]))
    assert "HPCANARY" not in everything_sent(evs)
    assert answer(evs) == "it ends with [REDACTED:honeypot-test]"


async def test_a_clean_answer_is_unchanged_by_the_guard(tmp_path):
    chunks = ("Variant calling ", "on chr20 finished: ", "3 samples, see run r1.")
    app, _ = build(tmp_path, model=answering(*chunks))
    async with running(app) as c:
        await until_status(c, 200)
        plain = await post_run(c)
    evs, _ = await run(tmp_path, answering(*chunks))
    assert answer(evs) == answer(plain) == "".join(chunks)
    assert terminal(evs) == ["RUN_FINISHED"] and tool_call_violations(evs) == []


async def test_study_ids_are_exempt(tmp_path):
    evs, _ = await run(tmp_path, answering(f"input {STUDY}.chr20.cram"))
    assert answer(evs) == f"input {STUDY}.chr20.cram"


# --- tool calls --------------------------------------------------------------------------------


async def test_a_canary_in_a_tool_result_is_redacted_before_the_model_and_the_client(tmp_path):
    seen: list = []
    sandbox = Printing(f"first line\n{TOKEN}\n{OTHER}\n")    # JSON escapes the newlines
    evs, _ = await run(tmp_path, calling("cat results.txt", seen), sandbox=sandbox)
    sent = to_model(seen)
    assert TOKEN not in sent and OTHER not in sent
    assert "[REDACTED:honeypot-test]" in sent and "[REDACTED:vcf-test]" in sent
    assert TOKEN not in everything_sent(evs) and OTHER not in everything_sent(evs)
    assert terminal(evs) == ["RUN_FINISHED"] and tool_call_violations(evs) == []


async def test_a_protected_file_name_in_a_tool_result_is_redacted(tmp_path):
    seen: list = []
    evs, _ = await run(tmp_path, calling("ls registry", seen), sandbox=Printing(f"phenotypes.tsv\n{NAME}\n"))
    sent = to_model(seen)
    assert NAME not in sent and "phenotypes.tsv" in sent


async def test_a_redacted_tool_result_is_not_marked_truncated(tmp_path):
    seen: list = []
    await run(tmp_path, calling("cat keys.txt", seen), sandbox=Printing(f"key {LONG}\n"))
    sent = to_model(seen)
    assert LONG not in sent and "[REDACTED:aws-key-test]" in sent
    assert "[truncated:" not in sent


async def test_a_canary_cut_across_two_output_entries_is_withheld(tmp_path):
    seen: list = []
    sandbox = Chunked("x" * 4000 + " HPCANARY-", "TEST23 and the rest")
    evs, _ = await run(tmp_path, calling("cat big.log", seen), sandbox=sandbox)
    sent = to_model(seen)
    assert "HPCANARY" not in sent and "Withheld by the SPE guard" in sent and "[truncated:" not in sent
    assert "HPCANARY" not in everything_sent(evs)
    assert "HPCANARY" not in (tmp_path / "log" / "runs.jsonl").read_text()
    (rec,) = log_records(tmp_path)
    assert {"where": "tool_result", "kind": "canary", "type": "honeypot-test", "action": "redacted"} in rec["guard"]


async def test_a_canary_cut_across_entries_of_an_answer_past_the_size_cap_is_withheld(tmp_path):
    """Past the 1 MiB cap the answer is cut and no longer parses as JSON: the entry seams are found as text."""
    seen: list = []
    sandbox = Chunked("x" * 4000 + " HPCANARY-", "TEST23 " + "y" * 1_100_000)
    await run(tmp_path, calling("cat big.log", seen), sandbox=sandbox)
    sent = to_model(seen)
    assert "HPCANARY" not in sent and "Withheld by the SPE guard" in sent


async def test_observe_mode_records_a_canary_cut_across_entries_and_changes_nothing(tmp_path):
    seen: list = []
    sandbox = Chunked("first HPCANARY-", "TEST23 rest")
    await run(tmp_path, calling("cat big.log", seen), sandbox=sandbox, mode="observe")
    assert "HPCANARY-" in to_model(seen) and "Withheld" not in to_model(seen)
    (rec,) = log_records(tmp_path)
    assert {"where": "tool_result", "kind": "canary", "type": "honeypot-test", "action": "observed"} in rec["guard"]


# Compact, ASCII-only JSON as Flask or json.dumps(ensure_ascii=True) writes it: an escaped astral character
# right after a URL decodes to a lone surrogate inside the URL candidate.
ASTRAL = '{"url":"https://x.org","icon":"\\ud83e\\uddec"}'


def test_an_escaped_astral_character_after_a_url_does_not_break_the_matcher(tmp_path):
    from spe_agent.config import GuardCfg

    g = guard_module.Guard(GuardCfg(mode="observe", matcher=matcher_path(), manifest=manifest(tmp_path)))
    assert g.find(ASTRAL) == {} and g.find(json.dumps({"output": ASTRAL})) == {}


@pytest.mark.parametrize("mode", ["observe", "enforce"])
async def test_a_tool_result_with_an_escaped_astral_character_reaches_the_model_unchanged(tmp_path, mode):
    seen: list = []
    evs, _ = await run(tmp_path, calling("cat icons.json", seen), sandbox=Printing(ASTRAL), mode=mode)
    sent = to_model(seen)
    assert "x.org" in sent and "Sandbox request failed" not in sent
    assert terminal(evs) == ["RUN_FINISHED"]


async def test_a_command_naming_a_protected_file_never_reaches_the_sandbox(tmp_path):
    evs, sandbox = await run(tmp_path, calling(f"head /data-share/sensitive/registry/{NAME}"))
    assert sandbox.calls == []
    result = next(e for e in evs if e["type"] == "TOOL_CALL_RESULT")
    assert "SPE guard" in result["content"]
    assert terminal(evs) == ["RUN_FINISHED"]


async def test_a_command_carrying_a_canary_never_reaches_the_sandbox(tmp_path):
    evs, sandbox = await run(tmp_path, calling(f"echo {TOKEN} > /tmp/out"))
    assert sandbox.calls == []
    assert TOKEN not in everything_sent(evs)


# --- the run log, observe mode, health -----------------------------------------------------------


async def test_the_run_log_holds_no_blocked_value_but_says_what_was_blocked(tmp_path):
    await run(tmp_path, answering(f"the reference is {TOKEN}"))
    raw = (tmp_path / "log" / "runs.jsonl").read_text()
    assert TOKEN not in raw
    (rec,) = log_records(tmp_path)
    assert {"where": "answer", "kind": "canary", "type": "honeypot-test", "action": "redacted"} in rec["guard"]


async def test_observe_mode_records_but_changes_nothing(tmp_path):
    evs, sandbox = await run(tmp_path, calling(f"head {NAME}"), mode="observe")
    assert len(sandbox.calls) == 1
    (rec,) = log_records(tmp_path)
    assert {"where": "tool_args", "kind": "name", "type": "sensitive-name", "action": "observed"} in rec["guard"]


async def test_observe_mode_passes_the_answer_unchanged(tmp_path):
    evs, _ = await run(tmp_path, answering(f"the reference is {TOKEN}"), mode="observe")
    assert answer(evs) == f"the reference is {TOKEN}"
    (rec,) = log_records(tmp_path)
    assert any(g["action"] == "observed" and g["type"] == "honeypot-test" for g in rec["guard"])


async def test_health_reports_the_guard_mode_and_its_token_count(tmp_path):
    app, _ = build(tmp_path, **guarded(tmp_path))
    async with running(app) as c:
        r = await until_status(c, 200)
    assert r.json()["guard"] == {"mode": "enforce", "tokens": len(TYPES)}


async def test_the_guard_is_off_unless_configured(tmp_path):
    app, _ = build(tmp_path, model=answering(f"the reference is {TOKEN}"))
    async with running(app) as c:
        r = await until_status(c, 200)
        evs = await post_run(c)
    assert "guard" not in r.json()
    assert answer(evs) == f"the reference is {TOKEN}"


def test_an_enforcing_guard_without_its_matcher_refuses_to_start(tmp_path):
    from spe_agent.config import ConfigError
    from spe_agent.app import create_app
    from test_app import SECRETS, config

    cfg = config(tmp_path, guard={"mode": "enforce", "matcher": str(tmp_path / "absent.py"),
                                  "manifest": str(manifest(tmp_path))})
    with pytest.raises(ConfigError, match="absent.py"):
        create_app(cfg, SECRETS, model_override=answering("x"))


# --- the title ---------------------------------------------------------------------------------


async def test_a_canary_in_a_title_is_redacted(tmp_path):
    def titling(messages, info):
        return ModelResponse(parts=[TextPart(json.dumps({"title": f"About {TOKEN}"}))])

    app, _ = build(tmp_path, model=FunctionModel(function=titling), **guarded(tmp_path))
    async with running(app) as c:
        await until_status(c, 200)
        r = await c.post("/title", json={"thread_id": "t1", "messages": [{"role": "user", "content": "hi"}]},
                         headers=AUTH)
    assert r.status_code == 200 and TOKEN not in r.text


# --- the event contract ------------------------------------------------------------------------


def test_every_streamed_event_type_is_held_back_until_its_text_is_whole():
    """An event type whose text arrives in deltas must be in the gate's stream table: a per-event check
    sees one delta at a time and misses a token split across two."""
    import ag_ui.core as core

    with_delta = {cls.model_fields["type"].default for cls in vars(core).values()
                  if isinstance(cls, type) and hasattr(cls, "model_fields") and "delta" in cls.model_fields}
    not_text = {EventType.STATE_DELTA}    # a JSON patch: checked whole, like every other event
    assert EventType.TEXT_MESSAGE_CONTENT in with_delta, "the ag_ui event classes changed shape"
    assert with_delta - not_text <= set(guard_module.STREAMS), sorted(with_delta - not_text - set(guard_module.STREAMS))
