#!/usr/bin/env python3
"""Drive the chat UI's session sidebar in a real browser, against the scripted agent (no LLM).

    python3 platform/dev/e2e/sessions.py [--shots DIR] [--sessions DIR] [--color-scheme light|dark]
    python3 platform/dev/e2e/sessions.py --scenario stop --save-delay-ms 1500
    python3 platform/dev/e2e/sessions.py --url http://127.0.0.1:3000 --compose-file F --scenario stop|slow-loop|two-turn

Run `npm ci && npm run build` in platform/agui/copilotkit-chat first. The script starts
platform/dev/fake_agent.py (with uv, in platform/agui/pydantic-ai-agent) and the standalone chat UI
with its own sessions directory, walks the sidebar (list, open, New chat, ?session=, the row menu's
close and focus rules, the row menu, the open session deleted elsewhere) and checks the session files after each step. It ends with three sessions: one tagged and pinned, one hidden, one
deleted, and checks that a run whose tab is closed is still saved whole. Needs Python Playwright with Chromium
(`pip install playwright` and `playwright install chromium`). Exits nonzero on the first failed check.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
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
    patches: list[str] = []
    page.on("request", lambda req: patches.append(req.url)
            if req.method == "PATCH" and req.url.endswith(f"/api/sessions/{ids['first']}") else None)
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
    patches.clear()
    tag_input.fill("leftover")
    page.locator(".spe-note").click()
    expect(page.locator(".spe-popover")).to_have_count(0)
    assert patches == [], patches  # a tag typed but not added must never PATCH
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


# --- search with tag: terms, date groups, Show hidden, header, a stopped run, a failed save --

SAVE_FAILED = "this session could not be saved"


def iso_days_ago(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def seed(r: Run, title: str, days_ago: float, **extra) -> str:
    """A session file written directly (local run only): old timestamps cannot come from a run."""
    sid = str(uuid.uuid4())
    when = iso_days_ago(days_ago)
    record = {"version": 1, "id": sid, "title": title, "title_source": "user", "tags": [], "pinned": False,
              "hidden": False, "created_at": when, "updated_at": when, "deleted_at": None,
              "messages": [], "runs": [], **extra}
    (r.sessions / f"{sid}.json").write_text(json.dumps(record))
    return sid


def groups(r: Run) -> list[str]:
    return r.page.locator(".spe-sidebar .spe-group").evaluate_all("els => els.map(e => e.dataset.group)")


def check_view(r: Run) -> None:
    """After check_close_tab: one pinned session updated today, one hidden, one deleted."""
    page = r.page
    seed(r, "Seeded yesterday", 1, tags=["alpha", "beta"])
    seed(r, "Seeded five days ago", 5, tags=["beta"])
    seed(r, "Seeded long ago", 40)
    seed(r, XSS, 41)
    page.goto(BASE + "/")
    expect(r.row("Seeded long ago")).to_have_count(1, timeout=10_000)
    assert groups(r) == ["Pinned", "Yesterday", "Previous 7 days", "Older"], groups(r)
    r.shot("groups")
    r.ok("groups: Pinned, then Yesterday, Previous 7 days, Older (no unpinned session today)")

    search = page.get_by_label("Search titles")
    search.fill("  SEEDED ")
    expect(r.rows()).to_have_count(3)
    search.fill("five")
    expect(r.rows()).to_have_count(1)
    expect(r.row("Seeded five days ago")).to_have_count(1)
    search.fill("<img")
    expect(r.rows()).to_have_count(1)
    assert page.evaluate("window.__speXss") is None
    r.shot("search")
    search.fill("")
    expect(r.rows()).to_have_count(5)
    r.ok("search: case-insensitive title substring; HTML in a title is text")

    options = page.locator(".spe-search-suggestions [role=option]")
    search.fill("tag:")
    expect(options).to_have_text(["tag:alpha", "tag:beta", "tag:dns", "tag:exfil"])
    search.fill("tag:b")
    expect(options).to_have_text(["tag:beta"])
    search.press("ArrowDown")
    search.press("Enter")
    expect(search).to_have_value("tag:beta ")
    expect(options).to_have_count(0)
    expect(r.rows()).to_have_count(2)
    search.press_sequentially("tag:")
    expect(options).to_have_text(["tag:alpha", "tag:dns", "tag:exfil"])  # beta is named already
    options.first.click()
    expect(search).to_have_value("tag:beta tag:alpha ")
    expect(r.rows()).to_have_count(1)
    expect(r.row("Seeded yesterday")).to_have_count(1)
    expect(r.rows().locator(".spe-chip")).to_have_count(0)  # rows show the title only
    r.shot("tag-search")
    search.fill("tag:beta five")
    expect(r.rows()).to_have_count(1)
    expect(r.row("Seeded five days ago")).to_have_count(1)
    search.fill("tag:al")
    expect(options).to_have_count(1)
    search.press("Escape")
    expect(options).to_have_count(0)
    expect(search).to_have_value("tag:al")
    search.fill("tag:nosuch")
    expect(r.rows()).to_have_count(0)
    expect(page.locator(".spe-empty")).to_have_text("No session matches.")
    search.fill("")
    expect(r.rows()).to_have_count(5)
    r.ok("tag: search: typing tag: suggests the tags in use (arrows and Enter, or a click); two tag: terms must "
         "both match; the rest filters titles; rows show no tags")

    expect(r.row("Read the dataset")).to_have_count(0)
    expect(page.get_by_text("Deleted sessions are kept in the run archive.")).to_be_visible()
    page.get_by_label("Show hidden").check()
    expect(r.row("Read the dataset")).to_have_count(1)
    expect(r.row("Read the dataset")).to_have_class("spe-row spe-row-hidden")
    r.shot("show-hidden")
    page.get_by_label("Show hidden").uncheck()
    expect(r.row("Read the dataset")).to_have_count(0)
    r.ok("Show hidden: the hidden session appears only with the toggle; the deleted one never")


def check_header(r: Run, ids: dict[str, str]) -> None:
    """The header: the title row, renamable in place, and the rows' ⋯ menu; tags only in its tag editor."""
    page = r.page
    title = "List the home directory (exfil try)"
    page.goto(f"{BASE}/?session={ids['first']}")
    header = page.locator(".spe-header")
    expect(header.locator(".spe-header-title")).to_have_text(title, timeout=10_000)
    expect(header).not_to_contain_text("tool call")  # the note is the line under the composer
    actions = header.get_by_role("button", name="Chat actions")
    actions.click()
    page.get_by_role("menuitem", name="Rename").click()
    page.get_by_label("Chat title").fill("Renamed in the header")
    page.get_by_label("Chat title").press("Enter")
    expect(header.locator(".spe-header-title")).to_have_text("Renamed in the header", timeout=5_000)
    expect(r.row("Renamed in the header")).to_have_count(1, timeout=5_000)
    expect(actions).to_be_focused()
    header.locator(".spe-header-title").dblclick()
    page.get_by_label("Chat title").fill("Discarded title")
    page.get_by_label("Chat title").press("Escape")
    expect(header.locator(".spe-header-title")).to_have_text("Renamed in the header")

    actions.click()
    page.get_by_role("menuitem", name="Tags").click()
    page.get_by_label("Add a tag").fill("Header")
    page.get_by_label("Add a tag").press("Enter")
    expect(page.locator(".spe-popover .spe-chip", has_text="header")).to_have_count(1, timeout=5_000)
    page.get_by_role("button", name="Remove tag exfil").click()
    expect(page.locator(".spe-popover .spe-chip")).to_have_count(2, timeout=5_000)
    r.shot("header-tags")
    page.get_by_label("Add a tag").press("Escape")
    expect(page.locator(".spe-popover")).to_have_count(0)
    expect(header.locator(".spe-chip")).to_have_count(0)  # the header shows no tags
    rec = r.files()[ids["first"]]
    assert rec["title"] == "Renamed in the header" and rec["title_source"] == "user", rec["title"]
    assert rec["tags"] == ["dns", "header"], rec["tags"]
    r.shot("header")

    actions.click()
    page.get_by_role("menuitem", name="Delete").click()
    dialog = page.get_by_role("alertdialog")
    expect(dialog).to_contain_text("Delete chat?")
    # The dialog renders inside the header, whose z-index: 10 puts it above the chat below;
    # this shot shows the dialog's backdrop covering the chat, not hidden behind it.
    r.shot("header-delete")
    page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    expect(r.row("Renamed in the header")).to_have_count(1)
    assert r.files()[ids["first"]]["deleted_at"] is None

    page.reload()
    expect(header.locator(".spe-header-title")).to_have_text("Renamed in the header", timeout=10_000)
    expect(page.locator(".spe-tool")).to_have_count(2)
    assert r.url_session() == ids["first"]
    page.get_by_role("button", name="New chat").click()
    expect(header.locator(".spe-header-title")).to_have_text("New chat")
    expect(header.get_by_role("button", name="Chat actions")).to_have_count(0)
    r.ok("header: rename by its menu (Enter saves) and double-click (Esc cancels), tags in the menu's tag editor, "
         "Delete opens the same dialog above the chat (Escape cancels, keeps the file); saved to the file; "
         "reload reopens it with its tool cards; New chat has no menu")


def check_stop(r: Run) -> str:
    """A slow run (fake agent: "slow" in the message) stopped from the chat: controls disabled during
    it, enabled after; the row appears, also with the save delayed (the recorder saves before the
    stop's RUN_ERROR reaches the browser); the file ends with a `cancelled` run. Returns the session id.

    Called right after a `page.goto()` by two of its three callers (the standalone `stop` scenario,
    local and against an instance); the third (the "all" scenario) is already well past its first
    load. Either way, the first click below needs no hydration wait of its own: New chat is
    `disabled` until the page is ready (hydrated, and the agent ready), so Playwright's click (which
    waits for "enabled") is safe whether or not the page is ready yet by the time it runs.
    """
    page = r.page
    title = f"slow run to stop {uuid.uuid4().hex[:8]}"
    page.get_by_role("button", name="New chat").click()
    box = page.get_by_test_id("copilot-chat-textarea")
    box.fill(title)
    box.press("Enter")
    expect(page.get_by_role("button", name="New chat")).to_be_disabled(timeout=5_000)
    for button in page.locator(".spe-row-open").all():
        expect(button).to_be_disabled()
    r.shot("during-run")
    # A stop clicked here, however soon, is now always recorded cancelled: lib/recorder.ts's
    # isAbort() covers both an abort after the agent's response headers (RUN_ERROR code "abort") and
    # one before them (a raw AbortError). No wait needed before this click.
    page.get_by_test_id("copilot-send-button").click()  # the stop button while a run is in progress
    expect(page.get_by_role("button", name="New chat")).to_be_enabled(timeout=15_000)
    for button in page.locator(".spe-row-open").all():
        expect(button).to_be_enabled()
    expect(r.row(title)).to_have_count(1, timeout=5_000)
    assert SAVE_FAILED not in "".join(page.locator(".spe-error").all_inner_texts())
    r.shot("after-stop")
    until = time.time() + 15
    while time.time() < until:
        found = [(sid, f) for sid, f in r.files().items() if f["title"] == title]
        if found and found[0][1]["runs"]:
            sid, rec = found[0]
            assert rec["runs"][-1]["status"] == "cancelled", rec["runs"]
            r.ok("stopped run: controls disabled then enabled, recorded cancelled (row shown)")
            return sid
        time.sleep(0.5)
    sys.exit(f"FAIL: no session file titled {title!r} with a run")


DELETED = "this session was deleted"


def check_deleted_open(r: Run) -> None:
    """The open session deleted elsewhere (here through the API): a message sent in it puts up
    "this session was deleted", and no "could not be saved" follows once the reconciliation is over."""
    page = r.page
    page.get_by_role("button", name="New chat").click()
    expect(page.locator(".spe-header-title")).to_have_text("New chat")
    title = f"deleted while open {uuid.uuid4().hex[:8]}"
    r.send(title, 1)
    expect(r.row(title)).to_have_count(1, timeout=5_000)
    sid = next(sid for sid, f in r.files().items() if f["title"] == title)
    with urllib.request.urlopen(urllib.request.Request(f"{BASE}/api/sessions/{sid}", method="DELETE")) as resp:
        assert resp.status < 300, resp.status
    box = page.get_by_test_id("copilot-chat-textarea")
    box.fill("one more")
    box.press("Enter")
    expect(page.locator(".spe-error")).to_contain_text(DELETED, timeout=10_000)
    time.sleep(3.5)  # longer than the reconciliation's retries
    assert SAVE_FAILED not in "".join(page.locator(".spe-error").all_inner_texts())
    r.shot("deleted-open")
    page.locator(".spe-error").get_by_role("button", name="Dismiss").click()
    r.ok("open session deleted elsewhere: a message says it was deleted, never that it could not be saved")


COMPACTED = "Earlier conversation compacted"
SUMMARY_LINE = "Summary the model continues from"
COMPACTION_XSS = "compact <img src=x onerror=window.__speXss=1>"


def check_compaction(r: Run) -> None:
    """A message that makes the scripted agent compact: the divider appears where the compaction was made,
    live and after a reload; the summary is collapsed, and expanded shows its markup as text."""
    page = r.page
    page.get_by_role("button", name="New chat").click()
    expect(page.locator(".spe-header-title")).to_have_text("New chat")
    box = page.get_by_test_id("copilot-chat-textarea")
    box.fill(COMPACTION_XSS)
    box.press("Enter")
    expect(page.get_by_text("The conversation was compacted.")).to_be_visible(timeout=20_000)
    divider = page.locator(".spe-compaction")
    expect(divider).to_have_count(1)
    expect(divider.locator(".spe-compaction-label")).to_have_text(COMPACTED)
    summary = divider.locator(".spe-compaction-summary")
    expect(summary.locator("> div")).not_to_be_visible()
    r.shot("compaction")
    summary.locator("summary", has_text=SUMMARY_LINE).click()
    expect(summary.locator("> div")).to_contain_text("<img src=x onerror=window.__speXss=1>")
    assert page.evaluate("window.__speXss") is None, "the summary's markup ran"
    assert summary.locator("img").count() == 0
    r.shot("compaction-open")
    # The divider sits between the user's message and the answer that followed the compaction.
    texts = page.locator(".spe-chat").inner_text()
    assert texts.index(COMPACTION_XSS) < texts.index(COMPACTED) < texts.index("The conversation was compacted."), texts
    sid = r.url_session()
    rec = r.wait_runs(sid, 1)
    markers = [m for m in rec["messages"] if str(m.get("id") or "").startswith("spe-compaction-")]
    assert [m["role"] for m in markers] == ["assistant"] and "Scripted summary" in markers[0]["content"], rec
    assert rec["title"] == COMPACTION_XSS, rec["title"]
    page.reload()
    expect(page.locator(".spe-compaction")).to_have_count(1, timeout=10_000)
    expect(page.get_by_text("The conversation was compacted.")).to_be_visible()
    # A later run in the same session still answers, and the divider stays where it was.
    box = page.get_by_test_id("copilot-chat-textarea")
    box.fill("one more")
    box.press("Enter")
    # Turn numbering restarts after a compaction (the sent history is cut), so this later answer is also
    # "Turn 1"; it is told apart from the compacted one by "Its output was:", never in the compacted answer.
    expect(page.get_by_text(re.compile(r"Turn \d+: the command ran\. Its output was:"))).to_have_count(
        1, timeout=20_000)
    expect(page.locator(".spe-compaction")).to_have_count(1)
    r.wait_runs(sid, 2)
    r.ok("compaction: divider in place live and after a reload, summary collapsed and shown as text, record keeps it")


def check_save_failed(r: Run) -> None:
    """The chat UI cannot write the session (its directory made read-only for the run): the
    server's save-failed event puts the error bar up, and the list is not fetched again and again
    (a retrying reconciliation would fetch it 6 times). Local run only, as a normal user."""
    if os.geteuid() == 0:
        sys.exit("FAIL: check_save_failed needs a normal user (root writes to a read-only directory)")
    page = r.page
    lists: list[str] = []
    page.on("request", lambda req: lists.append(req.url)
            if req.method == "GET" and req.url.split("?")[0].endswith("/api/sessions") else None)
    page.get_by_role("button", name="New chat").click()
    expect(page.locator(".spe-header-title")).to_have_text("New chat")
    title = f"run that cannot be saved {uuid.uuid4().hex[:8]}"
    mode = r.sessions.stat().st_mode & 0o7777
    r.sessions.chmod(0o500)
    try:
        lists.clear()
        r.send(title, 1)
        expect(page.locator(".spe-error")).to_contain_text(SAVE_FAILED, timeout=5_000)
        expect(page.get_by_role("button", name="New chat")).to_be_enabled(timeout=5_000)
        time.sleep(3.5)  # longer than five retries 500 ms apart
        assert len(lists) <= 2, lists  # the one fetch after the run, and at most one from New chat
    finally:
        r.sessions.chmod(mode)
    assert not any(f["title"] == title for f in r.files().values())
    r.shot("save-failed")
    r.ok("failed save: the server's event shows the error bar; the list is fetched once, not retried")


def slow_loop(r: Run) -> None:
    """Archive check during a run: slow runs back to back, each in a new session (a second run of
    one thread right after the first can be refused while the server finishes it), until the chat
    UI goes away under the archive's barrier or 12 runs have passed. Prints each run's title; the
    last one printed is the run the barrier stopped."""
    page = r.page
    stamp = uuid.uuid4().hex[:8]
    page.goto(BASE + "/")
    for n in range(1, 13):
        title = f"slow run {stamp}-{n}"
        try:
            # No hydration wait before this first click (n == 1): New chat is `disabled` until
            # the page is ready (hydrated, and the agent ready), so the click's own wait for
            # "enabled" covers it.
            page.get_by_role("button", name="New chat").click(timeout=10_000)
            box = page.get_by_test_id("copilot-chat-textarea")
            box.fill(title)
            box.press("Enter")
            print(f"title {title}", flush=True)
            expect(page.get_by_role("button", name="New chat")).to_be_enabled(timeout=60_000)
        except Exception as e:  # the chat UI went away under the barrier
            print(f"stopped at {title}: {type(e).__name__}", flush=True)
            return
        if page.locator(".spe-error").count():
            print(f"stopped at {title}: {page.locator('.spe-error').inner_text()}", flush=True)
            return


def two_turn(r: Run) -> None:
    """The paid check: two turns with the instance's real model; both runs recorded completed."""
    page = r.page
    page.goto(BASE + "/")
    # No hydration wait needed before this click: New chat is `disabled` until the page is
    # ready (hydrated, and the agent ready), so Playwright's click (which waits for "enabled")
    # is safe either way (as in check_stop).
    page.get_by_role("button", name="New chat").click()
    first = "Run pwd and tell me the result in one sentence."
    for text in (first, "Now list the files in that directory, briefly."):
        box = page.get_by_test_id("copilot-chat-textarea")
        box.fill(text)
        box.press("Enter")
        expect(page.get_by_role("button", name="New chat")).to_be_disabled(timeout=10_000)
        expect(page.get_by_role("button", name="New chat")).to_be_enabled(timeout=120_000)
    expect(r.row(first)).to_have_count(1, timeout=10_000)
    r.shot("two-turn")
    rec = next(f for f in r.files().values() if f["title"] == first)
    assert [x["status"] for x in rec["runs"]] == ["completed", "completed"], rec["runs"]
    r.ok(f"two turns with the real model, both completed (session {rec['id']})")


class InstanceRun(Run):
    """Against an instance's chat UI: the session files are read in the chat-ui container."""

    def __init__(self, page: Page, compose_file: str, shots: Path | None):
        super().__init__(page, Path("/nonexistent"), shots)
        self.compose_file = compose_file

    def files(self) -> dict[str, dict]:
        script = ("const fs=require('fs');const d='/data/sessions';const o={};"
                  "for(const f of fs.readdirSync(d))if(f.endsWith('.json'))"
                  "o[f.slice(0,-5)]=JSON.parse(fs.readFileSync(d+'/'+f,'utf8'));"
                  "process.stdout.write(JSON.stringify(o))")
        out = subprocess.run(["docker", "compose", "-p", "spe-frontend", "-f", self.compose_file, "exec", "-T",
                              "chat-ui", "node", "-e", script], check=True, capture_output=True, text=True)
        return json.loads(out.stdout)


def compaction_live(r: Run, turns: int = 8) -> None:
    """On an instance with a small window: commands with long output until the agent compacts."""
    page = r.page
    page.goto(BASE + "/")
    page.get_by_role("button", name="New chat").click()
    box = page.get_by_test_id("copilot-chat-textarea")
    for turn in range(1, turns + 1):
        box.fill(f"Turn {turn}: run `seq 1 3000` exactly as written, without pipes, filters or redirection, "
                 "then read its whole output and tell me only the last line it printed.")
        box.press("Enter")
        # New chat is disabled while a run is in flight (as two_turn waits for a run's end).
        expect(page.get_by_role("button", name="New chat")).to_be_disabled(timeout=10_000)
        expect(page.get_by_role("button", name="New chat")).to_be_enabled(timeout=120_000)
        if page.locator(".spe-compaction").count():
            break
    assert page.locator(".spe-compaction").count(), f"no compaction after {turns} turns"
    # One turn can compact more than once: the model reads a truncated output again and the window fills again.
    expect(page.locator(".spe-compaction").first).to_be_visible()
    r.shot("live-compaction")
    page.locator(".spe-compaction-summary > summary").first.click()
    r.shot("live-compaction-open")
    print(f"session {r.url_session()}, {page.locator('.spe-compaction').count()} compactions "
          f"after {turn} turns")


LOCAL = ("all", "stop", "compaction")
INSTANCE = ("stop", "slow-loop", "two-turn", "compaction-live")


def main() -> None:
    global BASE
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shots", type=Path, help="write numbered screenshots here")
    ap.add_argument("--sessions", type=Path, help="sessions directory to use and keep (default: a temporary one)")
    ap.add_argument("--scenario", default="all", choices=sorted(set(LOCAL + INSTANCE)),
                    help="all: every check (save-failed last); stop: a stopped run whose save is delayed "
                         "(--save-delay-ms); slow-loop, two-turn: --url only")
    ap.add_argument("--save-delay-ms", type=int, default=0,
                    help="SPE_SESSIONS_TEST_SAVE_DELAY_MS for the local chat UI")
    ap.add_argument("--url", help="an instance's chat UI (e.g. http://127.0.0.1:3000) instead of local servers")
    ap.add_argument("--compose-file", help="with --url: the instance's frontend docker-compose.yml")
    ap.add_argument("--color-scheme", choices=["light", "dark"],
                    help="emulate this colour scheme (for --shots; default: Playwright's own default)")
    args = ap.parse_args()
    if args.shots:
        args.shots.mkdir(parents=True, exist_ok=True)
    if args.url:
        if args.scenario not in INSTANCE or not args.compose_file:
            sys.exit(f"FAIL: --url takes --compose-file and a scenario of {INSTANCE}")
        BASE = args.url.rstrip("/")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1280, "height": 800}, color_scheme=args.color_scheme)
            r = InstanceRun(page, args.compose_file, args.shots)
            if args.scenario == "stop":
                page.goto(BASE + "/")
                print(f"session {check_stop(r)}")
            elif args.scenario == "slow-loop":
                slow_loop(r)
            elif args.scenario == "two-turn":
                two_turn(r)
            else:
                compaction_live(r)
            browser.close()
        return
    if args.scenario not in LOCAL:
        sys.exit(f"FAIL: {args.scenario} needs --url")
    standalone = APP / ".next" / "standalone"
    if not (standalone / "server.js").exists():
        sys.exit("FAIL: run `npm ci && npm run build` in platform/agui/copilotkit-chat first")
    shutil.copytree(APP / ".next" / "static", standalone / ".next" / "static", dirs_exist_ok=True)
    data = args.sessions or Path(tempfile.mkdtemp(prefix="spe-e2e-")) / "sessions"
    data.mkdir(parents=True, exist_ok=True)
    procs = [subprocess.Popen(["uv", "run", "--group", "dev", "python", "../../dev/fake_agent.py",
                               "--port", str(AGENT_PORT), "--key", KEY], cwd=AGENT_DIR)]
    try:
        wait_http(f"http://127.0.0.1:{AGENT_PORT}/healthz", "the fake agent")
        env = {**os.environ, "AGENT_URL": f"http://127.0.0.1:{AGENT_PORT}/agent", "AGENT_API_KEY": KEY,
               "PORT": str(UI_PORT), "HOSTNAME": "127.0.0.1", "SPE_SESSIONS_DIR": str(data),
               "NEXT_MANUAL_SIG_HANDLE": "true", "SPE_SESSIONS_TEST_SAVE_DELAY_MS": str(args.save_delay_ms)}
        procs.append(subprocess.Popen(["node", "server.js"], cwd=standalone, env=env))
        wait_http(BASE + "/api/sessions", "the chat UI")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1280, "height": 800}, color_scheme=args.color_scheme)
            r = Run(page, data, args.shots)
            if args.scenario == "all":
                ids = check_list(r)
                check_focus(r, ids)
                check_menu(r, ids)
                check_close_tab(r, ids)
                check_view(r)
                check_header(r, ids)
                check_deleted_open(r)
                check_compaction(r)
                check_stop(r)
                check_save_failed(r)
            elif args.scenario == "stop":
                page.goto(BASE + "/")
                # New chat is disabled until the page is ready, so the click right after goto is safe
                check_stop(r)
            else:
                page.goto(BASE + "/")
                check_compaction(r)
            browser.close()
        print(f"sessions: {data}")
    finally:
        for proc in reversed(procs):
            proc.terminate()
            proc.wait(timeout=35)


if __name__ == "__main__":
    main()
