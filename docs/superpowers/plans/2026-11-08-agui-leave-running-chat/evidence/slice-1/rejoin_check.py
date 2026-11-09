#!/usr/bin/env python3
"""Decision 42's rejoin check (slice 1 of the leave-running-chat plan): drives the throwaway page
CHAT/app/rejoin-check/page.tsx against the scripted agent (no LLM) and prints what each check saw.

    cd platform/agui/copilotkit-chat && npm run build && \\
      python3 ../../../docs/superpowers/plans/2026-11-08-agui-leave-running-chat/evidence/slice-1/rejoin_check.py \\
      | tee ../../../docs/superpowers/plans/2026-11-08-agui-leave-running-chat/evidence/slice-1/rejoin-check.txt
    ... rejoin_check.py --dedupe --checks CE        # step 4: the page merges the journal's history into the
                                                    # rejoined messages on every change (?dedupe=1)
    ... rejoin_check.py --dedupe wait --checks CE   # the same from the replay's first event on (?dedupe=wait)

Starts platform/dev/fake_agent.py and the standalone chat UI on platform/dev/e2e/sessions.py's ports, the way
its main() does, logs every request to /api/copilotkit/** (method, path), and for each check prints PASS or
FAIL with the message ids the page shows against the journal's (GET /api/sessions/{id}'s `messages`):
  A  two private agents streaming at once;
  B  an ordinary open (no run): no connect, each id once, also after an unmount and remount, a send works;
  C  a reload mid-run with mode=rejoin: connect count, duplicates and gaps at 1 s intervals, the end compared
     with GET; once on a session with earlier runs made through this server process, once on a fresh one;
  D  as C, then the rejoined chat's stop button: the journal's last run_end is `cancelled`;
  E  as C, with a second browser context opening the session instead of a reload.
  C3 (beyond the brief) earlier runs made before a chat UI restart, so the runtime's replay lacks them.
C is data for the verdict, not a gate: its PASS means "each id once and none of the journal's missing, at every
tick and in every id list the page committed (window.__rejoinTrace), and equal to GET's at the end".
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(ROOT / "platform" / "dev" / "e2e"))
from sessions import AGENT_DIR, AGENT_PORT, APP, KEY, UI_PORT, read_journal, summary, wait_http  # noqa: E402

from playwright.sync_api import Browser, Page, expect, sync_playwright  # noqa: E402

BASE = f"http://127.0.0.1:{UI_PORT}"
HERE = Path(__file__).resolve().parent
DEDUPE = ""  # "", "every" or "wait"
SESSIONS: Path = Path()
FAILED: list[str] = []
RESTART_UI = None


def out(line: str = "") -> None:
    print(line, flush=True)


def verdict(check: str, ok: bool, what: str) -> None:
    out(f"{'PASS' if ok else 'FAIL'} {check}: {what}")
    if not ok:
        FAILED.append(check)


# --- the server side: GET and the journal files ---


def get(sid: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"{BASE}/api/sessions/{sid}", timeout=5) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def journal_ids(sid: str) -> tuple[list[str], bool]:
    s = get(sid)
    return ([m["id"] for m in s["messages"]], bool(s["running"])) if s else ([], False)


def runs(sid: str) -> list[dict]:
    path = SESSIONS / f"{sid}.jsonl"
    return summary(read_journal(path.read_text()))["runs"] if path.exists() else []


def wait_ended(sid: str, n: int, seconds: float = 40) -> list[dict]:
    until = time.time() + seconds
    while True:
        rs = runs(sid)
        if sum(r["status"] != "incomplete" for r in rs) >= n or time.time() > until:
            return rs
        time.sleep(0.25)


# --- the browser side ---


class Requests:
    """Every request a page makes to /api/copilotkit/**, with a label for the page."""

    def __init__(self) -> None:
        self.log: list[tuple[float, str, str, str]] = []

    def attach(self, page: Page, label: str) -> None:
        def on_request(req) -> None:
            path = req.url.split("://", 1)[-1].split("/", 1)[-1]
            if path.startswith("api/copilotkit"):
                self.log.append((time.time(), label, req.method, "/" + path))
        page.on("request", on_request)

    def mark(self) -> int:
        return len(self.log)

    def since(self, mark: int, label: str | None = None) -> list[tuple[str, str, str]]:
        return [(lab, m, p) for _, lab, m, p in self.log[mark:] if label is None or lab == label]

    def print_since(self, mark: int) -> None:
        for lab, m, p in self.since(mark):
            out(f"  request [{lab}] {m} {p}")


def connects(reqs: list[tuple[str, str, str]]) -> int:
    return sum(p.rstrip("/").endswith("/connect") for _, _, p in reqs)


CONSOLE: list[str] = []


def watch_console(page: Page, label: str) -> None:
    page.on("console", lambda m: CONSOLE.append(f"[{label}] {m.type}: {m.text}") if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: CONSOLE.append(f"[{label}] pageerror: {e}"))


def url(ids: list[str], mode: str) -> str:
    q = "&".join(f"{k}={v}" for k, v in zip("ab", ids))
    dedupe = {"every": "&dedupe=1", "wait": "&dedupe=wait"}.get(DEDUPE, "")
    return f"{BASE}/rejoin-check?{q}&mode={mode}{dedupe}"


def holder(page: Page, sid: str):
    return page.get_by_test_id(f"holder-{sid}")


def shown(page: Page, sid: str) -> list[str]:
    return json.loads(page.get_by_test_id(f"ids-{sid}").inner_text() or "[]")


def status(page: Page, sid: str) -> str:
    return page.get_by_test_id(f"status-{sid}").inner_text()


def slow_steps(page: Page, sid: str) -> int:
    return page.get_by_test_id(f"chat-{sid}").inner_text().count("Slow step")


def wait_chat(page: Page, sid: str) -> None:
    expect(holder(page, sid).get_by_test_id("copilot-chat-textarea")).to_be_visible(timeout=20_000)


def send(page: Page, sid: str, text: str) -> None:
    box = holder(page, sid).get_by_test_id("copilot-chat-textarea")
    box.fill(text)
    box.press("Enter")


def wait_turn(page: Page, sid: str, turn: int) -> None:
    expect(holder(page, sid).get_by_text(f"Turn {turn}: the command ran.")).to_be_visible(timeout=30_000)


def shot(page: Page, name: str) -> None:
    suffix = {"every": "-dedupe", "wait": "-dedupe-wait"}.get(DEDUPE, "")
    page.screenshot(path=str(HERE / f"rejoin-{name}{suffix}.png"), type="png")


def compare(what: str, mine: list[str], theirs: list[str]) -> bool:
    dups = sorted(i for i, c in Counter(mine).items() if c > 1)
    missing = [i for i in theirs if i not in mine]
    extra = [i for i in mine if i not in theirs]
    same = mine == theirs
    out(f"  {what}: shown {len(mine)} ids, journal {len(theirs)}; equal={same} duplicates={dups} "
        f"journal-not-shown={missing} shown-not-in-journal={extra}")
    if not same and not dups and not missing and not extra:
        out(f"    order differs: shown {mine}")
        out(f"                 journal {theirs}")
    return same and not dups


# --- the checks ---


def check_a(browser: Browser, reqs: Requests) -> None:
    out("== A. Two private agents at once")
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    page = browser.new_context(viewport={"width": 1280, "height": 720}).new_page()
    reqs.attach(page, "A")
    watch_console(page, "A")
    mark = reqs.mark()
    page.goto(url([a, b], "stream"))
    wait_chat(page, a)
    wait_chat(page, b)
    send(page, a, f"slow A {a[:8]}")
    send(page, b, f"slow B {b[:8]}")
    samples, both_growing, shot_taken = [], False, False
    until = time.time() + 40
    while time.time() < until:
        ca, cb = slow_steps(page, a), slow_steps(page, b)
        samples.append((ca, cb))
        if len(samples) >= 2:
            pa, pb = samples[-2]
            if ca > pa and cb > pb and ca < 10 and cb < 10:
                both_growing = True
                if not shot_taken:
                    shot(page, "a-two-streams")
                    shot_taken = True
        if ca >= 10 and cb >= 10:
            break
        time.sleep(1)
    out(f"  slow steps shown (A, B) at 1 s intervals: {samples}")
    ra, rb = wait_ended(a, 1), wait_ended(b, 1)
    out(f"  journal A runs: {[r['status'] for r in ra]}; journal B runs: {[r['status'] for r in rb]}")
    time.sleep(1)
    eq_a = compare("A at the end", shown(page, a), journal_ids(a)[0])
    eq_b = compare("B at the end", shown(page, b), journal_ids(b)[0])
    reqs.print_since(mark)
    ok = (both_growing and [r["status"] for r in ra] == ["completed"] and [r["status"] for r in rb] == ["completed"])
    verdict("A", ok, f"both growing at once={both_growing}; A {[r['status'] for r in ra]}, B {[r['status'] for r in rb]}; "
                     f"ids equal to GET at the end: A {eq_a}, B {eq_b}")
    page.context.close()


def make_runs(page: Page, sid: str, n: int, first_turn: int = 1) -> None:
    """n ordinary runs in the open stream-mode page, each waited for."""
    for i in range(n):
        send(page, sid, f"earlier run {first_turn + i} {sid[:8]}")
        wait_turn(page, sid, first_turn + i)


def check_b(browser: Browser, reqs: Requests) -> None:
    out("== B. Ordinary open (the stop point)")
    sid = str(uuid.uuid4())
    page = browser.new_context(viewport={"width": 1280, "height": 720}).new_page()
    reqs.attach(page, "B")
    watch_console(page, "B")
    page.goto(url([sid], "stream"))
    wait_chat(page, sid)
    make_runs(page, sid, 3)
    rs = wait_ended(sid, 3)
    out(f"  seeded: {[r['status'] for r in rs]}")
    console_mark = len(CONSOLE)
    mark = reqs.mark()
    page.goto(url([sid], "open"))
    expect(page.get_by_test_id(f"status-{sid}")).to_contain_text("opened", timeout=20_000)
    wait_chat(page, sid)
    time.sleep(1.5)  # room for a connect, if CopilotChat made one
    ok_open = compare("after open", shown(page, sid), journal_ids(sid)[0])
    n_connect_open = connects(reqs.since(mark))
    reqs.print_since(mark)
    out(f"  connect requests on open: {n_connect_open}")

    mark = reqs.mark()
    page.get_by_test_id(f"remount-{sid}").click()
    expect(page.get_by_test_id(f"generation-{sid}")).to_have_text("1")
    expect(page.get_by_test_id(f"status-{sid}")).to_contain_text("opened", timeout=20_000)
    wait_chat(page, sid)
    time.sleep(1.5)
    ok_remount = compare("after unmount and remount", shown(page, sid), journal_ids(sid)[0])
    n_connect_remount = connects(reqs.since(mark))
    reqs.print_since(mark)
    registered = [c for c in CONSOLE[console_mark:] if "already registered" in c]
    out(f"  connect requests on remount: {n_connect_remount}; 'already registered' console lines: {registered}")

    mark = reqs.mark()
    send(page, sid, f"fourth run {sid[:8]}")
    wait_turn(page, sid, 4)
    rs = wait_ended(sid, 4)
    time.sleep(1)
    ok_send = compare("after a send", shown(page, sid), journal_ids(sid)[0])
    reqs.print_since(mark)
    out(f"  journal runs: {[r['status'] for r in rs]}")
    ok = (ok_open and ok_remount and ok_send and n_connect_open == 0 and n_connect_remount == 0 and not registered
          and [r["status"] for r in rs] == ["completed"] * 4)
    verdict("B", ok, f"no connect (open {n_connect_open}, remount {n_connect_remount}); ids equal and once: open "
                     f"{ok_open}, remount {ok_remount}, after send {ok_send}; journal runs {len(rs)}")
    page.context.close()


def follow(page: Page, sid: str, label: str, stop_after: float | None = None) -> dict:
    """At 1 s intervals until GET answers running false (and two ticks more): the ids the page shows against
    GET's, every id shown more than once and every journal id not shown. stop_after: click the holder's
    stop button that many seconds in."""
    seen_dups: set[str] = set()
    seen_gaps: set[str] = set()
    ticks, started, after_end, stopped = 0, time.time(), 0, False
    first_steps = None  # the slow steps the first tick's line shows (the caller waits for the chat to render)
    while True:
        ticks += 1
        steps = slow_steps(page, sid)
        if first_steps is None:
            first_steps = steps
        mine = shown(page, sid)
        theirs, running = journal_ids(sid)
        dups = sorted(i for i, c in Counter(mine).items() if c > 1)
        gaps = [i for i in theirs if i not in mine]
        extra = [i for i in mine if i not in theirs]
        seen_dups.update(dups)
        seen_gaps.update(gaps)
        out(f"  [{label}] t={time.time() - started:4.1f}s running={running} status={status(page, sid)!r} "
            f"steps={steps} shown={len(mine)} journal={len(theirs)} dups={dups} "
            f"journal-not-shown={gaps} shown-not-in-journal={extra}")
        if stop_after is not None and not stopped and time.time() - started >= stop_after:
            stop = holder(page, sid).get_by_test_id("copilot-send-button")
            out(f"  [{label}] clicking the stop button (aria-label {stop.get_attribute('aria-label')!r})")
            stop.click()
            stopped = True
        if not running:
            after_end += 1
            if after_end > 2:
                break
        if time.time() - started > 60:
            out(f"  [{label}] gave up after 60 s")
            break
        time.sleep(1)
    return {"dups": sorted(seen_dups), "gaps": sorted(seen_gaps), "first_steps": first_steps,
            "last_steps": slow_steps(page, sid)}


def trace(page: Page, sid: str, before: list[str]) -> dict:
    """Every list of ids the page committed (window.__rejoinTrace) from the rejoin on, against the journal's
    ids at the moment of the rejoin: how many lists held a duplicate, how many lacked one of those ids."""
    entries = page.evaluate(f"(window.__rejoinTrace || {{}})[{json.dumps(sid)}] || []")
    entries = [e for e in entries if e["status"].startswith("connect")]
    dup_lists = [e for e in entries if len(set(e["ids"])) != len(e["ids"])]
    gap_lists = [e for e in entries if any(i not in e["ids"] for i in before)]
    t0 = entries[0]["t"] if entries else 0
    out(f"  committed id lists from the connect on: {len(entries)}; with a duplicate: {len(dup_lists)}; lacking one "
        f"of the {len(before)} ids the journal held at the rejoin: {len(gap_lists)} "
        f"(lengths {[len(e['ids']) for e in gap_lists]}, at ms {[e['t'] - t0 for e in gap_lists]}); "
        f"lengths in order: {[len(e['ids']) for e in entries]}, the first five at ms {[e['t'] - t0 for e in entries[:5]]}")
    return {"lists": len(entries), "dup_lists": len(dup_lists), "gap_lists": len(gap_lists)}


def start_slow(browser: Browser, reqs: Requests, label: str, earlier: int,
               restart: bool = False) -> tuple[Page, str]:
    """A session with `earlier` completed runs made through this server, then a slow run under way. restart:
    the chat UI is restarted after the earlier runs, and the page reopens the session from its journal (open
    mode) before the slow run, so the runtime holds only the slow run."""
    sid = str(uuid.uuid4())
    page = browser.new_context(viewport={"width": 1280, "height": 720}).new_page()
    reqs.attach(page, f"{label}-1")
    watch_console(page, f"{label}-1")
    page.goto(url([sid], "stream"))
    wait_chat(page, sid)
    make_runs(page, sid, earlier)
    if restart:
        wait_ended(sid, earlier)
        RESTART_UI()
        page.goto(url([sid], "open"))
        expect(page.get_by_test_id(f"status-{sid}")).to_contain_text("opened", timeout=20_000)
        wait_chat(page, sid)
    send(page, sid, f"slow run {sid[:8]}")
    expect(holder(page, sid).get_by_text("Slow step 2 of")).to_be_visible(timeout=30_000)
    return page, sid


def rejoin(browser: Browser, reqs: Requests, label: str, earlier: int, how: str,
           stop_after: float | None = None, restart: bool = False) -> dict:
    page, sid = start_slow(browser, reqs, label, earlier, restart)
    out(f"  session {sid}, {earlier} earlier run(s){' before a chat UI restart' if restart else ''}; journal before the {how}: {len(journal_ids(sid)[0])} ids, "
        f"runs {[r['status'] for r in runs(sid)]}")
    before = journal_ids(sid)[0]
    mark = reqs.mark()
    if how == "reload":
        viewer, vlabel = page, f"{label}-1"
        page.goto(url([sid], "rejoin"))
    else:
        viewer = browser.new_context(viewport={"width": 1280, "height": 720}).new_page()
        vlabel = f"{label}-2"
        reqs.attach(viewer, vlabel)
        watch_console(viewer, vlabel)
        viewer.goto(url([sid], "rejoin"))
    expect(viewer.get_by_test_id(f"status-{sid}")).not_to_have_text("waiting", timeout=20_000)
    wait_chat(viewer, sid)  # so the first tick's slow-step count reads a rendered chat
    res = follow(viewer, sid, vlabel, stop_after)
    res["trace"] = trace(viewer, sid, before)
    if how == "second-tab":
        res["first_tab_end"] = shown(page, sid)
    time.sleep(1)
    res["final_ok"] = compare(f"{label} at the end", shown(viewer, sid), journal_ids(sid)[0])
    if how == "second-tab":
        compare(f"{label} first tab at the end", shown(page, sid), journal_ids(sid)[0])
    reqs.print_since(mark)
    res["connects"] = connects(reqs.since(mark, vlabel))
    res["runs"] = [r["status"] for r in wait_ended(sid, earlier + 1, seconds=10)]
    res["sid"], res["viewer"], res["page"] = sid, viewer, page
    out(f"  connect requests from the rejoining page: {res['connects']}; journal runs {res['runs']}; "
        f"slow steps shown at the first tick {res['first_steps']}, at the end {res['last_steps']}")
    out(f"  every id shown more than once: {res['dups']}; every journal id not shown at some tick: {res['gaps']}")
    return res


def close(res: dict) -> None:
    res["viewer"].context.close()
    if res["page"].context is not res["viewer"].context:
        res["page"].context.close()


def check_c(browser: Browser, reqs: Requests) -> None:
    cases = ((2, "C1", False, "with earlier runs through this server process"), (0, "C2", False, "a fresh session"),
             (2, "C3", True, "earlier runs made before a chat UI restart: only the journal holds them"))
    for earlier, label, restart, what in cases:
        out(f"== C. Rejoin after a reload ({label}: {what})")
        res = rejoin(browser, reqs, label, earlier, "reload", restart=restart)
        if label == "C1":
            shot(res["viewer"], "c-after-run")
        ok = (res["final_ok"] and not res["dups"] and not res["gaps"] and not res["trace"]["dup_lists"]
              and not res["trace"]["gap_lists"] and res["connects"] == 1 and res["last_steps"] == 10)
        verdict(label, ok, f"connects {res['connects']}; duplicates {len(res['dups'])}; ids missing at some tick "
                           f"{len(res['gaps'])}; committed lists with a duplicate {res['trace']['dup_lists']}, "
                           f"lacking a history id {res['trace']['gap_lists']} of {res['trace']['lists']}; slow steps shown at the end {res['last_steps']} of 10 (exactly 10: streamed whole, none repeated); "
                           f"equal to GET at the end {res['final_ok']}; runs {res['runs']}")
        close(res)


def check_d(browser: Browser, reqs: Requests) -> None:
    out("== D. Stop in the rejoined chat")
    res = rejoin(browser, reqs, "D", 1, "reload", stop_after=2)
    last = res["runs"][-1] if res["runs"] else None
    stops = [r for r in reqs.log if r[1] == "D-1" and "/agent/spe/stop" in r[3]]
    out(f"  stop requests: {len(stops)}")
    verdict("D", last == "cancelled", f"last run_end {last!r}; runs {res['runs']}; stop requests {len(stops)}")
    close(res)


def check_e(browser: Browser, reqs: Requests) -> None:
    out("== E. Second tab")
    res = rejoin(browser, reqs, "E", 1, "second-tab")
    shot(res["viewer"], "e-second-tab")
    # "as C": the same criterion.
    ok = (res["final_ok"] and not res["dups"] and not res["gaps"] and not res["trace"]["dup_lists"]
          and not res["trace"]["gap_lists"] and res["connects"] == 1 and res["last_steps"] == 10)
    verdict("E", ok, f"connects {res['connects']}; duplicates {len(res['dups'])}; ids missing at some tick "
                     f"{len(res['gaps'])}; committed lists with a duplicate {res['trace']['dup_lists']}, "
                     f"lacking a history id {res['trace']['gap_lists']} of {res['trace']['lists']}; slow steps shown at the end {res['last_steps']} of 10 (exactly 10: streamed whole, none repeated); "
                     f"equal to GET at the end {res['final_ok']}; runs {res['runs']}")
    close(res)


CHECKS = {"A": check_a, "B": check_b, "C": check_c, "D": check_d, "E": check_e}


def port_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def main() -> None:
    global DEDUPE, SESSIONS
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dedupe", nargs="?", const="every", default="", choices=("every", "wait"),
                    help="step 4: the page's dedupe layer, merging on every change (?dedupe=1, the default) or "
                         "from the replay's first event on (?dedupe=wait)")
    ap.add_argument("--checks", default="ABCDE", help="which checks to run (default ABCDE)")
    args = ap.parse_args()
    DEDUPE = args.dedupe
    standalone = APP / ".next" / "standalone"
    if not (standalone / "server.js").exists():
        sys.exit("FAIL: run `npm ci && npm run build` in platform/agui/copilotkit-chat first")
    for port in (AGENT_PORT, UI_PORT):
        if not port_free(port):
            sys.exit(f"FAIL: port {port} is taken (another e2e run?)")
    shutil.copytree(APP / ".next" / "static", standalone / ".next" / "static", dirs_exist_ok=True)
    SESSIONS = Path(tempfile.mkdtemp(prefix="spe-rejoin-")) / "sessions"
    SESSIONS.mkdir(parents=True)
    procs = [subprocess.Popen(["uv", "run", "--group", "dev", "python", "../../dev/fake_agent.py",
                               "--port", str(AGENT_PORT), "--key", KEY], cwd=AGENT_DIR)]
    try:
        wait_http(f"http://127.0.0.1:{AGENT_PORT}/healthz", "the fake agent")
        env = {**os.environ, "AGENT_URL": f"http://127.0.0.1:{AGENT_PORT}/agent", "AGENT_API_KEY": KEY,
               "PORT": str(UI_PORT), "HOSTNAME": "127.0.0.1", "SPE_SESSIONS_DIR": str(SESSIONS),
               "NEXT_MANUAL_SIG_HANDLE": "true", "COPILOTKIT_TELEMETRY_DISABLED": "true", "DO_NOT_TRACK": "1"}
        def start_ui() -> subprocess.Popen:
            return subprocess.Popen(["node", "server.js"], cwd=standalone, env=env)

        def restart_ui() -> None:
            """SIGTERM (the drain), then a fresh process: the runtime's memory of past runs is gone."""
            procs[-1].terminate()
            procs[-1].wait(timeout=35)
            procs[-1] = start_ui()
            wait_http(BASE + "/api/sessions", "the chat UI after a restart")

        global RESTART_UI
        RESTART_UI = restart_ui
        procs.append(start_ui())
        wait_http(BASE + "/api/sessions", "the chat UI")
        out(f"rejoin check, {time.strftime('%Y-%m-%d %H:%M:%S')}, dedupe layer {DEDUPE or 'off'}, "
            f"CopilotKit {json.loads((APP / 'node_modules/@copilotkit/react-core/package.json').read_text())['version']}")
        reqs = Requests()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            for name in args.checks:
                try:
                    CHECKS[name](browser, reqs)
                except Exception as e:  # a check that throws is reported and the rest still run
                    verdict(name, False, f"raised {type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}")
            browser.close()
        out("== Browser console (errors and warnings)")
        for line in CONSOLE:
            out(f"  {line[:300]}")
        out(f"== Summary: {'all PASS' if not FAILED else 'FAIL: ' + ' '.join(FAILED)}")
    finally:
        for proc in reversed(procs):
            proc.terminate()
            proc.wait(timeout=35)


if __name__ == "__main__":
    main()
