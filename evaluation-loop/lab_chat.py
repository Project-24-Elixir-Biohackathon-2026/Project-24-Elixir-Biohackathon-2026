"""The two ways a turn reaches the chat, behind one interface.

    t = open_transport(cfg)
    r = t.turn(message, session_id=None)   # {answer, tool_calls, error, session_id}
    r2 = t.turn(next_message, r["session_id"])   # continues the same chat session
    t.close()

* ``http``: chat-ui's run route over plain HTTP, no key (platform/promptfoo-evals/agui_provider.py,
  `via: chat`), at ``chat_run_url`` (an instance's chat server, from the cloud or through
  ``agui_tunnel``). No browser.
* ``browser``: the same request on the cookies of the browser you are logged into the portal with
  (lab_browser.py over CDP), at ``chat_url`` (the portal address). Local.

Both continue a session as the chat page does: the server's current branch plus the new message.
chat-ui owns the history (TM-005), so a client-side history would be ignored.
"""
from __future__ import annotations

TRANSPORTS = ("http", "browser")


class HttpChat:
    kind = "http"

    def __init__(self, run_url: str, timeout_s: float):
        if not run_url:
            raise SystemExit("transport http needs chat_run_url in lab.yaml "
                             "(e.g. http://127.0.0.1:3000/api/copilotkit/agent/spe/run through agui_tunnel)")
        import spe_threat
        self.agui = spe_threat.agui
        self.run_url, self.timeout_s = run_url, timeout_s

    def turn(self, message: str, session_id: str | None = None) -> dict:
        ctx = {"vars": {"sessionId": session_id}} if session_id else {"vars": {}}
        res = self.agui.call_api(message, {"config": {"via": "chat", "url": self.run_url,
                                                      "run_timeout_s": self.timeout_s}}, ctx)
        meta = res.get("metadata") or {}
        return {"answer": res.get("output") or "", "tool_calls": meta.get("tool_calls") or [],
                "error": res.get("error"), "session_id": res.get("sessionId") or session_id or meta.get("thread_id")}

    def close(self) -> None:
        pass


class BrowserChat:
    kind = "browser"

    def __init__(self, cdp: str, chat_url: str, timeout_s: float):
        if not chat_url:
            raise SystemExit("transport browser needs chat_url in lab.yaml (the chat's portal address)")
        import lab_browser
        self.br = lab_browser.Browser(cdp, chat_url, timeout_s)

    def preflight(self) -> None:
        self.br.preflight()

    def turn(self, message: str, session_id: str | None = None) -> dict:
        r = self.br.turn(message, session_id)
        return {"answer": r.get("answer") or "", "tool_calls": r.get("tool_calls") or [], "error": r.get("error"),
                "session_id": r.get("session_id")}

    def close(self) -> None:
        self.br.close()


def open_transport(cfg: dict):
    kind = cfg.get("transport") or "browser"
    if kind == "http":
        return HttpChat(cfg.get("chat_run_url"), float(cfg.get("timeout_s", 420)))
    if kind == "browser":
        return BrowserChat(cfg.get("cdp"), cfg.get("chat_url"), float(cfg.get("timeout_s", 420)))
    raise SystemExit(f"lab.yaml transport: {kind!r} is not one of {', '.join(TRANSPORTS)}")
