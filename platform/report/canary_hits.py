"""Canary hits: each source's records turned into places (where a value was said, read or sent),
and places into hit records (spec *Sources*, *Hits*; decisions 3, 4, 5; clarification 1).

Sources: AG-UI session journals (JournalReader, fed line by line, so a value streamed in pieces
across events and polls is matched whole), the agent's run log (agent_run_places), Open WebUI's
chats from its database or its archive export (openwebui_places) and the test receiver's request
log (receiver_places). hits_for gives the partial hit record per canary found in a place, with its
`origin`: "eval" for a run of an evaluation (its journal's run_start carries forwardedProps.spe_source
"eval", its run log record `source` "eval", or a receiver request inside an evaluation's window, which
the watcher decides with add_window and in_eval_window), else "chat"; a hit line without it reads as
chat (decision 12). The
watcher adds `id`, `detected`, `workspace`, `instance` and `owner`, and keeps dedup_key in its
state, never in the record. HitsFile is a workspace's hits file: one JSON line per hit, `id` its line
number (decision 10), mode 0640, capped at 10 MB.

Standard library only: the portal runs this from its repository checkout with the system Python.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from canarymatch import found, hosts, is_file_canary, received, spans, texts

EXCERPT = 400  # characters, for every excerpt and the prompt
COMPACTION_PREFIX = "spe-compaction-"  # the agent's compaction marker messages: not the answer
RUN_PIECES_MAX = 1 << 20  # characters of argument and text pieces an open run buffers (untrusted journals)
OPEN_RUNS_MAX = 64  # open runs a journal keeps; past it the oldest is dropped
ENDED_RUNS_KEPT = 1024  # ended run ids remembered, so a late event cannot re-open one


@dataclass
class Place:
    frontend: str | None
    source: str
    session: dict | None
    run: str | None
    at: str | None
    prompt: str | None
    place: str
    tool: dict | None
    value: object
    origin: str = "chat"  # "eval": a run of an evaluation (decision 12)
    epoch: float | None = None  # the receiver's own time of a request, for the watcher's windows


def _eval(value: object) -> str:
    """The origin a run's mark gives: "eval" only for that exact string, anything else "chat"."""
    return "eval" if value == "eval" and isinstance(value, str) else "chat"


def _iso(epoch: object) -> str | None:
    if isinstance(epoch, bool) or not isinstance(epoch, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return None


def _text(content: object) -> str:
    """A message's content: a string, or a list of parts whose `text` fields are joined."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict) and isinstance(p.get("text"), str))
    return ""


# AG-UI journals

class JournalReader:
    """One session's journal, fed one parsed line at a time. Keeps the title (`meta` lines) and, per
    open run, its prompt and the pieces of its tool calls and text messages, and emits a place when
    a value is whole: arguments at TOOL_CALL_END, a result at TOOL_CALL_RESULT, a message's text at
    TEXT_MESSAGE_END, and whatever is still open at run_end. REASONING_* events are ignored.

    The journal is the participant's (root on the instance), so what it can make the reader hold is
    bounded: an open run buffers at most RUN_PIECES_MAX characters of pieces (later ones are dropped),
    at most OPEN_RUNS_MAX runs stay open (the oldest is dropped), and an event for a run already ended
    is ignored rather than opening it again; only its run_start does that."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.title: str | None = None
        self.runs: dict[str, dict] = {}
        self.ended: dict[str, None] = {}  # an ordered set, the newest ENDED_RUNS_KEPT ids

    def _open(self, run_id: str, prompt: str | None, origin: str = "chat") -> dict:
        self.ended.pop(run_id, None)
        self.runs.pop(run_id, None)
        while len(self.runs) >= OPEN_RUNS_MAX:
            del self.runs[next(iter(self.runs))]
        run = self.runs[run_id] = {"prompt": prompt, "calls": {}, "texts": {}, "size": 0, "origin": origin}
        return run

    def _run(self, run_id: str) -> dict | None:
        """The open run, opened by its first event when its run_start was never read (a journal read
        from the middle); None for a run already ended."""
        if run_id in self.runs:
            return self.runs[run_id]
        return None if run_id in self.ended else self._open(run_id, None)

    @staticmethod
    def _keep(run: dict, piece: str) -> bool:
        """Whether the run may buffer one more piece (counted against RUN_PIECES_MAX)."""
        if run["size"] + len(piece) > RUN_PIECES_MAX:
            return False
        run["size"] += len(piece)
        return True

    def _place(self, line: dict, run_id: str, place: str, value: object, tool: dict | None = None) -> Place:
        run = self.runs.get(run_id) or {}
        return Place(frontend="agui", source="agui-journal", session={"id": self.session_id, "title": self.title},
                     run=run_id, at=line.get("at"), prompt=run.get("prompt"), place=place, tool=tool,
                     value=value, origin=run.get("origin", "chat"))

    @staticmethod
    def _origin(line: dict) -> str:
        """A run_start's origin: "eval" when its request.forwardedProps.spe_source is "eval" (the promptfoo
        provider's mark, which the chat server passes through). Of the wrong shape anywhere: "chat"."""
        request = line.get("request")
        props = request.get("forwardedProps") if isinstance(request, dict) else None
        return _eval(props.get("spe_source")) if isinstance(props, dict) else "chat"

    def _args_place(self, line: dict, run_id: str, call_id: str, call: dict) -> Place:
        call["args_done"] = True
        args = "".join(call["args"])
        return self._place(line, run_id, "tool_args", args,
                           {"name": call["name"], "call_id": call_id, "args": args, "result": None})

    def feed(self, line: dict) -> list[Place]:
        if not isinstance(line, dict):
            return []
        kind, run_id = line.get("type"), line.get("run_id")
        if kind == "meta":
            if isinstance(line.get("title"), str):
                self.title = line["title"]
            return []
        if not isinstance(run_id, str):
            return []
        if kind == "run_start":
            messages = line.get("messages")
            if messages is None:
                messages = []
            if not isinstance(messages, list):
                return []
            users = [m for m in messages if isinstance(m, dict) and m.get("role") == "user"]
            prompt = "\n".join(_text(m.get("content")) for m in users) if users else None
            self._open(run_id, prompt, self._origin(line))
            return [self._place(line, run_id, "prompt", prompt)] if prompt else []
        if kind == "run_end":
            run = self.runs.get(run_id)
            out = []
            if run:
                out += [self._args_place(line, run_id, cid, c) for cid, c in run["calls"].items() if not c["args_done"]]
                out += [self._place(line, run_id, "answer", "".join(t)) for t in run["texts"].values()]
                del self.runs[run_id]
            self.ended[run_id] = None
            while len(self.ended) > ENDED_RUNS_KEPT:
                del self.ended[next(iter(self.ended))]
            return out
        event = line.get("event")
        if kind != "event" or not isinstance(event, dict):
            return []
        return self._event(line, run_id, event)

    def _event(self, line: dict, run_id: str, event: dict) -> list[Place]:
        call_id, message_id = event.get("toolCallId"), event.get("messageId")
        if not isinstance(call_id, (str, type(None))) or not isinstance(message_id, (str, type(None))):
            return []  # ids are dict keys: anything but a string is a hostile record
        run, kind = self._run(run_id), event.get("type")
        if run is None:
            return []
        if kind == "TOOL_CALL_START" and isinstance(call_id, str):
            if call_id in run["calls"] or self._keep(run, call_id):
                run["calls"][call_id] = {"name": event.get("toolCallName"), "args": [], "args_done": False}
        elif kind == "TOOL_CALL_ARGS" and call_id in run["calls"] and isinstance(event.get("delta"), str):
            if self._keep(run, event["delta"]):
                run["calls"][call_id]["args"].append(event["delta"])
        elif kind == "TOOL_CALL_END" and call_id in run["calls"]:
            if not run["calls"][call_id]["args_done"]:
                return [self._args_place(line, run_id, call_id, run["calls"][call_id])]
        elif kind == "TOOL_CALL_RESULT" and isinstance(call_id, str):
            call = run["calls"].pop(call_id, None) or {"name": None, "args": [], "args_done": True}
            out = [] if call["args_done"] else [self._args_place(line, run_id, call_id, call)]
            tool = {"name": call["name"], "call_id": call_id, "args": "".join(call["args"]),
                    "result": event.get("content")}
            return out + [self._place(line, run_id, "tool_result", event.get("content"), tool)]
        elif kind == "TEXT_MESSAGE_START" and isinstance(message_id, str):
            if not message_id.startswith(COMPACTION_PREFIX) and (message_id in run["texts"] or self._keep(run, message_id)):
                run["texts"].setdefault(message_id, [])
        elif kind == "TEXT_MESSAGE_CONTENT" and isinstance(message_id, str) and isinstance(event.get("delta"), str):
            if not message_id.startswith(COMPACTION_PREFIX) and self._keep(run, message_id + event["delta"]):
                run["texts"].setdefault(message_id, []).append(event["delta"])
        elif kind == "TEXT_MESSAGE_END" and message_id in run["texts"]:
            return [self._place(line, run_id, "answer", "".join(run["texts"].pop(message_id)))]
        return []


# The agent's run log

def agent_run_places(record: dict, titles: dict[str, str]) -> list[Place]:
    """One record of the agent's run log. Title records ({"type": "title", ...}) give no places:
    the caller collects them into `titles`, by thread id. The record is untrusted: a thread id that is
    not a string is no session id (never a dict key), and `tool_calls` that is not a list is absent."""
    if not isinstance(record, dict) or record.get("type") == "title" or not isinstance(record.get("run_id"), str):
        return []
    thread = record.get("thread_id") if isinstance(record.get("thread_id"), str) else None
    prompt = record.get("input") if isinstance(record.get("input"), str) else None
    common = dict(frontend="agui", source="agent-runs",
                  session={"id": thread, "title": titles.get(thread) if thread is not None else None},
                  run=record["run_id"], at=_iso(record.get("started")), prompt=prompt,
                  origin=_eval(record.get("source")))
    out = [Place(**common, place="prompt", tool=None, value=prompt)] if prompt else []
    calls = record.get("tool_calls")
    for call in calls if isinstance(calls, list) else []:
        if not isinstance(call, dict):
            continue
        tool = {"name": call.get("name"), "call_id": call.get("id"), "args": call.get("args"),
                "result": call.get("result")}
        out.append(Place(**common, place="tool_args", tool=tool, value=call.get("args")))
        if call.get("result") is not None:
            out.append(Place(**common, place="tool_result", tool=tool, value=call.get("result")))
    if record.get("answer"):
        out.append(Place(**common, place="answer", tool=None, value=record["answer"]))
    return out


# Open WebUI

def _id(value: object) -> bool:
    """A message or call id, used as a dict key: a string or missing; anything else is hostile."""
    return value is None or isinstance(value, str)


def _messages(chat: dict) -> list[dict]:
    """The chat's messages: history.messages (a dict by id), or the flat `messages` list of an older
    chat, whose replies then answer the user message before them. A message whose `id` or `parentId`
    is not a string is skipped."""
    history = chat.get("history").get("messages") if isinstance(chat.get("history"), dict) else None
    if isinstance(history, dict) and history:
        found = list(history.values())
    else:
        flat = chat.get("messages")
        found, last_user = [], None
        for m in flat if isinstance(flat, list) else []:
            if not isinstance(m, dict) or not _id(m.get("id")):
                continue
            found.append(m if "parentId" in m else m | {"parentId": last_user})
            if m.get("role") == "user":
                last_user = m.get("id")
    return [m for m in found if isinstance(m, dict) and _id(m.get("id")) and _id(m.get("parentId"))]


def openwebui_places(chat: dict, source: str) -> list[Place]:
    """One chat: an item of the export's `chats`, or one row of the database's `chat` table (`id`,
    `title`, `chat` as JSON text). An assistant message is one run (its `id`); its prompt is the
    content of the user message it answers (its `parentId`). Records of the wrong shape (root-controlled
    data) are skipped: a chat, message or output item, never an exception."""
    if not isinstance(chat, dict):
        return []
    body = chat.get("chat")
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except (ValueError, RecursionError):
            return []
    if not isinstance(body, dict):
        return []
    session = {"id": chat.get("id"), "title": chat.get("title")}
    messages = _messages(body)
    by_id = {m.get("id"): m for m in messages}
    out = []
    for m in messages:
        common = dict(frontend="openwebui", source=source, session=session, run=m.get("id"), at=_iso(m.get("timestamp")))
        if m.get("role") == "user":
            content = _text(m.get("content"))
            if content:
                out.append(Place(**common, prompt=content, place="prompt", tool=None, value=content))
            continue
        if m.get("role") != "assistant":
            continue
        parent = by_id.get(m.get("parentId"))
        prompt = _text(parent.get("content")) if parent else None
        output = m.get("output")
        if output is not None and not isinstance(output, list):
            continue
        items = [i for i in output or [] if isinstance(i, dict) and _id(i.get("call_id"))]
        calls = {i.get("call_id"): i for i in items if i.get("type") == "function_call"}
        outputs = {i.get("call_id"): i.get("output") for i in items if i.get("type") == "function_call_output"}
        for i in items:
            call_id = i.get("call_id")
            if i.get("type") == "function_call":
                tool = {"name": i.get("name"), "call_id": call_id, "args": i.get("arguments"),
                        "result": outputs.get(call_id)}
                out.append(Place(**common, prompt=prompt, place="tool_args", tool=tool, value=i.get("arguments")))
            elif i.get("type") == "function_call_output":
                call = calls.get(call_id) or {}
                tool = {"name": call.get("name"), "call_id": call_id, "args": call.get("arguments"),
                        "result": i.get("output")}
                out.append(Place(**common, prompt=prompt, place="tool_result", tool=tool, value=i.get("output")))
        # The answer as the chat shows it (write_run.render_message): the text of its `message` output
        # items when `output` is set (`content` may then embed tool results), else the message's `content`.
        answer = ([_text(i.get("content")) for i in items if i.get("type") == "message"] if output
                  else [_text(m.get("content"))])
        answer = [a for a in answer if a]
        if answer:
            out.append(Place(**common, prompt=prompt, place="answer", tool=None, value=answer))
    return out


# The test receiver

def receiver_places(request: dict) -> list[Place]:
    """One line of the receiver's log. Its `at` (the sink's epoch seconds) gives the place's time and
    `epoch`, which the watcher compares against the evaluation windows; a line without a usable one has
    neither. Always "chat" here: only the watcher, which holds the windows, makes one "eval"."""
    at = _iso(request.get("at"))
    return [Place(frontend=None, source="receiver", session=None, run=None, at=at, prompt=None, place="request",
                  tool=None, value=request, epoch=float(request["at"]) if at is not None else None)]


# Evaluation windows (spe-eval's windows.jsonl: {run, experiment, start, end}, whole UTC seconds)

WINDOW_TIME = "%Y-%m-%dT%H:%M:%SZ"
WINDOWS_MAX = 1000  # runs' windows kept; past it the oldest go first
WINDOW_RUN_MAX = 256  # characters of a run id (a dict key from an untrusted line)


def _window_epoch(text: object) -> float:
    """A window time as epoch seconds; ValueError when it is not WINDOW_TIME."""
    if not isinstance(text, str):
        raise ValueError("window time is not a string")
    return datetime.strptime(text, WINDOW_TIME).replace(tzinfo=timezone.utc).timestamp()


def add_window(windows: dict[str, dict], line: object) -> None:
    """Fold one windows.jsonl line into `windows` ({run: {"start", "end"}}, oldest first, at most
    WINDOWS_MAX). spe-eval writes an opening line (`end` null) when a run starts and a closing one when it
    ends: per run, a closing line wins over an opening one, whatever their order. The line is untrusted:
    one of the wrong shape (run not a short string, start not WINDOW_TIME, end neither null nor
    WINDOW_TIME, either key missing) raises ValueError and changes nothing."""
    if not isinstance(line, dict) or "end" not in line:
        raise ValueError("window line is not an object with an end")
    run, start, end = line.get("run"), line.get("start"), line["end"]
    if not isinstance(run, str) or not run or len(run) > WINDOW_RUN_MAX:
        raise ValueError("window line has no usable run id")
    _window_epoch(start)
    if end is not None:
        _window_epoch(end)
    known = windows.get(run)
    if end is None and known is not None and known.get("end") is not None:
        return  # the closing line, already read, wins
    windows.pop(run, None)
    windows[run] = {"start": start, "end": end}
    while len(windows) > WINDOWS_MAX:
        del windows[next(iter(windows))]


def in_eval_window(epoch: float | None, windows: dict[str, dict]) -> bool:
    """Whether a receiver request at `epoch` fell inside an evaluation's window: start <= epoch < end + 1 s
    (the end is a whole second, the request's time is not). A window still open (no closing line: a run
    going on, or one killed before it could write it) lasts until the next window's start, else is
    open-ended. No time: never."""
    if epoch is None:
        return False
    spans = []
    for window in windows.values():
        try:
            spans.append((_window_epoch(window["start"]),
                          None if window.get("end") is None else _window_epoch(window["end"]) + 1))
        except (ValueError, KeyError, TypeError):
            continue
    starts = sorted(start for start, _ in spans)
    for start, end in spans:
        if end is None:
            end = next((s for s in starts if s > start), math.inf)
        if start <= epoch < end:
            return True
    return False


# Hits

def _readings(place: Place) -> list[str]:
    if place.place == "request":
        return received(place.value) if isinstance(place.value, dict) else []
    return texts(place.value)


def _window(text: str, start: int, end: int) -> tuple[str, int, int]:
    """At most EXCERPT characters of `text`, centred on text[start:end]; the match's offsets in it."""
    lo = max(0, min(start - (EXCERPT - (end - start)) // 2, len(text) - EXCERPT))
    cut = text[lo:lo + EXCERPT]
    return cut, start - lo, min(end - lo, len(cut))


def _excerpt(readings: list[str], token: str) -> dict | None:
    for reading in readings:
        found_spans = spans(token, reading)
        if found_spans:
            text, start, end = _window(reading, *found_spans[0])
            return {"text": text, "start": start, "end": end}
    return None


def _cut(value: object, token: str) -> str | None:
    """A tool's arguments or result for the record: around the match when it is in them, else their start."""
    if value is None:
        return None
    around = _excerpt(texts(value), token)
    if around:
        return around["text"]
    raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return raw[:EXCERPT]


def _kind(place: Place, canary: dict, readings: list[str], api_host: str | None) -> str | None:
    if place.place == "answer":
        return "answer"
    if place.place == "tool_result":
        return "touched" if is_file_canary(canary) else "seen"
    if place.place == "tool_args":
        named = set().union(*map(hosts, readings)) if readings else set()
        foreign = named - {api_host.lower()} if api_host else named
        return "sent" if foreign else "args"
    if place.place == "prompt":
        return "prompt"
    if place.place == "request":
        return "delivered"
    return None


def hits_for(place: Place, canaries: list[dict], api_host: str | None) -> list[dict]:
    """One partial hit record per canary found in the place (spec *Hits*, without `id`, `detected`,
    `workspace`, `instance` and `owner`, which the watcher adds)."""
    readings = _readings(place)
    out = []
    for canary in found(canaries, readings):
        kind = _kind(place, canary, readings, api_host)
        excerpt = _excerpt(readings, canary["token"])
        if kind is None or excerpt is None:
            continue
        tool = None
        if place.tool is not None:
            tool = {"name": place.tool.get("name"), "call_id": place.tool.get("call_id"),
                    "args": _cut(place.tool.get("args"), canary["token"]),
                    "result": _cut(place.tool.get("result"), canary["token"])}
        out.append({
            "at": place.at, "frontend": place.frontend, "source": place.source, "session": place.session,
            "run": place.run, "prompt": place.prompt[:EXCERPT] if isinstance(place.prompt, str) else None,
            "kind": kind, "place": place.place, "tool": tool,
            "canary": {"type": canary["type"], "file": canary["file"], "token": canary["token"]},
            "excerpt": excerpt, "origin": place.origin,
        })
    return out


def dedup_key(hit: dict, generation: str) -> str:
    """One hit per workspace, generation, run, place, tool call id and canary (spec *Sources*, *One
    hit, many copies*): the first copy written wins. A receiver request (no run) of an evaluation is keyed
    apart from the chat's, so an evaluation's delivery never hides the chat's own of the same canary; every
    other key is as it was (a run's copies share their origin, and an older hit line has none: chat)."""
    call_id = (hit.get("tool") or {}).get("call_id")
    parts = (hit.get("workspace"), generation, hit.get("run"), hit.get("place"), call_id, hit["canary"]["token"])
    if hit.get("place") == "request" and hit.get("origin") == "eval":
        parts += ("eval",)
    text = LONE_SURROGATE.sub("\ufffd", "|".join("" if p is None else str(p) for p in parts))  # as written
    return hashlib.sha256(text.encode()).hexdigest()


# The hits file

HITS_FILE_MAX = 10_000_000  # bytes per hits file (spec *Watcher*, untrusted reader output)
# A lone surrogate (untrusted JSON's "\ud800") cannot be UTF-8: written as U+FFFD, one character for one,
# so the excerpt's offsets still hold.
LONE_SURROGATE = re.compile("[\ud800-\udfff]")


class HitsFile:
    """One hits file: a hit per JSON line, its `id` the line number from 1, so an id carries nothing of
    the canary. Created with mode 0640 (portal-only). Past `max_bytes` nothing more is written: `append`
    returns None and `full` is true, which the pages say.

    One writer per file (the watcher, one process; a scan by hand writes its own file). A crash mid-append
    can leave a partial last line: it counts as a line (ids stay line numbers), the next append first ends
    it with a newline, and `read` skips it as a line that does not parse."""

    def __init__(self, path: str, max_bytes: int = HITS_FILE_MAX):
        self.path, self.max_bytes = path, max_bytes
        self.count, self.size, self.full, self.partial = 0, 0, False, False
        try:
            with open(path, "rb") as f:
                data = f.read()
        except FileNotFoundError:
            return
        self.size = len(data)
        self.partial = bool(data) and not data.endswith(b"\n")
        self.count = data.count(b"\n") + self.partial
        self.full = self.size >= max_bytes

    def append(self, hit: dict) -> int | None:
        if self.full:
            return None
        hit["id"] = self.count + 1
        line = (LONE_SURROGATE.sub("\ufffd", json.dumps(hit, ensure_ascii=False)) + "\n").encode()
        if self.partial:
            line = b"\n" + line
        if self.size + len(line) > self.max_bytes:
            del hit["id"]
            self.full = True
            return None
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o640)
        try:
            if self.size == 0:
                os.fchmod(fd, 0o640)  # whatever the umask
            os.write(fd, line)
        finally:
            os.close(fd)
        self.count, self.size, self.partial = self.count + 1, self.size + len(line), False
        return hit["id"]

    def read(self, after: int = 0) -> list[dict]:
        """The hits whose id is past `after`, in order; a line that does not parse is skipped."""
        out = []
        try:
            # errors="replace": a line cut mid-character by a crash fails to parse, not the read
            with open(self.path, encoding="utf-8", errors="replace") as f:
                for n, line in enumerate(f, 1):
                    if n <= after:
                        continue
                    try:
                        hit = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(hit, dict):
                        out.append(hit)
        except FileNotFoundError:
            pass
        return out
