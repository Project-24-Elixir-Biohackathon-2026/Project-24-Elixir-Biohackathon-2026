"""The guard: keeps canaries and protected file names out of what the agent passes on.

It acts at three points of a run:
  - before a sandbox tool runs: a request that names a protected file or carries a canary is
    refused, and the sandbox never sees it (`RunGuard.deny`);
  - on the sandbox's answer, before the model or the tool card see it: canaries and protected
    file names are redacted (`RunGuard.screen`). The model runs off the VM, so this is also
    what keeps them away from the model endpoint. The sandbox cuts a command's output into
    entries wherever a terminal read ended; a value cut across two entries is found in the joined
    output and withholds the answer. Polls of one process are joined too: the sandbox numbers the
    entries, and the guard keeps what it passed on either side of each boundary a poll began or
    ended at, per chat (`_Polls`), so a poll that completes a value with output passed on before
    is withheld, whatever the order and in later runs too. Not joined: a poll cut at the size cap
    (where it starts is unknown), and boundaries pushed out of the bounded store or lost when the
    agent restarts;
  - on every AG-UI event the client receives: canaries are redacted (`RunGuard.feed`). Text that
    arrives in deltas is held back until the next whitespace, so a token split across deltas is
    checked whole and never leaves in part. Protected file names in the agent's own text are
    recorded, not redacted (an open question for the operators).

Matching is the shared matcher's (`platform/canary_check/canary_check.py`, loaded by path):
every candidate substring is hashed and looked up in the hand-off's hash-only manifest, so the
agent never holds a plaintext canary. Each text is also read with its backslash escapes decoded,
twice, so a token behind a JSON `\\n` (a sandbox answer is JSON, an error nests it once more) is
seen. A hit that only shows decoded cannot be replaced in place; that text is withheld.

Modes: `disabled` (no guard), `observe` (record what would be changed, change nothing) and
`enforce`. Records never hold a matched value, only where, what kind, which canary type and the
action: `denied` (the tool call), `redacted` (replaced in place), `withheld` (the whole text
replaced) or `observed`.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import re
import sys
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from ag_ui.core import BaseEvent, EventType
from pydantic import BaseModel

from .compaction import MARKER_PREFIX
from .config import ConfigError, GuardCfg

log = logging.getLogger("spe_agent.guard")

NAME_TYPE = "sensitive-name"
WITHHELD = "[REDACTED:withheld]"
DENIED = json.dumps({"error": "Blocked by the SPE guard: this request names a protected file or value. "
                              "Work with the registered datasets instead."})
WITHHELD_RESULT = json.dumps({"error": "Withheld by the SPE guard: the answer holds protected data that "
                                       "could not be removed from it."})

# Event types whose text arrives in pieces: the kind of stream and the field that names it.
STREAMS: dict[EventType, tuple[str, str | None]] = {
    EventType.TEXT_MESSAGE_CONTENT: ("text", "message_id"),
    EventType.TEXT_MESSAGE_CHUNK: ("text", "message_id"),
    EventType.THINKING_TEXT_MESSAGE_CONTENT: ("thinking", None),
    EventType.REASONING_MESSAGE_CONTENT: ("reasoning", "message_id"),
    EventType.REASONING_MESSAGE_CHUNK: ("reasoning", "message_id"),
    EventType.TOOL_CALL_ARGS: ("tool_args", "tool_call_id"),
    EventType.TOOL_CALL_CHUNK: ("tool_args", "tool_call_id"),
}
# The events that close a stream; chunk streams have none and close at the run's end.
ENDS: dict[EventType, tuple[str, str | None]] = {
    EventType.TEXT_MESSAGE_END: ("text", "message_id"),
    EventType.THINKING_TEXT_MESSAGE_END: ("thinking", None),
    EventType.REASONING_MESSAGE_END: ("reasoning", "message_id"),
    EventType.TOOL_CALL_END: ("tool_args", "tool_call_id"),
}
_TERMINAL = {EventType.RUN_FINISHED, EventType.RUN_ERROR}
_WHERE = {"text": "answer", "thinking": "reasoning", "reasoning": "reasoning", "tool_args": "tool_args"}
_EVENT_WHERE = {EventType.TOOL_CALL_RESULT: "tool_result", EventType.RUN_ERROR: "error"}
_SKIP_FIELDS = {"type", "timestamp"}

_ESCAPE = re.compile(r"\\(u[0-9a-fA-F]{4}|.)", re.DOTALL)
_SIMPLE_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f"}
_WHITESPACE = re.compile(r"\s")
# Between two output entries of a sandbox answer, for a body cut at the size cap that no longer parses.
_SEAM = re.compile(r'"\s*}\s*,\s*{\s*"type"\s*:\s*"[a-z]+"\s*,\s*"data"\s*:\s*"')
# The sandbox operations whose answers hold a process's numbered output: the process `id`, the
# entries read and `next_offset`, the count so far.
_POLLED = frozenset({"run_command", "get_process_status"})
# How much of a process's output either side of a poll boundary is kept and joined. No protected
# value holds whitespace (a candidate is a run of token characters or a URL; names hold none), so
# only the text since the last whitespace can join, but such a run can be long. The manifest holds
# hashes, not lengths: the longest value the seeding plants is 65 characters (the placeholder
# callback URL) and a file name is at most 255 bytes.
_REACH = 256
# Poll boundaries kept over all chats (two sides of at most _REACH characters each); the least
# recently written go first.
_BOUNDARIES = 4096


def _unescape(text: str) -> str:
    def one(m: re.Match) -> str:
        e = m.group(1)
        return chr(int(e[1:], 16)) if len(e) == 5 else _SIMPLE_ESCAPES.get(e, e)
    return _ESCAPE.sub(one, text)


def _joined_output(text: str) -> str | None:
    """A sandbox answer's output entries joined, as the tool card shows them; None when there is no seam."""
    try:
        answer = json.loads(text)
    except ValueError:
        return _SEAM.sub("", text) if _SEAM.search(text) else None
    entries = answer.get("output") if isinstance(answer, dict) else None
    if not isinstance(entries, list) or len(entries) < 2:
        return None
    return "".join(e["data"] for e in entries if isinstance(e, dict) and isinstance(e.get("data"), str))


@dataclass(frozen=True)
class _Read:
    """A poll's output entries [start, end) of one process, joined."""
    process: str
    start: int
    end: int
    text: str


def _read(text: str) -> _Read | None:
    """The process output a poll answer holds. Whatever `offset` and `tail` asked for, the sandbox
    answers with a suffix of the output so far, so it ends at `next_offset`. None for a body cut at
    the size cap: it no longer parses and where it starts is unknown."""
    try:
        answer = json.loads(text)
    except ValueError:
        return None
    if not isinstance(answer, dict):
        return None
    process, end, entries = answer.get("id"), answer.get("next_offset"), answer.get("output")
    if not isinstance(process, str) or type(end) is not int or not isinstance(entries, list) or len(entries) > end:
        return None
    data = "".join(e["data"] for e in entries if isinstance(e, dict) and isinstance(e.get("data"), str))
    return _Read(process, end - len(entries), end, data)


def _lead(text: str) -> str:
    head = text[:_REACH]
    m = _WHITESPACE.search(head)
    return head[:m.start()] if m else head


def _trail(text: str) -> str:
    tail = text[-_REACH:]
    return tail[_last_whitespace_end(tail):]


class _Polls:
    """What was passed on of each process's output either side of the entry boundaries its polls began
    or ended at, per chat, so a value cut across two polls is checked whole: in whichever order they
    arrive, in any run of the chat."""

    def __init__(self):
        self._sides: OrderedDict[tuple, list[str]] = OrderedDict()

    def _around(self, thread_id: str | None, read: _Read) -> tuple[str, str]:
        before = self._sides.get((thread_id, read.process, read.start), ("", ""))[0]
        after = self._sides.get((thread_id, read.process, read.end), ("", ""))[1]
        return before, after

    def windows(self, thread_id: str | None, read: _Read) -> list[str]:
        """The texts a value that `read` completes with output passed on before would show whole in."""
        before, after = self._around(thread_id, read)
        text = read.text
        if not _WHITESPACE.search(text) and len(text) <= _REACH:   # a value may run through it
            return [before + text + after] if before or after else []
        return [w for side, w in ((before, before + _lead(text)), (after, _trail(text) + after)) if side]

    def passed(self, thread_id: str | None, read: _Read) -> None:
        """Keeps `read`'s edges, joined with what was passed on next to them, since a value may run
        through a short piece into a third poll."""
        before, after = self._around(thread_id, read)
        self._keep((thread_id, read.process, read.end), 0, _trail(before + read.text))
        self._keep((thread_id, read.process, read.start), 1, _lead(read.text + after))

    def _keep(self, key: tuple, side: int, text: str) -> None:
        """A side is never shortened: a poll that starts later or ends sooner holds less of the same output."""
        sides = self._sides.pop(key, ["", ""])
        if len(text) > len(sides[side]):
            sides[side] = text
        if any(sides):
            self._sides[key] = sides
            while len(self._sides) > _BOUNDARIES:
                self._sides.popitem(last=False)


def views(text: str) -> list[str]:
    """The text as written and with its escapes decoded, once and twice (an error body nests JSON in JSON)."""
    out = [text]
    for _ in range(2):
        decoded = _unescape(out[-1])
        if decoded == out[-1]:
            break
        out.append(decoded)
    return out


def _load_matcher(path: Path) -> ModuleType:
    if not path.is_file():
        raise ConfigError(f"guard.matcher {path}: not found")
    spec = importlib.util.spec_from_file_location("spe_canary_check", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module   # its dataclasses look their module up there
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        del sys.modules[spec.name]
        raise ConfigError(f"guard.matcher {path}: {e}") from e
    if not all(hasattr(module, f) for f in ("candidates", "load_manifest")):
        raise ConfigError(f"guard.matcher {path}: not the canary matcher (no candidates/load_manifest)")
    return module


Hit = tuple[str, str]   # (kind, type): "canary" and its manifest type, or "name" and NAME_TYPE


class Guard:
    """The instance's guard: the matcher, the manifest (reloaded when it changes) and the names."""

    def __init__(self, cfg: GuardCfg):
        self.mode = cfg.mode
        self._matcher = _load_matcher(cfg.matcher)
        self._manifest_path = cfg.manifest
        self._exempt = set(cfg.exempt_types)
        names = sorted({n for n in cfg.sensitive_names if n}, key=len, reverse=True)
        self._names = re.compile("|".join(map(re.escape, names)), re.IGNORECASE) if names else None
        self._hashes: dict[str, str] = {}
        self._mtime: float | None = None
        self._lock = threading.Lock()
        self.polls = _Polls()   # here, not on a run: a chat polls a process in its later runs too

    @property
    def enforcing(self) -> bool:
        return self.mode == "enforce"

    def _manifest(self) -> dict[str, str]:
        """The hash manifest. Missing is not an error: the hand-off writes it after the agent starts."""
        try:
            mtime = self._manifest_path.stat().st_mtime
        except OSError:
            return self._hashes
        with self._lock:
            if mtime != self._mtime:
                try:
                    self._hashes = self._matcher.load_manifest(self._manifest_path)
                    self._mtime = mtime
                    log.info(json.dumps({"event": "guard_manifest_loaded", "tokens": len(self._hashes)}))
                except (OSError, ValueError) as e:
                    log.warning(json.dumps({"event": "guard_manifest_error", "error": str(e)}))
            return self._hashes

    @property
    def tokens(self) -> int:
        return len(self._manifest())

    def find(self, text: str) -> dict[str, Hit]:
        """Each protected value in `text` (as written or decoded) and what it is."""
        hashes = self._manifest()
        hits: dict[str, Hit] = {}
        for view in views(text):
            if hashes:
                for c in self._matcher.candidates(view):
                    # a decoded escape can leave a lone surrogate; no canary holds one
                    t = hashes.get(hashlib.sha256(c.encode("utf-8", "surrogatepass")).hexdigest())
                    if t and t not in self._exempt:
                        hits[c] = ("canary", t)
            if self._names:
                for m in self._names.finditer(view):
                    hits[m.group(0)] = ("name", NAME_TYPE)
        return hits

    def redact(self, text: str, kinds: tuple[str, ...]) -> tuple[str, list[Hit], bool]:
        """`text` with the values of `kinds` replaced, every hit, and whether the result reads clean.
        A value that only shows decoded cannot be replaced in place: not clean."""
        hits = self.find(text)
        if not hits:
            return text, [], True
        out = text
        for value in sorted(hits, key=len, reverse=True):     # a value that holds another goes whole
            kind, typ = hits[value]
            if kind in kinds:
                out = out.replace(value, f"[REDACTED:{typ}]")
        clean = not any(k in kinds for k, _ in self.find(out).values())
        return out, list(hits.values()), clean

    def run(self, thread_id: str | None) -> RunGuard:
        return RunGuard(self, thread_id)


@dataclass
class _Held:
    where: str
    last: BaseEvent
    text: str = ""
    sent: int = 0


@dataclass
class RunGuard:
    """One run's view of the guard: the tool hooks, the event gate and the run's records."""

    guard: Guard
    thread_id: str | None
    entries: list[dict] = field(default_factory=list)
    _streams: dict[tuple, _Held] = field(default_factory=dict)

    @property
    def enforcing(self) -> bool:
        return self.guard.enforcing

    def note(self, where: str, hits: list[Hit], action: str) -> None:
        for kind, typ in dict.fromkeys(hits):
            entry = {"where": where, "kind": kind, "type": typ, "action": action}
            if entry not in self.entries:
                self.entries.append(entry)
                log.info(json.dumps({"event": "guard_hit", "thread_id": self.thread_id, **entry}))

    def _act(self, where: str, hits: list[Hit], applied: tuple[str, ...], *, withheld: bool) -> None:
        """Records `hits`: those of the `applied` kinds as redacted in place, or as withheld when the
        whole text is replaced, so withholds can be counted from the records."""
        changed = [h for h in hits if h[0] in applied]
        self.note(where, changed, ("withheld" if withheld else "redacted") if self.enforcing else "observed")
        self.note(where, [h for h in hits if h[0] not in applied], "observed")

    # --- the sandbox ---------------------------------------------------------------------------

    def deny(self, args: dict) -> str | None:
        """The refusal to return instead of running a tool call, when any string in its arguments
        names a protected value; None to let it run."""
        hits = [h for s in _strings(args) for h in self.guard.find(s).values()]
        if not hits:
            return None
        self.note("tool_args", hits, "denied" if self.enforcing else "observed")
        return DENIED if self.enforcing else None

    def screen(self, text: str, op: str | None = None) -> str:
        """The answer to sandbox operation `op` as the model may see it: canaries and protected names
        redacted. A value cut across two output entries, or completed by a poll with output of the same
        process passed on before, cannot be replaced in place: that answer is withheld."""
        kinds = ("canary", "name")
        out, hits, clean = self.guard.redact(text, kinds)
        joined = _joined_output(out)
        cut = [h for h in self.guard.find(joined).values() if h[0] in kinds] if joined else []
        read = _read(out) if op in _POLLED else None
        if read is not None:
            cut += [h for w in self.guard.polls.windows(self.thread_id, read)
                    for h in self.guard.find(w).values() if h[0] in kinds]
        withheld = not clean or bool(cut)
        if read is not None and not withheld:     # as enforcing would pass it on, in observe mode too
            self.guard.polls.passed(self.thread_id, read)
        if not hits and not cut:
            return text
        self._act("tool_result", hits + cut, kinds, withheld=withheld)
        if not self.enforcing:
            return text
        return WITHHELD_RESULT if withheld else out

    def title(self, title: str) -> str:
        """A chat title the model wrote, as the client may show it."""
        out, hits, clean = self.guard.redact(title, ("canary",))
        if not hits:
            return title
        self._act("title", hits, ("canary",), withheld=not clean)
        if not self.enforcing:
            return title
        return out if clean else WITHHELD

    # --- the event stream ----------------------------------------------------------------------

    def feed(self, event: BaseEvent) -> list[BaseEvent]:
        """The events to send for `event`. Observe mode records and returns `event` unchanged."""
        gated = self._gate(event)
        return gated if self.enforcing else [event]

    def _gate(self, event: BaseEvent) -> list[BaseEvent]:
        t = event.type
        if t in STREAMS:
            key = self._key(STREAMS[t], event)
            held = self._streams.get(key)
            if held is None:
                held = self._streams[key] = _Held(self._where(key), event)
            held.last = event
            held.text += getattr(event, "delta", None) or ""
            return self._release(key, final=False)
        out: list[BaseEvent] = []
        if t in ENDS:
            key = self._key(ENDS[t], event)
            if key in self._streams:
                out += self._release(key, final=True)
                del self._streams[key]
        elif t in _TERMINAL:
            for key in list(self._streams):
                out += self._release(key, final=True)
            self._streams.clear()
        return out + [self._whole(event)]

    @staticmethod
    def _key(spec: tuple[str, str | None], event: BaseEvent) -> tuple:
        kind, id_field = spec
        return kind, getattr(event, id_field, None) if id_field else None

    @staticmethod
    def _where(key: tuple) -> str:
        kind, ident = key
        if kind == "text" and isinstance(ident, str) and ident.startswith(MARKER_PREFIX):
            return "compaction"
        return _WHERE[kind]

    def _release(self, key: tuple, *, final: bool) -> list[BaseEvent]:
        """The held text up to its last whitespace (all of it when the stream ends), checked and redacted.
        No token holds whitespace, so a token is never split between two releases."""
        held = self._streams[key]
        cut = len(held.text) if final else _last_whitespace_end(held.text)
        if cut <= held.sent:
            return []
        piece = held.text[held.sent:cut]
        held.sent = cut
        out, hits, clean = self.guard.redact(piece, ("canary",))
        if hits:
            self._act(held.where, hits, ("canary",), withheld=not clean)
            piece = out if clean else WITHHELD
        return [held.last.model_copy(update={"delta": piece})] if piece else []

    def _whole(self, event: BaseEvent) -> BaseEvent:
        """`event` with canaries redacted in every field it carries."""
        where = _EVENT_WHERE.get(event.type, "event")
        update = {}
        for name in type(event).model_fields:
            if name in _SKIP_FIELDS:
                continue
            value = getattr(event, name)
            new = self._value(value, where)
            if new is not value:
                update[name] = new
        return event.model_copy(update=update) if update else event

    def _value(self, value: Any, where: str) -> Any:
        """`value` with canaries redacted at any depth; the same object when nothing changed."""
        if isinstance(value, str):
            out, hits, clean = self.guard.redact(value, ("canary",))
            if not hits:
                return value
            self._act(where, hits, ("canary",), withheld=not clean)
            return out if clean else WITHHELD
        if isinstance(value, BaseModel):
            dumped = value.model_dump()
            new = self._value(dumped, where)
            return value if new is dumped else type(value).model_validate(new)
        if isinstance(value, dict):
            items = {k: self._value(v, where) for k, v in value.items()}
            return value if all(items[k] is value[k] for k in value) else items
        if isinstance(value, (list, tuple)):
            items = [self._value(v, where) for v in value]
            return value if all(a is b for a, b in zip(items, value)) else type(value)(items)
        return value

    # --- the run log ---------------------------------------------------------------------------

    def seal(self, record: dict) -> dict:
        """The run-log record: the guard's entries added and, when enforcing, every canary redacted,
        so an archive scan does not count a run the guard stopped as a leak."""
        record = {**record, "guard": self.entries}
        if not self.enforcing:
            return record
        return _redact_deep(record, self.guard)


def _last_whitespace_end(text: str) -> int:
    last = None
    for last in _WHITESPACE.finditer(text):
        pass
    return last.end() if last else 0


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _strings(k)
            yield from _strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _strings(v)


def _redact_deep(value: Any, guard: Guard) -> Any:
    if isinstance(value, str):
        out, _, clean = guard.redact(value, ("canary",))
        return out if clean else WITHHELD
    if isinstance(value, dict):
        return {k: _redact_deep(v, guard) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_deep(v, guard) for v in value]
    return value
