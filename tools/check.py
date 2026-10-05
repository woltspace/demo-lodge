"""Screenshot pages of the built demo lodge and list errors.

Usage: uv run --with playwright python check.py BASE_URL OUT_DIR PATH[|typed;lines] ...
"""
import sys

from playwright.sync_api import sync_playwright

base, out, paths = sys.argv[1], sys.argv[2], sys.argv[3:]
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1400, "height": 900})
    errs = []
    pg.on("console", lambda m: m.type == "error" and errs.append(m.text[:160]))
    pg.on("response", lambda r: r.status >= 400 and errs.append(f"{r.status} {r.url[:120]}"))
    for i, path in enumerate(paths):
        typed = None
        if "|" in path:
            path, typed = path.split("|", 1)
        pg.goto(base + path)
        pg.wait_for_timeout(2200)
        if typed:
            pg.click(".xterm")
            for line in typed.split(";"):
                pg.keyboard.type(line)
                pg.keyboard.press("Enter")
                pg.wait_for_timeout(1300)
        pg.screenshot(path=f"{out}/s{i}.png")
        print(i, path, "|", pg.title(), "| errors:", errs[:6])
        errs.clear()
    b.close()
