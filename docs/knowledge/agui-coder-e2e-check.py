"""End-to-end check of the AG-UI chat in a Coder workspace, through `coder port-forward` on :13000
(docs/knowledge/agui-coder-e2e-check.md). Paid model calls: a few dozen.

Usage: SPE_WS=theo/agui-e2e python3 agui-coder-e2e-check.py <out dir> [--turns N] [--compactions N]

Two tabs: sessions run side by side, the other tab switches into a session mid-run, stop and send again at
once, new / rename / delete, long conversations until each has --compactions compactions (lower the agent's
`context_window_tokens` first), `/compact` with and without a focus, then reload and reopen every session and
compare the chat with its journal. Writes <out dir>/journals.json (the summaries) for the archive comparison.
"""
import argparse, json, os, re, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "platform" / "dev" / "e2e"))
from sessions import read_journal, summary  # noqa: E402
from playwright.sync_api import expect, sync_playwright  # noqa: E402

URL = os.environ.get("SPE_URL", "http://127.0.0.1:13000/")
WS = os.environ.get("SPE_WS", "theo/agui-e2e")
ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--turns", type=int, default=14)
ap.add_argument("--compactions", type=int, default=2)
ap.add_argument("--resume", help="A,B,C,D session ids of an earlier run: skip steps 1-3")
args = ap.parse_args()
OUT = Path(args.out); OUT.mkdir(parents=True, exist_ok=True)
results = []


def ok(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f" — {detail}" if detail else ""), flush=True)


def vm(cmd):
    return subprocess.run(["coder", "ssh", WS, "--", cmd], capture_output=True, text=True).stdout


def journal(sid, tries=5):
    """One session's journal, read whole: `coder ssh` can cut a large output short, so the byte count is checked
    (`head -c` of the counted size: a live run appends between the count and the read).
    A session with no journal yet (its first run not started) reads as no runs."""
    for _ in range(tries):
        out = subprocess.run(["coder", "ssh", WS, "--", "cd ~/spe-frontend && docker compose exec -T chat-ui sh -c "
                              f"'f=/data/sessions/{sid}.jsonl; [ -f $f ] || {{ echo none; exit; }}; n=$(wc -c < $f); echo $n; head -c $n $f'"],
                             capture_output=True).stdout
        head, _, body = out.partition(b"\n")
        if head.strip() == b"none":
            return {"runs": [], "title": None, "deleted_at": None}
        if head.strip().isdigit() and len(body) == int(head):
            return summary(read_journal(body.decode()))
        time.sleep(3)
    raise RuntimeError(f"journal {sid}: no complete copy in {tries} tries")


def journals(*sids):
    return {sid: journal(sid) for sid in sids}


def done_runs(sid):
    return [r for r in journal(sid)["runs"] if r["status"] != "incomplete"]


THREADS = {}  # page -> the threadIds of its runs, in order: the URL gets ?session= only once a run has ended


def track(page):
    THREADS[page] = []
    page.on("request", lambda req: THREADS[page].append(json.loads(req.post_data or "{}").get("threadId"))
            if req.method == "POST" and req.url.endswith("/agent/spe/run") else None)


def session_of(page, seconds=30, after=None):
    """The page's session: from its URL, or (after a submit) the threadId of its newest run request."""
    t0 = time.time()
    while time.time() - t0 < seconds:
        if after is not None and len(THREADS[page]) > after:
            return THREADS[page][-1]
        m = re.search(r"[?&]session=([^&]+)", page.url)
        if m and after is None:
            return m.group(1)
        page.wait_for_timeout(500)
    return None


def errors(page):
    return [t for t in page.locator(".spe-error").all_inner_texts() if t.strip()]


def submit(page, text):
    box = page.get_by_test_id("copilot-chat-textarea")
    box.fill(text)
    box.press("Enter")


def wait_done(page, sid, before, timeout=900):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if len(done_runs(sid)) > before:
            expect(page.get_by_role("button", name="New chat")).to_be_enabled(timeout=60_000)
            page.wait_for_timeout(1000)
            return True
        time.sleep(5)
    return False


def send(page, text, timeout=900):
    """Send in the page's session (a new one if none yet); True when its journal has the run ended."""
    sid = session_of(page, 0.1)
    before = len(done_runs(sid)) if sid else 0
    n = len(THREADS[page])
    submit(page, text)
    sid = sid or session_of(page, after=n)
    return sid, wait_done(page, sid, before, timeout)


def open_session(page, sid):
    page.goto(URL + f"?session={sid}")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)


# CopilotChat virtualizes its message list: only the rows near the viewport are in the DOM (`[data-index]`), so a
# locator count on a long chat misses the rest. Scroll the list top to bottom and count each row once.
CHAT_ROWS = """async () => {
  const count = (el) => [el.querySelectorAll('.copilotKitUserMessage').length, el.querySelectorAll('.spe-compaction').length];
  const first = document.querySelector('[data-index]');
  if (!first) { const [users, compactions] = count(document); return {rows: null, users, compactions}; }  // short: all there
  let box = first.parentElement;  // the ancestor that actually scrolls (inner overflow-y-auto ones fit their content)
  while (box && !(/auto|scroll/.test(getComputedStyle(box).overflowY) && box.scrollHeight > box.clientHeight + 1))
    box = box.parentElement;
  if (!box || box.clientHeight < 1) { const [users, compactions] = count(document); return {rows: null, users, compactions}; }
  const seen = new Map(), pause = () => new Promise((r) => setTimeout(r, 250));
  for (let top = 0, step = 0; step < 2000; top += box.clientHeight / 2, step++) {
    box.scrollTop = top; await pause();
    for (const row of document.querySelectorAll('[data-index]')) seen.set(row.dataset.index, count(row));
    if (top >= box.scrollHeight - box.clientHeight) break;
  }
  box.scrollTop = box.scrollHeight;
  const sum = (i) => [...seen.values()].reduce((n, v) => n + v[i], 0);
  return {rows: seen.size, users: sum(0), compactions: sum(1)};
}"""


def chat_rows(page):
    """The whole chat's rows, user messages and compaction dividers, however long it is."""
    return page.evaluate(CHAT_ROWS)


def compactions(page):
    return chat_rows(page)["compactions"]


def row(page, title):
    return page.locator(".spe-sidebar .spe-row").filter(has=page.locator(".spe-row-title", has_text=title))


with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--no-sandbox"])
    ctx = b.new_context(viewport={"width": 1400, "height": 900})
    A, B = ctx.new_page(), ctx.new_page()
    perr = []
    for pg in (A, B):
        pg.on("pageerror", lambda e: perr.append(str(e)))
        track(pg)
        pg.goto(URL); pg.wait_for_load_state("networkidle")

    if args.resume:
        sA, sB, sC, sD = args.resume.split(",")
    else:
        # 1. two sessions at once; tab B switches into A's session while A's run streams
        A.get_by_role("button", name="New chat").click()
        submit(A, "List the files in /data-share, then count the lines of the two largest text files.")
        sA = session_of(A, after=0)
        B.get_by_role("button", name="New chat").click()
        sB, okB = send(B, "In two sentences: what does a GA4GH WES service do?")
        still = [r["status"] for r in journal(sA)["runs"]] == ["incomplete"]
        ok("two sessions at once: B's run ended while A's ran", okB and sA != sB and still, f"A={sA} B={sB} A running={still}")
        B.goto(URL); B.wait_for_load_state("networkidle")
        open_session(B, sA)
        still = [r["status"] for r in journal(sA)["runs"]] == ["incomplete"]
        B.screenshot(path=str(OUT / "1-switch-mid-run.png"), full_page=True)
        shown = chat_rows(B)["users"]
        ok("tab B opened A's session" + (" mid-run" if still else " (A had already ended)") + ": A's message shown",
           session_of(B, 2) == sA and shown == 1 and not errors(B), f"user messages={shown} {errors(B)}")
        ok("A's run ended", wait_done(A, sA, 0))
        open_session(B, sA)
        st = [r["status"] for r in journal(sA)["runs"]]
        shown = chat_rows(B)["users"]
        ok("B shows A's whole run after it ended", shown == 1 and st == ["completed"],
           f"user messages={shown} runs={st} errors={errors(B)}")

        # 2. stop mid-run and send again at once
        before = len(done_runs(sA))
        submit(A, "Run `sleep 30` in the sandbox, then list /data-share and summarise what is there.")
        expect(A.get_by_role("button", name="New chat")).to_be_disabled(timeout=10_000)
        A.wait_for_timeout(4000)
        A.get_by_test_id("copilot-send-button").click()  # stop
        expect(A.get_by_role("button", name="New chat")).to_be_enabled(timeout=30_000)
        submit(A, "Say OK and nothing else.")
        A.wait_for_timeout(3000)
        errs = errors(A)
        ok("stop then send at once: no 'Thread already running'", not any("already running" in e for e in errs), "; ".join(errs))
        ok("resent run ended", wait_done(A, sA, before + 1))
        errs = errors(A)
        ok("no error in the chat after the resent run", not errs, "; ".join(errs))
        st = [r["status"] for r in journal(sA)["runs"]]
        ok("journal: cancelled then completed", st[-2:] == ["cancelled", "completed"], str(st))

        # 3. new, rename, delete
        B.goto(URL); B.wait_for_load_state("networkidle")
        B.get_by_role("button", name="New chat").click()
        sC, okC = send(B, "Say hi in three words.")
        B.wait_for_timeout(3000)
        ok("third session ran", okC)
        B.get_by_role("button", name="Chat actions").click()
        B.get_by_role("menuitem", name="Rename").click()
        B.get_by_label("Chat title").fill("E2E long C"); B.get_by_label("Chat title").press("Enter")
        expect(row(B, "E2E long C")).to_have_count(1, timeout=10_000)
        ok("rename kept in the journal", journal(sC)["title"] == "E2E long C", journal(sC)["title"])
        B.get_by_role("button", name="New chat").click()
        sD, okD = send(B, "Say bye in three words.")
        B.wait_for_timeout(3000)
        title_d = journal(sD)["title"]
        row(B, title_d).first.locator(".spe-row-menu").click()
        B.get_by_role("menuitem", name="Delete").click()
        B.get_by_role("alertdialog").get_by_role("button", name="Delete").click()
        expect(row(B, title_d)).to_have_count(0, timeout=10_000)
        ok("delete: row gone, journal kept with deleted_at", journal(sD)["deleted_at"] is not None)

    # 4. long conversations in A and C: several compactions each, /compact with and without a focus
    for page, sid, cmd in ((A, sA, "/compact"), (B, sC, "/compact keep the line counts and file names")):
        open_session(page, sid)
        if (n := compactions(page)) >= args.compactions + 1:
            ok(f"{sid[:8]}: already {n} compactions", True)
            continue
        _, okc = send(page, cmd)
        n0, n = n, compactions(page)
        ok(f"{cmd!r} in {sid[:8]} ran", okc and n > n0, f"dividers {n0} -> {n}")
        turn = 0
        while n < args.compactions + 1 and turn < args.turns:
            turn += 1
            _, okt = send(page, f"Turn {turn}: run `seq 1 3000` exactly as written, without pipes, filters or "
                                "redirection, then read its whole output and tell me only the last line it printed.")
            if not okt:
                ok(f"turn {turn} in {sid[:8]} ended", False); break
            if errors(page):
                ok(f"turn {turn} in {sid[:8]}: no error in the chat", False, "; ".join(errors(page))); break
            n = compactions(page)
        ok(f"{sid[:8]}: {n} compactions after {turn} turns", n >= args.compactions + 1)
        page.screenshot(path=str(OUT / f"4-long-{sid[:8]}.png"), full_page=True)

    # 5. reload and reopen each session: the chat agrees with its journal
    rec = journals(sA, sB, sC)
    for sid in (sA, sB, sC):
        open_session(A, sid)
        users = [m for r in rec[sid]["runs"] for m in r["messages"] if m["role"] == "user"]
        shown = chat_rows(A)["users"]
        ok(f"reopened {sid[:8]}: user messages shown = journaled", shown == len(users), f"{shown} vs {len(users)}")
        ok(f"reopened {sid[:8]}: no error", not errors(A), "; ".join(errors(A)))
    A.screenshot(path=str(OUT / "5-reopened.png"), full_page=True)
    ok("no page errors", not perr, "; ".join(perr)[:300])
    (OUT / "journals.json").write_text(json.dumps(rec, indent=1))
    (OUT / "ids.json").write_text(json.dumps({"A": sA, "B": sB, "C": sC, "D": sD}))
    b.close()

print(f"\n{sum(r[1] for r in results)}/{len(results)} passed")
