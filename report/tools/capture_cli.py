#!/usr/bin/env python3
"""Fallback screenshot tool that needs no pip packages: drives the Chromium binary shipped in the
Playwright image directly from its command line (headless --screenshot). Same manifest format as
capture.py, but "click"/"select" are not supported - pages that need interaction take URL
parameters instead (e.g. the dashboard's /hive?qid=...&autorun=1).

  docker run --rm --network bda16-net -v ${PWD}:/work -w /work \
      mcr.microsoft.com/playwright/python:v1.48.0-jammy python3 report/tools/capture_cli.py <manifest.json> [names...]
"""
import glob
import html
import json
import math
import os
import subprocess
import sys
import tempfile

OUT = "report/screenshots"
CHROME = (glob.glob("/ms-playwright/chromium-*/chrome-linux/chrome") or ["chromium"])[0]

TERM_CSS = """
body { margin: 0; background: #e9edf3; font-family: 'DejaVu Sans Mono', 'Liberation Mono', monospace; }
.win { margin: 18px; border-radius: 10px; overflow: hidden; box-shadow: 0 6px 24px rgba(0,0,0,.25); background: #0f1724; }
.bar { background: #2b3445; color: #c9d3e3; font: 13px 'DejaVu Sans', sans-serif; padding: 8px 12px; display: flex; align-items: center; height: 18px; }
.bar i { width: 12px; height: 12px; border-radius: 50%; display: inline-block; margin-right: 7px; }
.bar span { margin-left: 10px; }
pre { margin: 0; padding: 14px 16px; color: #d7e0ee; font-size: 13px; line-height: 19px; white-space: pre-wrap; word-break: break-all; }
.cmd { color: #7ee787; font-weight: bold; }
.hl { color: #ffd479; }
"""


def chrome(url, path, width, height, budget_ms):
    cmd = [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
           "--force-device-scale-factor=1", f"--window-size={width},{height}",
           f"--virtual-time-budget={budget_ms}", "--run-all-compositor-stages-before-draw",
           f"--screenshot={path}", url]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if r.returncode != 0 or not os.path.exists(path):
        raise RuntimeError(r.stderr[-300:])


def render_term(shot):
    with open(shot["file"], encoding="utf-8", errors="replace") as f:
        lines = f.read().rstrip("\n").replace("\t", "    ").split("\n")
    max_lines = shot.get("max_lines", 70)
    if len(lines) > max_lines:
        keep = max_lines - 1
        lines = lines[:keep] + [f"... ({len(lines) - keep} more lines in {os.path.basename(shot['file'])})"]
    width = shot.get("width", 1280)
    cols = int((width - 36 - 32) / 7.83)          # usable px / DejaVu Sans Mono 13px advance
    visual = sum(max(1, math.ceil(len(l) / cols)) for l in lines)
    height = 36 + 34 + 28 + visual * 19 + 8
    body = []
    for ln in lines:
        e = html.escape(ln)
        if ln.startswith(("$ ", "PS ", "> ", "hive> ")):
            e = f'<span class="cmd">{e}</span>'
        elif any(k in ln for k in shot.get("highlight", [])):
            e = f'<span class="hl">{e}</span>'
        body.append(e)
    doc = (f"<html><head><meta charset='utf-8'><style>{TERM_CSS}</style></head><body><div class='win'><div class='bar'>"
           f"<i style='background:#ff5f56'></i><i style='background:#ffbd2e'></i><i style='background:#27c93f'></i>"
           f"<span>{html.escape(shot.get('title', ''))}</span></div><pre>{chr(10).join(body)}</pre></div></body></html>")
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as t:
        t.write(doc)
    chrome(f"file://{t.name}", f"{OUT}/{shot['name']}.png", width, height, 500)


def render_web(shot):
    chrome(shot["url"], f"{OUT}/{shot['name']}.png", shot.get("width", 1440), shot.get("height", 900),
           shot.get("budget_ms", 8000))


def main(manifest):
    os.makedirs(OUT, exist_ok=True)
    only = set(sys.argv[2:])
    for shot in json.load(open(manifest)):
        if only and shot["name"] not in only:
            continue
        try:
            (render_term if shot["type"] == "term" else render_web)(shot)
            print(f"ok   {shot['name']}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {shot['name']}: {e}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
