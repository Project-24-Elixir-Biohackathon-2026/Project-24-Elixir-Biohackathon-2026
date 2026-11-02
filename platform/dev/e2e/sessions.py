#!/usr/bin/env python3
"""Drive the chat UI's session sidebar in a real browser, against the scripted agent (no LLM).

    python3 platform/dev/e2e/sessions.py [--shots DIR] [--sessions DIR]

Run `npm ci && npm run build` in platform/agui/copilotkit-chat first. The script starts
platform/dev/fake_agent.py (with uv, in platform/agui/pydantic-ai-agent) and the standalone chat UI
with its own sessions directory, walks the sidebar (list, open, New chat, ?session=, the row menu's
close and focus rules, the row menu) and checks the session files after each step. It ends with three sessions: one tagged and pinned, one hidden, one
deleted, and checks that a run whose tab is closed is still saved whole. Needs Python Playwright with Chromium
(`pip install playwright` and `playwright install chromium`). Exits nonzero on the first failed check.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "platform" / "agui" / "copilotkit-chat"
AGENT_DIR = ROOT / "platform" / "agui" / "pydantic-ai-agent"
KEY = "e2e-sessions-key"
AGENT_PORT = 18108
UI_PORT = 3108
BASE = f"http://127.0.0.1:{UI_PORT}"
XSS = '<img src=x onerror="window.__speXss=1">'


def wait_http(url: str, what: str, seconds: float = 60) -> None:
    until = time.time() + seconds
    while time.time() < until:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except Exception:
            time.sleep(0.25)
    sys.exit(f"FAIL: {what} did not come up at {url}")


class Run:
    def __init__(self, page: Page, sessions: Path, shots: Path | None):
        self.page, self.sessions, self.shots, self.n = page, sessions, shots, 0

    def shot(self, name: str) -> None:
        if self.shots:
            self.n += 1
            # animations="disabled" ends the menu's fade first, so a shot is not caught mid-way.
            self.page.screenshot(path=str(self.shots / f"{self.n:02d}-{name}.png"), full_page=True,
                                 animations="disabled")

    def ok(self, what: str) -> None:
        print(f"ok - {what}", flush=True)

    def files(self) -> dict[str, dict]:
        return {p.stem: json.loads(p.read_text()) for p in self.sessions.glob("*.json")}

    def wait_runs(self, sid: str, n: int, seconds: float = 5) -> dict:
        """The session's record once it has n runs: the recorder writes after the answer is shown."""
        until = time.time() + seconds
        while True:
            path = self.sessions / f"{sid}.json"
            rec = json.loads(path.read_text()) if path.exists() else {"runs": []}
            if len(rec["runs"]) >= n or time.time() > until:
                assert len(rec["runs"]) == n, (sid, n, rec["runs"])
                return rec
            time.sleep(0.2)

    def url_session(self) -> str | None:
        from urllib.parse import parse_qs, urlparse
        return (parse_qs(urlparse(self.page.url).query).get("session") or [None])[0]

    def rows(self):
        return self.page.locator(".spe-sidebar .spe-row")

    def row(self, title: str):
        return self.rows().filter(has=self.page.locator(".spe-row-title", has_text=title))

    def send(self, text: str, turn: int) -> None:
        box = self.page.get_by_test_id("copilot-chat-textarea")
        box.fill(text)
        box.press("Enter")
        expect(self.page.get_by_text(f"Turn {turn}: the command ran.")).to_be_visible(timeout=20_000)

    def menu(self, title: str, item: str) -> None:
        self.row(title).locator(".spe-row-menu").click()
        self.page.get_by_role("menuitem", name=item).click()


def check_list(r: Run) -> dict[str, str]:
    page = r.page
    page.goto(BASE + "/")
    expect(page.get_by_role("button", name="New chat")).to_be_visible()
    assert r.url_session() is None, page.url
    r.ok("first load: no session in the URL, New chat shown")

    r.send("List the home directory", 1)
    expect(r.row("List the home directory")).to_have_count(1, timeout=5_000)
    first = r.url_session()
    assert first and first in r.files(), (first, list(r.files()))
    rec = r.files()[first]
    assert [x["status"] for x in rec["runs"]] == ["completed"] and rec["title"] == "List the home directory"
    r.ok("first run: the row appears, the URL names the session, the file has one completed run")

    page.reload()
    expect(page.get_by_text("Turn 1: the command ran.")).to_be_visible(timeout=10_000)
    expect(page.locator(".spe-tool .spe-tool-name", has_text="run_command")).to_have_count(1)
    expect(r.row("List the home directory")).to_have_class("spe-row spe-row-active")
    r.ok("reload reopens the session with its tool card")

    page.get_by_role("button", name="New chat").click()
    expect(page.get_by_text("Turn 1: the command ran.")).to_have_count(0)
    assert r.url_session() is None, page.url
    r.send("Read the dataset", 1)
    expect(r.row("Read the dataset")).to_have_count(1, timeout=5_000)
    second = r.url_session()
    assert second and second != first
    r.ok("New chat: empty history, a second session after its first run")

    page.get_by_role("button", name="New chat").click()
    r.send(XSS, 1)
    expect(r.rows()).to_have_count(3, timeout=5_000)
    third = r.url_session()
    assert third and r.files()[third]["title"] == XSS
    expect(r.row("<img src=x")).to_have_count(1)
    assert page.evaluate("window.__speXss") is None
    r.ok("a title of an HTML tag shows as literal text and runs nothing")
    r.shot("three-sessions")

    r.row("List the home directory").locator(".spe-row-open").click()
    # "Turn 1" text is already on screen from the previous session, so waiting on it races
    # open(): wait for the URL to actually name `first` before asserting on it.
    page.wait_for_url(f"**session={first}**")
    expect(page.get_by_text("Turn 1: the command ran.")).to_be_visible(timeout=10_000)
    assert r.url_session() == first
    r.send("And the hidden files?", 2)
    assert [x["status"] for x in r.wait_runs(first, 2)["runs"]] == ["completed", "completed"]
    r.ok("opening a row restores its history, and a run continues it")

    for bad in ("not-a-uuid", str(uuid.uuid4()), first.upper()):
        page.goto(f"{BASE}/?session={bad}")
        expect(page.get_by_role("button", name="New chat")).to_be_visible()
        expect(page.get_by_test_id("copilot-chat-textarea")).to_be_visible(timeout=10_000)
        expect(page.locator(".spe-error")).to_have_count(0)
        assert r.url_session() is None, page.url
    r.ok("?session= malformed, unknown or upper-case: new session, parameter dropped, no error bar")
    return {"first": first, "second": second, "third": third}


def focused_label(page: Page) -> str | None:
    return page.evaluate("document.activeElement && document.activeElement.getAttribute('aria-label')")


def focused_text(page: Page) -> str:
    return page.evaluate("document.activeElement ? document.activeElement.textContent : ''")


def check_focus(r: Run, ids: dict[str, str]) -> None:
    """The row menu closes, saves and gives focus back as Open WebUI's does. Leaves the sessions as it found them."""
    page = r.page
    a, b = "List the home directory", "Read the dataset"
    page.goto(f"{BASE}/?session={ids['first']}")
    expect(page.get_by_text("Turn 2: the command ran.")).to_be_visible(timeout=10_000)
    menus = page.locator(".spe-menu")

    before = r.row(b).bounding_box()
    r.row(a).locator(".spe-row-menu").click()
    expect(menus).to_have_count(1)
    assert r.row(b).bounding_box() == before, "the popover moved the rows"
    page.locator(".spe-note").click()
    expect(menus).to_have_count(0)
    r.ok("menu: floats over the list; a click on empty sidebar space closes it")

    r.row(a).locator(".spe-row-menu").click()
    page.keyboard.press("Escape")
    expect(menus).to_have_count(0)
    assert focused_label(page) == f"Menu for {a}", focused_label(page)
    r.ok("menu: Escape closes it and focus is back on its ⋯")

    # The popover covers the rows under its ⋯, so the second ⋯ is the top row's, with the bottom row's menu open.
    top, bottom = r.rows().first, r.rows().last
    top_title = top.locator(".spe-row-title").inner_text()
    bottom.locator(".spe-row-menu").click()
    top.locator(".spe-row-menu").click()
    expect(menus).to_have_count(1)
    expect(menus).to_have_attribute("aria-label", f"Menu for {top_title}")
    page.get_by_role("button", name="New chat").click()
    expect(menus).to_have_count(0)
    r.row(a).locator(".spe-row-menu").click()
    page.get_by_role("button", name="Hide sessions").click()
    page.get_by_role("button", name="Show sessions").click()
    expect(menus).to_have_count(0)
    r.ok("menu: another row's ⋯ leaves exactly one menu, that row's; New chat and collapsing close it")

    r.row(a).locator(".spe-row-menu").click()
    page.keyboard.press("ArrowDown")
    assert focused_text(page) == "Rename", focused_text(page)
    page.keyboard.press("ArrowDown")
    assert focused_text(page) == "Pin", focused_text(page)
    page.keyboard.press("End")
    assert focused_text(page) == "Delete", focused_text(page)
    page.keyboard.press("ArrowDown")
    assert focused_text(page) == "Rename", focused_text(page)
    page.keyboard.press("ArrowUp")
    assert focused_text(page) == "Delete", focused_text(page)
    page.keyboard.press("Home")
    assert focused_text(page) == "Rename", focused_text(page)
    texts = [t.strip() for t in menus.locator('[role="menuitem"]').all_text_contents()]
    assert texts == ["Rename", "Pin", "Tags", "Hide", "Delete"], texts
    expect(menus.locator('[role="separator"]')).to_have_count(1)
    page.keyboard.press("Escape")
    page.keyboard.press("Enter")  # the ⋯ has focus: opened from the keyboard, the first item takes it
    expect(menus).to_have_count(1)
    assert focused_text(page) == "Rename", focused_text(page)
    page.keyboard.press("Escape")
    r.ok("menu: Rename, Pin, Tags, Hide, separator, Delete; arrows, Home and End move focus; from the keyboard the first item has it")

    height = r.row(b).bounding_box()["height"]
    r.menu(b, "Rename")
    title = page.get_by_label("Session title")
    expect(title).to_be_focused()
    assert page.evaluate("(() => { const i = document.activeElement; return i.value.slice(i.selectionStart, i.selectionEnd); })()") == b
    assert page.locator(".spe-row-renaming").bounding_box()["height"] == height, "the rename changed the row's height"
    title.fill("Discarded title")
    title.press("Escape")
    expect(page.locator(".spe-rename")).to_have_count(0)
    assert focused_label(page) == f"Menu for {b}", focused_label(page)
    assert r.files()[ids["second"]]["title"] == b
    r.ok("rename: in place, focused, text selected, same height; Escape cancels and focus is back on the ⋯")

    r.menu(b, "Rename")
    page.locator(".spe-row-renaming .spe-row-menu").click(force=True)  # inert while renaming
    expect(page.locator(".spe-rename")).to_have_count(1)
    expect(menus).to_have_count(0)
    page.get_by_label("Session title").fill(f"{b} (renamed)")
    r.row(a).locator(".spe-row-open").click()
    page.wait_for_url(f"**session={ids['first']}**")
    expect(page.locator(".spe-rename")).to_have_count(0)
    expect(r.row(f"{b} (renamed)")).to_have_count(1, timeout=5_000)
    page.reload()
    expect(r.row(f"{b} (renamed)")).to_have_count(1, timeout=10_000)
    assert r.files()[ids["second"]]["title"] == f"{b} (renamed)"
    r.ok("rename: the ⋯ is inert; a click on another row saves the title (a reload shows it) and opens that row")

    r.row(b).locator(".spe-row-open").dblclick()
    expect(page.get_by_label("Session title")).to_be_focused()
    page.get_by_label("Session title").fill(b)
    page.get_by_label("Session title").press("Enter")
    expect(page.locator(".spe-rename")).to_have_count(0)
    expect(r.row(f"{b} (renamed)")).to_have_count(0, timeout=5_000)
    assert r.files()[ids["second"]]["title"] == b
    r.ok("rename: a double-click on the title starts it, Enter saves")

    tag_input = page.get_by_label("Add a tag")
    chips = page.locator(".spe-popover .spe-chip")
    r.menu(b, "Tags")
    expect(tag_input).to_be_focused()
    expect(tag_input).to_have_attribute("placeholder", "Add a tag…")
    tag_input.fill("canary-probe")
    tag_input.press("Enter")
    expect(chips.filter(has_text="canary-probe")).to_have_count(1, timeout=5_000)
    tag_input.fill("Bad Tag!")
    tag_input.press("Enter")
    expect(page.locator(".spe-tag-error")).to_contain_text("400", timeout=5_000)
    expect(tag_input).to_have_value("Bad Tag!")
    tag_input.press("Escape")
    expect(page.locator(".spe-popover")).to_have_count(0)
    assert r.files()[ids["second"]]["tags"] == ["canary-probe"]
    r.ok("tags: Enter adds the typed tag; an invalid one shows the server's 400 under the input and keeps the text")

    r.menu(a, "Tags")
    suggestions = page.locator(".spe-tag-suggestions [role=option]")
    tag_input.fill("PROBE")
    expect(suggestions).to_have_text(["canary-probe"])
    tag_input.press("Escape")
    expect(suggestions).to_have_count(0)
    expect(page.locator(".spe-popover")).to_have_count(1)
    tag_input.fill("canary")
    expect(suggestions).to_have_text(["canary-probe"])
    tag_input.press("ArrowDown")
    tag_input.press("Enter")
    expect(chips).to_have_text(["canary-probe"], timeout=5_000)
    assert r.files()[ids["first"]]["tags"] == ["canary-probe"]
    page.get_by_role("button", name="Remove tag canary-probe").click()
    expect(chips).to_have_count(0, timeout=5_000)
    assert r.files()[ids["first"]]["tags"] == []
    tag_input.fill("leftover")
    page.locator(".spe-note").click()
    expect(page.locator(".spe-popover")).to_have_count(0)
    time.sleep(0.5)
    assert r.files()[ids["first"]]["tags"] == []
    r.menu(b, "Tags")
    page.get_by_role("button", name="Remove tag canary-probe").click()
    expect(chips).to_have_count(0, timeout=5_000)
    tag_input.press("Escape")
    assert r.files()[ids["second"]]["tags"] == []
    r.ok("tags: a prefix shows the tag in use (Escape hides it first), Enter adds it, x removes it, a click outside adds nothing")

    r.menu(b, "Delete")
    dialog = page.get_by_role("alertdialog")
    expect(dialog).to_contain_text("Delete chat?")
    expect(dialog).to_contain_text("This removes it from your list. It is kept in the run archive.")
    expect(dialog.get_by_role("button", name="Cancel")).to_be_focused()
    page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    expect(r.row(b)).to_have_count(1)
    assert focused_label(page) == f"Menu for {b}", focused_label(page)
    r.menu(b, "Delete")
    page.locator(".spe-dialog-backdrop").click(position={"x": 5, "y": 5})
    expect(dialog).to_have_count(0)
    assert r.files()[ids["second"]]["deleted_at"] is None
    r.ok("delete: the dialog opens on Cancel; Escape and the backdrop cancel, focus back on the ⋯, the row stays")


def check_menu(r: Run, ids: dict[str, str]) -> None:
    page = r.page
    page.goto(f"{BASE}/?session={ids['first']}")
    expect(page.get_by_text("Turn 2: the command ran.")).to_be_visible(timeout=10_000)

    r.row("List the home directory").locator(".spe-row-menu").click()
    r.shot("row-menu")
    page.get_by_role("menuitem", name="Rename").click()
    page.get_by_label("Session title").fill("Discarded title")
    page.get_by_label("Session title").press("Escape")
    expect(r.row("List the home directory")).to_have_count(1)
    assert r.files()[ids["first"]]["title"] == "List the home directory"
    r.menu("List the home directory", "Rename")
    page.get_by_label("Session title").fill("List the home directory (exfil try)")
    page.get_by_label("Session title").press("Enter")
    expect(r.row("List the home directory (exfil try)")).to_have_count(1, timeout=5_000)
    rec = r.files()[ids["first"]]
    assert rec["title"] == "List the home directory (exfil try)" and rec["title_source"] == "user"
    r.ok("rename: Esc cancels, Enter saves (title_source user)")

    title = "List the home directory (exfil try)"
    r.menu(title, "Tags")
    for tag in ("Exfil", "dns", "scratch"):
        page.get_by_label("Add a tag").fill(tag)
        page.get_by_label("Add a tag").press("Enter")
        expect(page.locator(".spe-popover .spe-chip", has_text=tag.lower())).to_have_count(1, timeout=5_000)
    r.shot("tags")
    page.get_by_role("button", name="Remove tag scratch").click()
    expect(page.locator(".spe-popover .spe-chip")).to_have_count(2, timeout=5_000)
    page.get_by_label("Add a tag").press("Escape")
    expect(page.locator(".spe-popover")).to_have_count(0)
    expect(r.row(title).locator(".spe-chip")).to_have_count(0)
    assert r.files()[ids["first"]]["tags"] == ["exfil", "dns"]
    r.ok("tags: added (lower-cased), one removed with its x; rows show no tags")

    r.menu("Read the dataset", "Pin")
    r.menu("Read the dataset", "Unpin")
    r.menu(title, "Pin")
    expect(r.rows().first.locator(".spe-row-title")).to_contain_text(title, timeout=5_000)
    expect(r.row(title).locator(".spe-pin")).to_have_count(1)
    assert r.files()[ids["first"]]["pinned"] is True and r.files()[ids["second"]]["pinned"] is False
    r.ok("pin and unpin: the pinned row comes first")

    r.menu("Read the dataset", "Hide")
    expect(r.row("Read the dataset")).to_have_count(0, timeout=5_000)
    assert r.files()[ids["second"]]["hidden"] is True
    page.goto(f"{BASE}/?session={ids['second']}")
    expect(page.get_by_text("Turn 1: the command ran.")).to_be_visible(timeout=10_000)
    assert r.url_session() == ids["second"]
    r.ok("hide: gone from the list, still openable by its URL")

    page.get_by_role("button", name="New chat").click()
    r.menu("<img src=x", "Rename")
    page.get_by_label("Session title").fill("Try the canary")
    page.get_by_label("Session title").press("Enter")
    expect(r.row("Try the canary")).to_have_count(1, timeout=5_000)
    r.menu("Try the canary", "Delete")
    r.shot("delete-confirmation")
    page.get_by_role("alertdialog").get_by_role("button", name="Cancel").click()
    expect(r.row("Try the canary")).to_have_count(1)
    assert r.files()[ids["third"]]["deleted_at"] is None
    r.menu("Try the canary", "Delete")
    page.get_by_role("alertdialog").get_by_role("button", name="Delete").click()
    expect(r.row("Try the canary")).to_have_count(0, timeout=5_000)
    assert r.files()[ids["third"]]["deleted_at"]
    page.goto(f"{BASE}/?session={ids['third']}")
    expect(page.get_by_test_id("copilot-chat-textarea")).to_be_visible(timeout=10_000)
    assert r.url_session() is None and page.locator(".spe-error").count() == 0
    r.ok("delete: Cancel keeps it; Delete removes the row, keeps the file; its URL opens a new session")

    page.goto(f"{BASE}/?session={ids['first']}")
    expect(page.get_by_text("Turn 2: the command ran.")).to_be_visible(timeout=10_000)
    expect(page.locator(".spe-tool")).to_have_count(2)
    r.shot("final-reopened")
    states = sorted((f["title"], f["pinned"], f["hidden"], bool(f["deleted_at"])) for f in r.files().values())
    assert states == [("List the home directory (exfil try)", True, False, False),
                      ("Read the dataset", False, True, False),
                      ("Try the canary", False, False, True)], states
    r.ok("final: three sessions, tagged and pinned / hidden / deleted; reload shows both tool cards")


def check_close_tab(r: Run, ids: dict[str, str]) -> None:
    """A run goes on when its tab is closed: the server records all of it, completed.

    Uses the hidden session, so the three sessions above keep their state and the first one its two runs.
    """
    # Not `r.page.context.new_page()`: Playwright's sync API refuses new_page() on a context
    # made by `browser.new_page()` ("Please use browser.new_context()"); a fresh context gives
    # an independent tab just as well here.
    page = r.page.context.browser.new_context().new_page()
    page.goto(f"{BASE}/?session={ids['second']}")
    expect(page.get_by_text("Turn 1: the command ran.")).to_be_visible(timeout=10_000)
    box = page.get_by_test_id("copilot-chat-textarea")
    box.fill("Read it again, slow please")
    box.press("Enter")
    expect(page.get_by_text("Slow step 1 of 10.")).to_be_visible(timeout=20_000)
    page.close()
    assert len(r.files()[ids["second"]]["runs"]) == 1, "the slow run was saved before it could have ended"
    rec = r.wait_runs(ids["second"], 2, seconds=15)
    assert rec["runs"][-1]["status"] == "completed", rec["runs"]
    answer = [m for m in rec["messages"] if m["role"] == "assistant" and isinstance(m.get("content"), str)][-1]
    assert "Slow step 10 of 10." in answer["content"], answer["content"]
    assert "Turn 2: the command ran." in answer["content"], answer["content"]
    assert rec["hidden"] is True and rec["title"] == "Read the dataset", rec
    r.ok("closing the tab mid-run: the whole run is on disk, completed")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shots", type=Path, help="write numbered screenshots here")
    ap.add_argument("--sessions", type=Path, help="sessions directory to use and keep (default: a temporary one)")
    args = ap.parse_args()
    standalone = APP / ".next" / "standalone"
    if not (standalone / "server.js").exists():
        sys.exit("FAIL: run `npm ci && npm run build` in platform/agui/copilotkit-chat first")
    shutil.copytree(APP / ".next" / "static", standalone / ".next" / "static", dirs_exist_ok=True)
    data = args.sessions or Path(tempfile.mkdtemp(prefix="spe-e2e-")) / "sessions"
    data.mkdir(parents=True, exist_ok=True)
    if args.shots:
        args.shots.mkdir(parents=True, exist_ok=True)
    procs = [subprocess.Popen(["uv", "run", "--group", "dev", "python", "../../dev/fake_agent.py",
                               "--port", str(AGENT_PORT), "--key", KEY], cwd=AGENT_DIR)]
    try:
        wait_http(f"http://127.0.0.1:{AGENT_PORT}/healthz", "the fake agent")
        env = {**os.environ, "AGENT_URL": f"http://127.0.0.1:{AGENT_PORT}/agent", "AGENT_API_KEY": KEY,
               "PORT": str(UI_PORT), "HOSTNAME": "127.0.0.1", "SPE_SESSIONS_DIR": str(data),
               "NEXT_MANUAL_SIG_HANDLE": "true"}
        procs.append(subprocess.Popen(["node", "server.js"], cwd=standalone, env=env))
        wait_http(BASE + "/api/sessions", "the chat UI")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            r = Run(page, data, args.shots)
            ids = check_list(r)
            check_focus(r, ids)
            check_menu(r, ids)
            check_close_tab(r, ids)
            browser.close()
        print(f"sessions: {data}")
    finally:
        for proc in reversed(procs):
            proc.terminate()
            proc.wait(timeout=35)


if __name__ == "__main__":
    main()
