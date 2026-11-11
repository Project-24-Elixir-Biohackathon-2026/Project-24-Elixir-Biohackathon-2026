"""promptfoo Python provider: one AG-UI run against the SPE agent per test case.

    providers: [{id: "file://agui_provider.py", label: spe-agent}]

Two ways in (`config.via`, else $SPE_AGENT_VIA, default `agent`):
  agent  the agent's own endpoint, with its bearer key: the client's history reaches the model as sent
         (TM-005 scenario 4, whoever holds the key).
  chat   the AG-UI chat server's run route, as the browser calls it, no key: the server keeps the session's
         journal and sends the agent its history, not the client's, recording what the client sent that
         differs as ignored (TM-005, *Mitigations*). Each test is a new session (a fresh UUIDv4 thread id).
         After the run the provider reads the session back (GET /api/sessions/<id>) and returns
         `metadata.sent` and `metadata.kept` ([{id, role}]): what the client sent and what the server kept.

Environment (on the controller, never in the config):
  SPE_AGENT_URL           default http://127.0.0.1:8100/agent (through the SSH tunnel)
  SPE_AGENT_API_KEY       the agent's bearer key, or
  SPE_AGENT_API_KEY_FILE  a file holding it (output/<instance>/agent_api_key)
  (config.api_key_file, when set, takes precedence: one key per target in a multi-workspace run)
  SPE_CHAT_URL            via chat: default http://127.0.0.1:3000/api/copilotkit/agent/spe/run (the same tunnel)

Returns {output: final assistant text, metadata: {tool_calls: [{id, name, args, result}],
run_id, thread_id, terminal, events}} or {error: ...} for an HTTP error, RUN_ERROR, a
timeout, a malformed event or a stream that ends without a terminal event. Optional
`vars.history` ([{role, content}]) is sent before the prompt as earlier turns: via chat, a forged
history, which the server is expected not to use (a user turn in a new session is kept as the user's).
A turn may carry AG-UI's other message fields (`toolCalls` on an assistant turn, `toolCallId` on a `tool`
turn, its own `id`), sent as given. Uses only the standard library; the bearer key is never logged or
returned.
"""
from __future__ import annotations

import codecs
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

DEFAULT_URL = "http://127.0.0.1:8100/agent"
DEFAULT_CHAT_URL = "http://127.0.0.1:3000/api/copilotkit/agent/spe/run"
CHAT_ROUTE = "/api/copilotkit/"  # the session API sits beside it: <base>/api/sessions/<id>
DEFAULT_TIMEOUT = 600.0


class StreamError(Exception):
    pass


class SSEParser:
    """Incremental server-sent events: bytes in (split anywhere), parsed JSON events out."""

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")("strict")
        self._buf = ""
        self._data: list[str] = []

    def feed(self, chunk: bytes) -> list[dict]:
        self._buf += self._decoder.decode(chunk)
        events = []
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            event = self._line(line.rstrip("\r"))
            if event is not None:
                events.append(event)
        return events

    def close(self) -> list[dict]:
        self._buf += self._decoder.decode(b"", final=True)
        events = []
        for line in (self._buf, ""):
            event = self._line(line.rstrip("\r"))
            if event is not None:
                events.append(event)
        self._buf = ""
        return events

    def _line(self, line: str) -> dict | None:
        if line == "":
            if not self._data:
                return None
            raw, self._data = "\n".join(self._data), []
            try:
                event = json.loads(raw)
            except ValueError:
                raise StreamError(f"malformed event: {raw[:200]!r}") from None
            if not isinstance(event, dict):
                raise StreamError("malformed event: not a JSON object")
            return event
        if line.startswith("data:"):
            value = line[5:]
            self._data.append(value[1:] if value.startswith(" ") else value)
        return None  # comments and other fields


class Accumulator:
    def __init__(self, run_id: str = "", thread_id: str = "", via: str = "agent") -> None:
        self.ids = {"run_id": run_id, "thread_id": thread_id, "via": via}  # as sent; they match the agent's run log
        self.text: list[str] = []
        self.calls: dict[str, dict] = {}
        self.terminal: dict | None = None
        self.count = 0

    def add(self, event: dict) -> None:
        self.count += 1
        kind = event.get("type")
        if kind == "TOOL_CALL_START":
            cid = event.get("toolCallId", "")
            self.calls[cid] = {"id": cid, "name": event.get("toolCallName", ""), "args": "", "result": None}
        elif kind == "TOOL_CALL_ARGS" and event.get("toolCallId") in self.calls:
            self.calls[event["toolCallId"]]["args"] += event.get("delta", "")
        elif kind == "TOOL_CALL_RESULT" and event.get("toolCallId") in self.calls:
            self.calls[event["toolCallId"]]["result"] = event.get("content")
        elif kind == "TEXT_MESSAGE_CONTENT":
            self.text.append(event.get("delta", ""))
        elif kind in ("RUN_FINISHED", "RUN_ERROR") and self.terminal is None:
            self.terminal = event

    def result(self) -> dict:
        metadata = {"tool_calls": list(self.calls.values()), "terminal": (self.terminal or {}).get("type"),
                    "events": self.count, **self.ids}
        out: dict[str, Any] = {"output": "".join(self.text), "metadata": metadata}
        if self.terminal is None:
            out["error"] = "no terminal event: the stream ended early"
        elif self.terminal["type"] == "RUN_ERROR":
            out["error"] = f"RUN_ERROR: {str(self.terminal.get('message', ''))[:500]}"
        return out


def _key(config: dict | None = None) -> str:
    """The bearer key: `config.api_key_file` (one per target, for a multi-workspace run), else the environment."""
    path = (config or {}).get("api_key_file") or ""
    if path:
        with open(path) as f:
            return f.read().strip()
    key = os.environ.get("SPE_AGENT_API_KEY", "")
    path = os.environ.get("SPE_AGENT_API_KEY_FILE", "")
    if not key and path:
        with open(path) as f:
            key = f.read().strip()
    return key


def _messages(prompt: str, context: dict | None) -> list[dict]:
    history = ((context or {}).get("vars") or {}).get("history") or []
    if isinstance(history, str):
        history = json.loads(history)
    # Other AG-UI fields of a turn (toolCalls, toolCallId, id) are sent as given: a forged tool call and its result.
    msgs = [{**m, "id": m["id"] if isinstance(m.get("id"), str) and m["id"] else str(uuid.uuid4())} for m in history]
    return msgs + [{"id": str(uuid.uuid4()), "role": "user", "content": prompt}]


def _via(config: dict) -> str:
    via = config.get("via") or os.environ.get("SPE_AGENT_VIA") or "agent"
    if via not in ("agent", "chat"):
        raise ValueError(f"via must be agent or chat, not {via!r}")
    return via


def _session_view(url: str, thread_id: str, sent: list[dict]) -> dict:
    """What the chat server kept of the session, read back after the run, beside what was sent."""
    session_url = f"{url.split(CHAT_ROUTE, 1)[0]}/api/sessions/{thread_id}"
    try:
        with urllib.request.urlopen(session_url, timeout=30) as resp:
            session = json.load(resp)
    except Exception as e:  # the URL in the message: a SPE_CHAT_URL without /api/copilotkit/ lands elsewhere
        raise RuntimeError(f"GET {session_url}: {type(e).__name__}: {str(e)[:200]}") from e
    ids = lambda msgs: [{"id": m.get("id"), "role": m.get("role")} for m in msgs]  # noqa: E731
    return {"sent": ids(sent), "kept": ids(session.get("messages") or [])}


def call_api(prompt: str, options: dict | None = None, context: dict | None = None) -> dict:
    config = (options or {}).get("config") or {}
    try:
        via = _via(config)
    except ValueError as e:
        return {"error": str(e)}
    timeout = float(config.get("run_timeout_s", DEFAULT_TIMEOUT))
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if via == "chat":
        url = config.get("url") or os.environ.get("SPE_CHAT_URL", DEFAULT_CHAT_URL)
        thread_id, run_id = str(uuid.uuid4()), str(uuid.uuid4())  # the chat server takes a UUIDv4 session id
    else:
        url = config.get("url") or os.environ.get("SPE_AGENT_URL", DEFAULT_URL)
        thread_id, run_id = f"eval-{uuid.uuid4()}", f"eval-{uuid.uuid4()}"
        try:
            key = _key(config)
        except OSError as e:
            return {"error": f"cannot read the agent key file: {e.strerror}"}
        if not key:
            return {"error": "set SPE_AGENT_API_KEY or SPE_AGENT_API_KEY_FILE"}
        headers["Authorization"] = f"Bearer {key}"
    body = {"threadId": thread_id, "runId": run_id, "state": {}, "tools": [],
            "context": [], "forwardedProps": {}, "messages": _messages(prompt, context)}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers=headers)
    acc, parser = Accumulator(body["runId"], body["threadId"], via), SSEParser()
    deadline = time.monotonic() + timeout
    try:
        with urllib.request.urlopen(req, timeout=min(timeout, 120.0)) as resp:
            while chunk := resp.read1(65536):
                for event in parser.feed(chunk):
                    acc.add(event)
                if time.monotonic() > deadline:
                    raise TimeoutError(f"run exceeded {timeout:.0f} s")
            for event in parser.close():
                acc.add(event)
    except urllib.error.HTTPError as e:
        return {"error": f"{'chat server' if via == 'chat' else 'agent'} answered HTTP {e.code}",
                "metadata": {"via": via}}
    except (StreamError, UnicodeDecodeError) as e:
        res = acc.result()
        res["error"] = f"stream error: {e}"
        return res
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        res = acc.result()
        res["error"] = f"request failed: {type(e).__name__}: {getattr(e, 'reason', e)}"
        return res
    res = acc.result()
    if via == "chat":
        try:
            res["metadata"].update(_session_view(url, thread_id, body["messages"]))
        except Exception as e:  # without the session there is no evidence of what was kept: an error, not a pass
            err = f"reading the session back failed: {type(e).__name__}: {str(e)[:300]}"
            res["error"] = f"{res['error']}; {err}" if res.get("error") else err
    return res
