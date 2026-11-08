"""All-features check of the AG-UI chat through an SSH tunnel on :13000 (docs/knowledge/agui-all-features-check.md).

Usage: python3 agui-all-features-check.py <screenshot dir>. Makes about five paid model calls.
"""
import os, subprocess, sys, time
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:13000/"
SHOTS = sys.argv[1] if len(sys.argv) > 1 else "."
results = []


def ok(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f" — {detail}" if detail else ""), flush=True)


def vm(cmd):
    return subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "LogLevel=ERROR",
                           os.environ.get("SPE_HOST", "agent-service-1"), cmd], capture_output=True, text=True).stdout


def run_ends():
    out = vm("docker exec spe-frontend-chat-ui-1 sh -c 'cat /data/sessions/*.jsonl' | grep -c run_end")
    return int(out.strip() or 0)


def send(page, text, timeout=600):
    before = run_ends()
    box = page.locator("textarea").first
    box.fill(text)
    box.press("Enter")
    t0 = time.time()
    while time.time() - t0 < timeout:
        if run_ends() > before:
            page.wait_for_timeout(1500)
            return True
        time.sleep(5)
    return False


with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--no-sandbox"])
    page = b.new_page(viewport={"width": 1400, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(URL)
    page.wait_for_load_state("networkidle")

    # theme: toggle top right, persists over a reload without a flash
    tog = page.get_by_role("switch", name="Dark mode")
    if tog.get_attribute("aria-checked") != "true":
        tog.click()
    page.add_init_script("document.addEventListener('DOMContentLoaded',()=>{window.__t=document.documentElement.dataset.theme})")
    page.reload(); page.wait_for_load_state("networkidle")
    ok("theme dark at DOMContentLoaded", page.evaluate("window.__t") == "dark", page.evaluate("window.__t"))
    box = tog.bounding_box()
    ok("theme toggle top right", box and box["x"] > 1200 and box["y"] < 60, str(box))

    # sidebar drag +120 px, kept over a reload
    r = page.locator(".spe-sidebar-resizer")
    rb = r.bounding_box(); x0 = rb["x"] + rb["width"] / 2
    page.mouse.move(x0, rb["y"] + 200); page.mouse.down(); page.mouse.move(x0 + 120, rb["y"] + 200, steps=10); page.mouse.up()
    page.reload(); page.wait_for_load_state("networkidle")
    x1 = page.locator(".spe-sidebar-resizer").bounding_box()["x"]
    ok("sidebar width kept after drag + reload", abs(x1 - rb["x"] - 120) < 8, f"{rb['x']:.0f} -> {x1:.0f}")

    # new chat, a tool-using prompt
    page.get_by_role("button", name="New chat").click()
    ok("new chat heading", page.get_by_role("heading", name="New chat").count() > 0)
    done = send(page, "List the files in the dataset directory and tell me which look sensitive.")
    ok("tool run ended", done)
    page.screenshot(path=f"{SHOTS}/1-tools.png", full_page=True)
    groups = page.locator(".spe-tool-group")
    ok("tool calls grouped", groups.count() > 0 or page.locator(".spe-tool").count() > 0,
       f"groups={groups.count()} cards={page.locator('.spe-tool').count()}")
    if groups.count():
        summ = groups.first.locator(":scope > summary").inner_text()
        ok("group header says Explored", "Explored" in summ, summ.replace("\n", " "))

    # model title
    title = ""
    for _ in range(24):
        t = page.locator(".spe-header-title")
        if t.count() and t.inner_text().strip() not in ("", "New chat"):
            title = t.inner_text().strip(); break
        page.wait_for_timeout(5000)
    ok("model title", title, title)

    # rename from the header menu
    page.get_by_role("button", name="Chat actions").click()
    page.get_by_role("menuitem", name="Rename").click()
    inp = page.get_by_label("Chat title")
    inp.fill("Recheck after upstream merge"); inp.press("Enter")
    page.wait_for_timeout(1000)
    ok("rename", page.locator(".spe-header-title").inner_text().strip() == "Recheck after upstream merge")

    # /compact with a focus between two no-tool questions
    ok("no-tool question", send(page, "In one sentence: what is a canary file?"))
    ok("/compact ran", send(page, "/compact keep the canary paths", timeout=600))
    ok("compaction divider", page.locator(".spe-compaction").count() == 1, str(page.locator(".spe-compaction").count()))
    ok("same question after compact", send(page, "In one sentence: what is a canary file?"))
    page.screenshot(path=f"{SHOTS}/2-compact.png", full_page=True)

    # reload: everything still there
    page.reload(); page.wait_for_load_state("networkidle"); page.wait_for_timeout(2000)
    ok("after reload: title", page.locator(".spe-header-title").inner_text().strip() == "Recheck after upstream merge")
    ok("after reload: divider", page.locator(".spe-compaction").count() == 1)
    ok("after reload: tool cards", page.locator(".spe-tool-group, .spe-tool").count() > 0)
    page.screenshot(path=f"{SHOTS}/3-reload.png", full_page=True)
    ok("no page errors", not errors, "; ".join(errors)[:300])
    b.close()

print(f"\n{sum(r[1] for r in results)}/{len(results)} passed")
