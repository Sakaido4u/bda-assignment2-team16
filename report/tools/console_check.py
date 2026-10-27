"""Debug helper: print console messages / errors of a page and optionally evaluate a JS expression."""
from playwright.sync_api import sync_playwright
import sys
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page()
    pg.on("console", lambda m: print("console:", m.type, m.text))
    pg.on("pageerror", lambda e: print("pageerror:", e))
    pg.goto(sys.argv[1], wait_until="networkidle"); pg.wait_for_timeout(3000)
    if len(sys.argv) > 2:
        print("eval:", pg.evaluate(sys.argv[2]))
    b.close()
