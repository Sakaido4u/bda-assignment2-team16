#!/usr/bin/env python3
"""Screenshot helper for the report appendix (runs in the Playwright container on bda16-net).

  docker run --rm --network bda16-net -v ${PWD}:/work -w /work \
      mcr.microsoft.com/playwright/python:v1.48.0-jammy \
      bash -c "pip install -q playwright==1.48.0 && python report/tools/capture.py report/tools/shots_<x>.json"

Manifest: JSON list of shots
  {"type": "web",  "name": "fig03_namenode", "url": "http://master:9870/dfshealth.html", "wait_ms": 3000,
   "full_page": false, "click": "css selector (optional)", "select": {"#id": "value"}, "wait_for": "selector",
   "height": 900}
  {"type": "term", "name": "fig10_dfsadmin", "title": "master: hdfs dfsadmin -report", "file": "report/screenshots/text/x.txt",
   "max_lines": 70}
Images are written to report/screenshots/<name>.png
"""
import html
import json
import os
import sys

from playwright.sync_api import sync_playwright

OUT = "report/screenshots"

TERM_CSS = """
body { margin: 0; background: #e9edf3; font-family: 'DejaVu Sans Mono', 'Liberation Mono', monospace; }
.win { margin: 18px; border-radius: 10px; overflow: hidden; box-shadow: 0 6px 24px rgba(0,0,0,.25); background: #0f1724; }
.bar { background: #2b3445; color: #c9d3e3; font: 13px 'DejaVu Sans', sans-serif; padding: 8px 12px; display: flex; align-items: center; }
.bar i { width: 12px; height: 12px; border-radius: 50%; display: inline-block; margin-right: 7px; }
.bar span { margin-left: 10px; }
pre { margin: 0; padding: 14px 16px; color: #d7e0ee; font-size: 13px; line-height: 1.42; white-space: pre-wrap; word-break: break-all; }
.cmd { color: #7ee787; font-weight: bold; }
.hl { color: #ffd479; }
"""


def render_term(page, shot):
    with open(shot["file"], encoding="utf-8", errors="replace") as f:
        lines = f.read().rstrip("\n").split("\n")
    max_lines = shot.get("max_lines", 70)
    if len(lines) > max_lines:
        keep = max_lines - 1
        lines = lines[:keep] + [f"... ({len(lines) - keep} more lines in {os.path.basename(shot['file'])})"]
    body = []
    for ln in lines:
        e = html.escape(ln)
        if ln.startswith("$ ") or ln.startswith("PS ") or ln.startswith("> "):
            e = f'<span class="cmd">{e}</span>'
        elif any(k in ln for k in shot.get("highlight", [])):
            e = f'<span class="hl">{e}</span>'
        body.append(e)
    doc = (f"<html><head><style>{TERM_CSS}</style></head><body><div class='win'><div class='bar'>"
           f"<i style='background:#ff5f56'></i><i style='background:#ffbd2e'></i><i style='background:#27c93f'></i>"
           f"<span>{html.escape(shot.get('title', ''))}</span></div><pre>{chr(10).join(body)}</pre></div></body></html>")
    page.set_viewport_size({"width": shot.get("width", 1280), "height": 400})
    page.set_content(doc)
    page.screenshot(path=f"{OUT}/{shot['name']}.png", full_page=True)


def render_web(page, shot):
    page.set_viewport_size({"width": shot.get("width", 1440), "height": shot.get("height", 900)})
    page.goto(shot["url"], wait_until="networkidle", timeout=shot.get("timeout_ms", 120000))
    for sel, val in shot.get("select", {}).items():
        page.select_option(sel, val)
        page.wait_for_timeout(300)
    for sel in ([shot["click"]] if isinstance(shot.get("click"), str) else shot.get("click", [])):
        page.click(sel, timeout=30000)
        page.wait_for_timeout(1500)
    if shot.get("wait_for"):
        page.wait_for_selector(shot["wait_for"], timeout=shot.get("timeout_ms", 120000))
    page.wait_for_timeout(shot.get("wait_ms", 1500))
    if shot.get("scroll_to"):
        page.locator(shot["scroll_to"]).first.scroll_into_view_if_needed()
        page.wait_for_timeout(500)
    if shot.get("full_page"):
        # grow the viewport first: a full_page capture resizes the page and Chart.js clears its canvases
        h = page.evaluate("document.documentElement.scrollHeight")
        page.set_viewport_size({"width": shot.get("width", 1440), "height": max(h, 400)})
        page.wait_for_timeout(1200)
    page.screenshot(path=f"{OUT}/{shot['name']}.png")


def main(manifest):
    os.makedirs(OUT, exist_ok=True)
    shots = json.load(open(manifest))
    only = set(sys.argv[2:])
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(device_scale_factor=1, locale="en-IN", timezone_id="Asia/Kolkata",
                                  geolocation={"latitude": 12.9716, "longitude": 77.5946}, permissions=["geolocation"])
        for shot in shots:
            if only and shot["name"] not in only:
                continue
            page = ctx.new_page()
            try:
                (render_term if shot["type"] == "term" else render_web)(page, shot)
                print(f"ok   {shot['name']}")
            except Exception as e:  # noqa: BLE001 - keep going, report failures at the end
                print(f"FAIL {shot['name']}: {e.__class__.__name__}: {str(e)[:200]}")
            finally:
                page.close()
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1])
