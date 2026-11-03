"""JSONL run log: one record per completed, failed or cancelled run.

Records hold player input, tool arguments and results, which include scenario canaries:
the file is private (0600) and must never be committed or published. The three key values
are redacted from every string, keys included, before a record is written.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ag_ui.core import (
    BaseEvent,
    RunAgentInput,
    RunErrorEvent,
    TextMessageContentEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)

from .compaction import MARKER_PREFIX
from .sandbox import truncate

REDACTED = "[redacted]"


def redact(value: Any, secrets: list[str]) -> Any:
    if isinstance(value, str):
        for s in secrets:
            if s:
                value = value.replace(s, REDACTED)
        return value
    if isinstance(value, dict):
        return {redact(k, secrets): redact(v, secrets) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v, secrets) for v in value]
    return value


def _bound(value: Any, max_bytes: int) -> Any:
    if isinstance(value, str):
        return truncate(value, max_bytes)
    if isinstance(value, dict):
        return {k: _bound(v, max_bytes) for k, v in value.items()}
    if isinstance(value, list):
        return [_bound(v, max_bytes) for v in value]
    return value


class RunLog:
    def __init__(self, path: Path, secrets: list[str], max_field_bytes: int = 16384):
        self.path = Path(path)
        self._secrets = [s for s in secrets if s]
        self._max = max_field_bytes
        self._lock = threading.Lock()

    def write(self, record: dict) -> None:
        line = json.dumps(_bound(redact(record, self._secrets), self._max), ensure_ascii=False) + "\n"
        data = line.encode()
        with self._lock:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                os.fchmod(fd, 0o600)
                view = memoryview(data)
                while view:
                    view = view[os.write(fd, view):]
            finally:
                os.close(fd)


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(getattr(p, "text", "") or "" for p in content)
    return ""


class RunRecorder:
    """Builds one run's record from the AG-UI events the client receives."""

    def __init__(self, run_input: RunAgentInput):
        user = [m for m in run_input.messages if m.role == "user"]
        self.record: dict[str, Any] = {
            "run_id": run_input.run_id,
            "thread_id": run_input.thread_id,
            "started": time.time(),
            "ended": None,
            "status": None,
            "input": _text(user[-1].content) if user else "",
            "tool_calls": [],
            "answer": "",
            "usage": None,
            "error": None,
            "compactions": [],
        }
        self._calls: dict[str, dict] = {}
        self._ended_at: dict[str, float] = {}

    def observe(self, event: BaseEvent) -> None:
        if isinstance(event, ToolCallStartEvent):
            call = {"id": event.tool_call_id, "name": event.tool_call_name, "args": "", "result": None,
                    "duration_s": None}
            self._calls[event.tool_call_id] = call
            self.record["tool_calls"].append(call)
        elif isinstance(event, ToolCallArgsEvent) and event.tool_call_id in self._calls:
            self._calls[event.tool_call_id]["args"] += event.delta
        elif isinstance(event, ToolCallEndEvent):
            self._ended_at[event.tool_call_id] = time.monotonic()
        elif isinstance(event, ToolCallResultEvent) and event.tool_call_id in self._calls:
            call = self._calls[event.tool_call_id]
            call["result"] = event.content
            if event.tool_call_id in self._ended_at:
                call["duration_s"] = round(time.monotonic() - self._ended_at[event.tool_call_id], 3)
        elif isinstance(event, TextMessageContentEvent):
            if not event.message_id.startswith(MARKER_PREFIX):  # a compaction marker is not the answer
                self.record["answer"] += event.delta
        elif isinstance(event, RunErrorEvent):
            self.record["error"] = event.message

    def usage(self, usage: Any) -> None:
        self.record["usage"] = {k: getattr(usage, k, None)
                                for k in ("requests", "tool_calls", "input_tokens", "output_tokens")}

    def compactions(self, records: list) -> None:
        self.record["compactions"] = [asdict(r) for r in records]

    def finish(self, status: str) -> dict:
        self.record["status"] = status
        self.record["ended"] = time.time()
        return self.record
