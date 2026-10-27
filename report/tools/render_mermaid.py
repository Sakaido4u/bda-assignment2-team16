#!/usr/bin/env python3
"""Render report/diagrams/*.mmd to PNG with Mermaid in headless Chromium (Playwright container)."""
import glob
import html
import os

from playwright.sync_api import sync_playwright

PAGE = """<html><head><script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
<style>body{margin:0;background:#fff;font-family:sans-serif} #d{display:inline-block;padding:16px}</style></head>
<body><div id="d"><pre class="mermaid">%s</pre></div>
<script>mermaid.initialize({startOnLoad:true, theme:'default', flowchart:{htmlLabels:true, curve:'basis'}});</script></body></html>"""

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1800, "height": 1200}, device_scale_factor=2)
    for f in sorted(glob.glob("report/diagrams/*.mmd")):
        pg.set_content(PAGE % html.escape(open(f).read()))
        pg.wait_for_selector("#d svg", timeout=30000)
        pg.wait_for_timeout(500)
        out = f[:-4] + ".png"
        pg.locator("#d").screenshot(path=out)
        print("rendered", out)
    b.close()
