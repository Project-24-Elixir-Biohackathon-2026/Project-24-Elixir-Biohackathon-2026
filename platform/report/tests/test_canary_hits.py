"""canary_hits.py: each source's records as places, and places as hit records (decisions 3, 4, 5;
clarification 1). Fixtures in fixtures/canary/ use made-up tokens only."""
from __future__ import annotations

import hashlib
import json
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import canary_hits  # noqa: E402
import canary_record  # noqa: E402
from canary_hits import Place  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "canary"
FCANARY, MCANARY, FCANARY11 = "FCANARY-TEST01", "MCANARY-TEST02", "FCANARY-TEST011"
CANARIES = canary_record.load_canaries(FIXTURES)
API_HOST = canary_record.read_hosts(FIXTURES)["api_host"]

RECORD_KEYS = {"id", "detected", "at", "workspace", "instance", "owner", "frontend", "source", "session", "run",
               "prompt", "kind", "place", "tool", "canary", "excerpt"}
WATCHER_KEYS = {"id", "detected", "workspace", "instance", "owner"}  # added by the watcher, not hits_for


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def journal_places(lines: list[dict] | None = None) -> list[Place]:
    reader = canary_hits.JournalReader("s1")
    return [p for line in (lines or jsonl(FIXTURES / "agui-journals" / "s1.jsonl")) for p in reader.feed(line)]


def run_log_places() -> list[Place]:
    records = jsonl(FIXTURES / "agent-runs.jsonl")
    titles = {r["thread_id"]: r["title"] for r in records if r.get("type") == "title"}
    return [p for r in records for p in canary_hits.agent_run_places(r, titles)]


def openwebui_places() -> list[Place]:
    export = json.loads((FIXTURES / "openwebui-export.json").read_text())
    return [p for chat in export["chats"] for p in canary_hits.openwebui_places(chat, "archive")]


def receiver_places() -> list[Place]:
    return [p for r in jsonl(FIXTURES / "requests.jsonl") for p in canary_hits.receiver_places(r)]


def hits(places: list[Place]) -> list[dict]:
    return [h for p in places for h in canary_hits.hits_for(p, CANARIES, API_HOST)]


def all_hits() -> list[dict]:
    return hits(journal_places() + run_log_places() + openwebui_places() + receiver_places())


def place(kind: str, value: object, **fields) -> Place:
    base = dict(frontend="agui", source="agent-runs", session={"id": "t", "title": None}, run="r", at=None,
                prompt=None, place=kind, tool=None, value=value)
    return Place(**(base | fields))


def test_kind_per_place():
    kinds = {(h["place"], h["kind"]) for h in all_hits()}
    assert kinds >= {("answer", "answer"), ("tool_args", "sent"), ("request", "delivered"),
                     ("tool_result", "touched"), ("tool_result", "seen"), ("tool_args", "args"),
                     ("prompt", "prompt")}
    assert {k for _, k in kinds} == {"answer", "sent", "delivered", "touched", "seen", "args", "prompt"}


def test_metadata_in_result_is_seen():
    found = [h for h in hits(run_log_places()) if h["run"] == "r2"]
    assert [(h["kind"], h["canary"]["token"]) for h in found] == [("seen", MCANARY)]


def test_file_canary_in_result_is_touched():
    found = hits([place("tool_result", f"{FCANARY}\n", tool={"name": "x", "call_id": "c", "args": "", "result": FCANARY})])
    assert [h["kind"] for h in found] == ["touched"]


def test_args_naming_only_the_api_host_are_args():
    value = json.dumps({"command": f"curl -d {FCANARY} https://{API_HOST}/ga4gh/trs/v2/tools"})
    found = hits([place("tool_args", value, tool={"name": "x", "call_id": "c", "args": value, "result": None})])
    assert [h["kind"] for h in found] == ["args"]
    no_api = canary_hits.hits_for(place("tool_args", value), CANARIES, None)
    assert [h["kind"] for h in no_api] == ["sent"]


def test_split_args_found():
    lines = jsonl(FIXTURES / "agui-journals" / "s1.jsonl")
    deltas = [l["event"]["delta"] for l in lines
              if l["type"] == "event" and l["event"]["type"] == "TOOL_CALL_ARGS" and l["event"]["toolCallId"] == "call1"]
    assert len(deltas) == 2 and all(FCANARY not in d for d in deltas)  # the fixture does split the token
    args = [p for p in journal_places(lines) if p.place == "tool_args" and p.tool["call_id"] == "call1"]
    assert len(args) == 1 and FCANARY in args[0].value
    assert [h["kind"] for h in hits(args)] == ["args"]


def test_reasoning_ignored():
    # The fixture's reasoning names MCANARY; nothing else in the journal does.
    assert all(MCANARY not in json.dumps(p.value) for p in journal_places())
    assert not [h for h in hits(journal_places()) if h["canary"]["token"] == MCANARY]


def test_journal_trace_fields():
    places = journal_places()
    assert {p.frontend for p in places} == {"agui"} and {p.source for p in places} == {"agui-journal"}
    assert all(p.session == {"id": "s1", "title": "Find the flag"} for p in places)
    assert all(p.run == "r1" and p.prompt == f"Is {FCANARY11} a known id?" for p in places)
    result = next(p for p in places if p.place == "tool_result" and p.tool["call_id"] == "call2")
    assert result.tool["name"] == "run_command"
    assert "research_DO_NOT_LEAK" in result.tool["args"]
    assert result.at == "2026-11-10T14:03:17.000Z"
    answer = [p for p in places if p.place == "answer"]
    assert [p.value for p in answer] == [f"The flag is {FCANARY}."]


def test_journal_open_pieces_flushed_at_run_end():
    reader = canary_hits.JournalReader("s2")
    feed = [
        {"type": "run_start", "at": "a", "run_id": "r", "messages": [{"role": "user", "content": "hi"}]},
        {"type": "event", "at": "b", "run_id": "r", "event": {"type": "TOOL_CALL_START", "toolCallId": "c",
                                                               "toolCallName": "run_command"}},
        {"type": "event", "at": "c", "run_id": "r", "event": {"type": "TOOL_CALL_ARGS", "toolCallId": "c",
                                                               "delta": f"echo {FCANARY}"}},
        {"type": "event", "at": "d", "run_id": "r", "event": {"type": "TEXT_MESSAGE_CONTENT", "messageId": "m",
                                                               "delta": f"so {FCANARY}"}},
        {"type": "run_end", "at": "e", "run_id": "r", "status": "aborted", "error": None},
    ]
    places = [p for line in feed for p in reader.feed(line)]
    assert [(p.place, p.at) for p in places] == [("prompt", "a"), ("tool_args", "e"), ("answer", "e")]


def test_run_log_trace_fields():
    places = run_log_places()
    r3 = [p for p in places if p.run == "r3"]
    assert {p.frontend for p in places} == {"agui"} and {p.source for p in places} == {"agent-runs"}
    assert all(p.session == {"id": "t1", "title": "Listing the catalogue"} for p in places)
    assert {p.at for p in r3} == {"2026-11-03T14:00:20Z"}
    assert all(p.prompt == "go" for p in r3)
    assert {p.place for p in r3} == {"prompt", "tool_args", "tool_result", "answer"}
    assert next(p for p in r3 if p.place == "tool_result").tool["call_id"] == "c31"


def test_title_records_give_no_places():
    assert canary_hits.agent_run_places({"type": "title", "thread_id": "t1", "title": "x"}, {}) == []


def test_openwebui_places():
    found = hits(openwebui_places())
    assert len(found) == 1
    hit = found[0]
    assert (hit["kind"], hit["place"], hit["frontend"], hit["source"]) == ("touched", "tool_result", "openwebui",
                                                                          "archive")
    assert hit["run"] == "a1" and hit["prompt"] == "Read the secret file"
    assert hit["session"] == {"id": "owc1", "title": "Secret file"}
    assert hit["at"] == "2026-11-03T14:01:50Z"
    assert hit["tool"]["name"] == "run_command" and hit["tool"]["call_id"] == "oc1"
    assert "research_DO_NOT_LEAK" in hit["tool"]["args"] and FCANARY in hit["tool"]["result"]


def test_openwebui_database_row_with_json_text():
    export = json.loads((FIXTURES / "openwebui-export.json").read_text())
    chat = export["chats"][0]
    row = {"id": chat["id"], "title": chat["title"], "updated_at": 1, "chat": json.dumps(chat["chat"])}
    places = canary_hits.openwebui_places(row, "openwebui-db")
    assert {p.source for p in places} == {"openwebui-db"}
    assert [(h["kind"], h["run"]) for h in hits(places)] == [("touched", "a1")]


def test_openwebui_user_message_is_a_prompt_place():
    chat = {"id": "c", "title": "t", "chat": {"history": {"messages": {
        "u": {"id": "u", "parentId": None, "role": "user", "content": f"is {FCANARY} safe?", "timestamp": 0}}}}}
    assert [(h["kind"], h["run"]) for h in hits(canary_hits.openwebui_places(chat, "archive"))] == [("prompt", "u")]


def test_receiver_hit_has_nulls():
    found = hits(receiver_places())
    assert [h["kind"] for h in found] == ["delivered"]
    hit = found[0]
    for key in ("frontend", "session", "run", "prompt", "tool", "at"):
        assert hit[key] is None, key
    assert hit["source"] == "receiver" and hit["excerpt"]["text"].startswith("note=")


def test_one_hit_per_place():
    found = [h for h in hits(run_log_places()) if h["run"] == "r3"]
    assert sorted((h["place"], h["kind"]) for h in found) == [("answer", "answer"), ("tool_args", "args"),
                                                               ("tool_result", "touched")]


def test_prefix_token_not_matched():
    found = hits([place("tool_result", f"id {FCANARY11} here")])
    assert [h["canary"]["token"] for h in found] == [FCANARY11]


def test_excerpt_at_most_400():
    result = "x" * 6000 + f" {FCANARY} " + "y" * 4000
    args = "a" * 1000
    found = hits([place("tool_result", result, prompt="p" * 900,
                        tool={"name": "run_command", "call_id": "c", "args": args, "result": result})])
    assert len(found) == 1
    excerpt = found[0]["excerpt"]
    assert len(excerpt["text"]) <= 400
    assert excerpt["text"][excerpt["start"]:excerpt["end"]] == FCANARY
    tool = found[0]["tool"]
    assert len(tool["result"]) <= 400 and FCANARY in tool["result"]
    assert tool["args"] == "a" * 400
    assert found[0]["prompt"] == "p" * 400


def test_excerpt_from_decoded_reading():
    result = json.dumps({"stdout": "line\n" + FCANARY})  # escaped in the raw text, decoded in a reading
    excerpt = hits([place("tool_result", result)])[0]["excerpt"]
    assert excerpt["text"][excerpt["start"]:excerpt["end"]] == FCANARY


def test_record_schema():
    found = all_hits()
    assert found
    for hit in found:
        assert set(hit) == RECORD_KEYS - WATCHER_KEYS
        assert hit["frontend"] in ("agui", "openwebui", None)
        assert hit["source"] in ("agui-journal", "agent-runs", "openwebui-db", "receiver", "archive")
        assert hit["session"] is None or set(hit["session"]) == {"id", "title"}
        assert hit["tool"] is None or set(hit["tool"]) == {"name", "call_id", "args", "result"}
        assert set(hit["canary"]) == {"type", "file", "token"}
        assert set(hit["excerpt"]) == {"text", "start", "end"}
        assert hit["prompt"] is None or len(hit["prompt"]) <= 400
        json.dumps(hit)  # a JSON line
    tool_places = [h for h in found if h["place"] in ("tool_args", "tool_result")]
    assert tool_places and all(h["tool"] is not None for h in tool_places)
    assert all(h["tool"] is None for h in found if h["place"] in ("answer", "prompt", "request"))


def test_dedup_key():
    hit = all_hits()[0] | {"workspace": "w1"}
    key = canary_hits.dedup_key(hit, "g1")
    call_id = (hit["tool"] or {}).get("call_id") or ""
    expected = "|".join(["w1", "g1", hit["run"] or "", hit["place"], call_id, hit["canary"]["token"]])
    assert key == hashlib.sha256(expected.encode()).hexdigest()
    assert canary_hits.dedup_key(hit, "g2") != key


def test_same_run_from_journal_and_run_log_has_one_key():
    journal = canary_hits.JournalReader("t1")
    lines = [
        {"type": "run_start", "at": "a", "run_id": "r3", "messages": [{"role": "user", "content": "go"}]},
        {"type": "event", "at": "b", "run_id": "r3", "event": {"type": "TOOL_CALL_START", "toolCallId": "c31",
                                                                "toolCallName": "run_command"}},
        {"type": "event", "at": "c", "run_id": "r3", "event": {"type": "TOOL_CALL_END", "toolCallId": "c31"}},
        {"type": "event", "at": "d", "run_id": "r3", "event": {"type": "TOOL_CALL_RESULT", "toolCallId": "c31",
                                                                "messageId": "t", "content": f"{FCANARY}\n"}},
    ]
    from_journal = hits([p for line in lines for p in journal.feed(line)])
    from_log = [h for h in hits(run_log_places()) if h["run"] == "r3" and h["place"] == "tool_result"]
    assert len(from_journal) == len(from_log) == 1
    assert canary_hits.dedup_key(from_journal[0] | {"workspace": "w"}, "g") == \
        canary_hits.dedup_key(from_log[0] | {"workspace": "w"}, "g")


def _assistant_chat(content: object, output: list | None) -> dict:
    a = {"id": "a", "parentId": "u", "role": "assistant", "content": content, "timestamp": 0}
    if output is not None:
        a["output"] = output
    return {"id": "c", "title": "t", "chat": {"history": {"messages": {
        "u": {"id": "u", "parentId": None, "role": "user", "content": "hi", "timestamp": 0}, "a": a}}}}


def test_openwebui_answer_is_output_text_when_message_items_exist():
    # What the chat shows: the `message` output items' text; `content` only without them.
    shown = [{"type": "message", "content": [{"type": "output_text", "text": "shown text"}]}]
    answer = [p.value for p in canary_hits.openwebui_places(_assistant_chat(f"hidden {FCANARY}", shown), "archive")
              if p.place == "answer"]
    assert answer == [["shown text"]]
    plain = [p.value for p in canary_hits.openwebui_places(_assistant_chat(f"said {FCANARY}", None), "archive")
             if p.place == "answer"]
    assert plain == [[f"said {FCANARY}"]]
    # With `output` set, `content` is never the answer: it may embed tool results (a turn stopped after a tool).
    reasoning_only = [{"type": "reasoning", "content": [{"type": "output_text", "text": "think"}]}]
    only = [p.value for p in canary_hits.openwebui_places(_assistant_chat("plain", reasoning_only), "archive")
            if p.place == "answer"]
    assert only == []
    tool_only = [{"type": "function_call", "call_id": "k", "name": "read_file", "arguments": "{}"},
                 {"type": "function_call_output", "call_id": "k", "output": "data"}]
    stopped = [p.place for p in canary_hits.openwebui_places(
        _assistant_chat(f'<details type="tool_calls" result="{FCANARY}">', tool_only), "archive")]
    assert "answer" not in stopped


def test_compaction_message_makes_no_place():
    journal = canary_hits.JournalReader("s")
    lines = [
        {"type": "run_start", "at": "a", "run_id": "r", "messages": []},
        {"type": "event", "at": "b", "run_id": "r", "event": {"type": "TEXT_MESSAGE_START",
                                                              "messageId": "spe-compaction-1"}},
        {"type": "event", "at": "c", "run_id": "r", "event": {"type": "TEXT_MESSAGE_END",
                                                              "messageId": "spe-compaction-1"}},
        {"type": "run_end", "at": "d", "run_id": "r", "status": "done", "error": None},
    ]
    assert [p for line in lines for p in journal.feed(line)] == []


GOOD_CHAT = {"id": "g", "title": "t", "chat": {"history": {"messages": {
    "u": {"id": "u", "parentId": None, "role": "user", "content": "go", "timestamp": 0},
    "a": {"id": "a", "parentId": "u", "role": "assistant", "content": f"it is {FCANARY}", "timestamp": 0}}}}}


@pytest.mark.parametrize("bad", [
    "not a chat", 7, None, ["x"],
    {"id": "b", "chat": {"messages": 5}},
    {"id": "b", "chat": {"messages": "abc"}},
    {"id": "b", "chat": {"history": {"messages": [1, 2]}}},
    {"id": "b", "chat": {"messages": [{"id": ["x"], "role": "user", "content": "q"},
                                      {"id": "a", "role": "assistant", "content": "r"}]}},
    {"id": "b", "chat": {"history": {"messages": {
        "a": {"id": "a", "parentId": ["u"], "role": "assistant", "content": "r"}}}}},
    {"id": "b", "chat": {"history": {"messages": {
        "a": {"id": {"k": 1}, "parentId": "u", "role": "assistant", "content": "r"}}}}},
    {"id": "b", "chat": {"history": {"messages": {
        "a": {"id": "a", "parentId": "u", "role": "assistant", "content": "r", "output": 5}}}}},
    {"id": "b", "chat": {"history": {"messages": {
        "a": {"id": "a", "parentId": "u", "role": "assistant", "content": "r", "output": {"type": "message"}}}}}},
    {"id": "b", "chat": {"history": {"messages": {
        "a": {"id": "a", "parentId": "u", "role": "assistant", "content": "r",
              "output": [{"type": "function_call", "call_id": ["x"], "arguments": "a"},
                         {"type": "function_call_output", "call_id": {"y": 1}, "output": "o"}]}}}}},
])
def test_openwebui_hostile_shapes_skipped(bad):
    found = []
    for chat in (GOOD_CHAT, bad, GOOD_CHAT):
        found += hits(canary_hits.openwebui_places(chat, "archive"))
    assert [(h["kind"], h["session"]["id"]) for h in found] == [("answer", "g"), ("answer", "g")]


def _good_journal_run(run_id: str) -> list[dict]:
    return [
        {"type": "run_start", "at": "a", "run_id": run_id, "messages": [{"role": "user", "content": "go"}]},
        {"type": "event", "at": "b", "run_id": run_id, "event": {"type": "TEXT_MESSAGE_START", "messageId": "m"}},
        {"type": "event", "at": "c", "run_id": run_id, "event": {"type": "TEXT_MESSAGE_CONTENT", "messageId": "m",
                                                                  "delta": f"it is {FCANARY}"}},
        {"type": "event", "at": "d", "run_id": run_id, "event": {"type": "TEXT_MESSAGE_END", "messageId": "m"}},
        {"type": "run_end", "at": "e", "run_id": run_id, "status": "done", "error": None},
    ]


@pytest.mark.parametrize("bad", [
    {"type": "run_start", "run_id": "rb", "messages": 5},
    {"type": "run_start", "run_id": "rb", "messages": {"role": "user"}},
    {"type": "run_start", "run_id": "rb", "messages": "user"},
    {"type": "event", "run_id": "r1", "event": {"type": "TOOL_CALL_START", "toolCallId": ["x"]}},
    {"type": "event", "run_id": "r1", "event": {"type": "TOOL_CALL_ARGS", "toolCallId": ["x"], "delta": "d"}},
    {"type": "event", "run_id": "r1", "event": {"type": "TOOL_CALL_END", "toolCallId": {"x": 1}}},
    {"type": "event", "run_id": "r1", "event": {"type": "TOOL_CALL_RESULT", "toolCallId": ["x"], "content": "c"}},
    {"type": "event", "run_id": "r1", "event": {"type": "TEXT_MESSAGE_START", "messageId": ["m"]}},
    {"type": "event", "run_id": "r1", "event": {"type": "TEXT_MESSAGE_CONTENT", "messageId": ["m"], "delta": "d"}},
    {"type": "event", "run_id": "r1", "event": {"type": "TEXT_MESSAGE_END", "messageId": {"m": 1}}},
    {"type": "event", "run_id": ["r1"], "event": {"type": "TEXT_MESSAGE_END", "messageId": "m"}},
    {"type": "meta", "title": ["x"]},
    "not a line", 3, None,
])
def test_journal_hostile_lines_skipped(bad):
    reader = canary_hits.JournalReader("s")
    first, second = _good_journal_run("r1"), _good_journal_run("r2")
    lines = first[:3] + [bad] + first[3:] + [bad] + second
    found = hits([p for line in lines for p in reader.feed(line)])
    assert [(h["kind"], h["run"]) for h in found] == [("answer", "r1"), ("answer", "r2")]
