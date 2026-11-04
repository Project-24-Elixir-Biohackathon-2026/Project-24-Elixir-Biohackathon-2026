"""Two short Open WebUI chats through a tunnel on :18080, no login (docs/knowledge/agui-coder-e2e-check.md,
*The final archive*). Usage: python3 owui-e2e-chats.py <screenshot dir>. Three paid model calls."""
import sys, time
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:18080/"
OUT = sys.argv[1]
PROMPTS = [
    ["List the files directly under /data with ls and tell me how many there are.", "Thanks. Which one is the largest?"],
    ["What is 17 times 23? Answer with the number only."],
]


def wait_done(page, timeout=600):
    # the send button is replaced by a stop button while a response streams: wait for it to come, then to go
    stop = page.locator("button[aria-label='Stop'], #stop-response-button")
    try:
        stop.first.wait_for(state="visible", timeout=60_000)
    except Exception:
        return False
    t0 = time.time()
    while time.time() - t0 < timeout:
        if stop.count() == 0:
            page.wait_for_timeout(3000)
            if stop.count() == 0:
                return True
        time.sleep(3)
    return False


with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--no-sandbox"])
    page = b.new_page(viewport={"width": 1400, "height": 900})
    for i, chat in enumerate(PROMPTS):
        page.goto(URL)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        for _ in range(3):
            if page.locator("div[role=dialog]").count() == 0:
                break
            btn = page.get_by_role("button", name="Okay, Let's Go!")
            btn.click() if btn.count() else page.keyboard.press("Escape")
            page.wait_for_timeout(1000)
        for j, text in enumerate(chat):
            box = page.locator("#chat-input")
            box.click()
            box.fill(text) if box.evaluate("e => e.tagName") == "TEXTAREA" else page.keyboard.type(text)
            page.keyboard.press("Enter")
            print(f"chat {i} turn {j}: done={wait_done(page)} url={page.url}", flush=True)
        page.screenshot(path=f"{OUT}/owui-{i}.png", full_page=True)
    b.close()
