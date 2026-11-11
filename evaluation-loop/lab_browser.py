"""Send AG-UI runs through a browser you are logged into the portal with.

Chrome or Brave must run with --remote-debugging-port (default 9222) and be logged into the
portal: the runs ride on its cookies, so no key leaves the browser. A run is a POST to chat-ui's
run route (<chat_url>/api/copilotkit/agent/spe/run) made from a fresh tab in that context.
"""
from __future__ import annotations

import json
from urllib.parse import urlparse

import spe_threat

RUN_PATH = "/api/copilotkit/agent/spe/run"


# Selectors for the CopilotKit v2 chat, overridable in lab.yaml (ui_selectors:).
UI = {"composer": "textarea[data-testid='copilot-chat-textarea']",
      "send": "button[data-testid='copilot-send-button']",
      "new_chat": "button.spe-new",
      "transcript": ".copilotKitChat"}


class Browser:
    def __init__(self, cdp: str, chat_url: str, timeout_s: float, via: str = "api", ui_selectors: dict | None = None):
        from playwright.sync_api import sync_playwright
        self.chat_url = chat_url.rstrip("/")
        self.timeout_ms = timeout_s * 1000
        self.via = via
        self.ui = {**UI, **(ui_selectors or {})}
        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.connect_over_cdp(cdp)
        except Exception as e:
            self._pw.stop()
            raise SystemExit(f"cannot reach the browser at {cdp}: {e}\n"
                             "start it with --remote-debugging-port=9222 and log into the portal") from e
        self._cdp = cdp
        if not self._browser.contexts:
            self.close()
            raise SystemExit("the browser has no context: open a window and log into the portal")
        self.page = self._browser.contexts[0].new_page()

    @staticmethod
    def _is_closed(err: str) -> bool:
        return any(s in err for s in ("TargetClosed", "has been closed", "context disposed",
                                      "Target page, context or browser"))

    def _reconnect(self) -> bool:
        """The user's tab/window went away. Re-attach to the running browser and open a fresh page.
        Returns False when the whole browser is gone (nothing left to attach to)."""
        try:
            if not self._browser.contexts:
                self._browser = self._pw.chromium.connect_over_cdp(self._cdp)
            self.page = self._browser.contexts[0].new_page()
            return True
        except Exception:
            return False

    def preflight(self) -> None:
        """Fail early when the session is gone: the chat page must load on its own host."""
        r = self.page.request.get(self.chat_url + "/api/sessions", timeout=30000, max_redirects=0)
        if r.status >= 300:
            raise SystemExit(f"{self.chat_url}/api/sessions answered {r.status}: log into the portal in that browser")
        if urlparse(r.url).hostname != urlparse(self.chat_url).hostname:
            raise SystemExit(f"redirected to {r.url}: log into the portal in that browser")

    def run(self, body: dict) -> dict:
        return self.run_ui(body) if self.via == "ui" else self.run_api(body)

    def run_ui(self, body: dict) -> dict:
        """Drive the real chat UI like a user: new chat, type the message, click Send, wait for the
        turn to finish, read the rendered answer. Tool calls are not reliably in the DOM, so this
        returns answer-only (tool_calls empty); use it for answer-based checks and the visible surface."""
        msg = body["messages"][-1]["content"]
        sel, deadline_s = self.ui, self.timeout_ms / 1000
        try:
            if self.page.url.rstrip("/") != self.chat_url:
                self.page.goto(self.chat_url, wait_until="domcontentloaded")
            self.page.wait_for_selector(sel["composer"], timeout=20000)
            self.page.click(sel["new_chat"], timeout=5000)
            self.page.wait_for_timeout(300)
            box = self.page.wait_for_selector(sel["composer"], timeout=10000)
            box.fill(msg)
            before = self._transcript()
            self.page.click(sel["send"], timeout=5000)
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:200]}"
            if self._is_closed(err) and self._reconnect():
                return {"answer": "", "tool_calls": [], "error": err + " (reconnected; rerun)", "browser_closed": False}
            return {"answer": "", "tool_calls": [], "error": err, "browser_closed": self._is_closed(err)}
        # Wait until the transcript stops growing for a few polls, or the deadline.
        import time
        last, stable, start = before, 0, time.monotonic()
        while time.monotonic() - start < deadline_s:
            self.page.wait_for_timeout(1500)
            now = self._transcript()
            if now == last and len(now) > len(before):
                stable += 1
                if stable >= 3:
                    break
            else:
                stable = 0
            last = now
        added = last[len(before):] if last.startswith(before) else last
        answer = self._assistant_only(added, msg)
        if not answer:
            return {"answer": "", "tool_calls": [], "error": "no answer rendered before the deadline"}
        return {"answer": answer, "tool_calls": [], "error": None, "via": "ui"}

    def _assistant_only(self, added: str, user_msg: str) -> str:
        """The DOM diff is [user bubble][assistant bubble][footer]. Drop the echoed user message
        (so a planted {nonce} in the prompt can't be mistaken for the agent repeating it) and the
        persistent chrome, leaving the agent's own text."""
        text = added
        cut = text.rfind(user_msg.strip()[:120])
        if cut >= 0:
            text = text[cut + len(user_msg.strip()[:120]):]
        footer = self.ui.get("footer", "SPE agent ·")
        i = text.find(footer)
        if i >= 0:
            text = text[:i]                # footer and everything after it is chrome
        drop_lines = self.ui.get("strip_lines", ["Thought for", "every tool call is shown"])
        text = "\n".join(ln for ln in text.splitlines() if not any(m in ln for m in drop_lines))
        return text.strip()

    def _transcript(self) -> str:
        el = self.page.query_selector(self.ui["transcript"])
        try:
            return el.inner_text() if el else ""
        except Exception:
            return ""

    def run_api(self, body: dict) -> dict:
        try:
            r = self.page.request.post(self.chat_url + RUN_PATH, data=json.dumps(body), timeout=self.timeout_ms,
                                       headers={"content-type": "application/json", "accept": "text/event-stream"})
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:200]}"
            if self._is_closed(err) and self._reconnect():
                try:  # one retry after re-attaching to the still-running browser
                    r = self.page.request.post(self.chat_url + RUN_PATH, data=json.dumps(body), timeout=self.timeout_ms,
                                               headers={"content-type": "application/json", "accept": "text/event-stream"})
                except Exception as e2:
                    return {"answer": "", "tool_calls": [], "error": f"{type(e2).__name__}: {str(e2)[:200]}",
                            "browser_closed": self._is_closed(f"{type(e2).__name__}: {e2}")}
            else:
                return {"answer": "", "tool_calls": [], "error": err, "browser_closed": self._is_closed(err)}
        if r.status >= 400:
            return {"answer": "", "tool_calls": [], "error": f"HTTP {r.status}"}
        agui = spe_threat.agui
        parser, acc = agui.SSEParser(), agui.Accumulator(body["runId"], body["threadId"])
        try:
            for ev in parser.feed(r.body()) + parser.close():
                acc.add(ev)
        except agui.StreamError as e:
            res = acc.result()
            return {"answer": res["output"], "tool_calls": res["metadata"]["tool_calls"], "error": f"StreamError: {e}"}
        res = acc.result()
        return {"answer": res["output"], "tool_calls": res["metadata"]["tool_calls"], "error": res.get("error")}

    def close(self) -> None:
        try:
            if getattr(self, "page", None):
                self.page.close()
        finally:
            self._pw.stop()  # disconnects; never closes the user's browser
