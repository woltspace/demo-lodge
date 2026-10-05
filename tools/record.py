"""Walk the throwaway demo lodge with a real browser and save every response.

Usage: uv run --with playwright python record.py OUT_DIR [LODGE_PORT]

Writes OUT_DIR/records.json: one entry per (origin, path?query) with status,
content type and body (base64). build.py turns that into a static lodge.
"""
import base64
import json
import sys
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

OUT = sys.argv[1]
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 7790
LODGE = f"http://127.0.0.1:{PORT}"
APPS = {"board": f"http://board.localhost:{PORT}", "woodipedia": f"http://woodipedia.localhost:{PORT}"}
WOLTS = ["commie", "uxwolt", "n00b", "scribe"]

ORIGINS = {urlsplit(LODGE).netloc: "lodge", **{urlsplit(u).netloc: n for n, u in APPS.items()}}
records = {}


def keep(resp):
    u = urlsplit(resp.url)
    space = ORIGINS.get(u.netloc)
    if not space or resp.request.method != "GET":
        return
    key = u.path + (("?" + u.query) if u.query else "")
    try:
        body = resp.body()
    except Exception:
        return
    records[f"{space} {key}"] = {
        "space": space, "path": u.path, "query": u.query, "status": resp.status,
        "type": resp.headers.get("content-type", ""),
        "nav": resp.request.is_navigation_request(),
        "body": base64.b64encode(body).decode(),
    }


def visit(pg, url, wait=1800):
    pg.goto(url)
    pg.wait_for_timeout(wait)


with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1400, "height": 900})
    pg.on("response", keep)

    # The lodge
    for path in ["/", "/?view=wolts", "/?view=sessions", "/?view=apps", "/wolves", "/connectors",
                 "/settings", "/tui", "/terminal", "/a/board", "/a/woodipedia"]:
        visit(pg, LODGE + path)
    for w in WOLTS:
        for path in [f"/w/{w}", f"/wolt/{w}/site/", f"/wolt/{w}/_/", f"/wolt/{w}/_/memory", f"/wolt/{w}/_/settings"]:
            visit(pg, LODGE + path)
    visit(pg, LODGE + "/wolt/scribe/site/soundboard.html")

    # Stick Overflow: the list, every thread, the ask page
    visit(pg, APPS["board"] + "/", 2500)
    topics = json.loads(pg.evaluate("fetch('/api/topics?limit=100&open=0').then(r => r.text())"))["topics"]
    for t in topics:
        visit(pg, APPS["board"] + f"/#/t/{t['id']}", 900)
    for h in ["#/new", "#/mine", "#/open", "#/lodges"]:
        visit(pg, APPS["board"] + "/" + h, 900)

    # Woodipedia: every page, its edit and history pages, every old version
    wiki = APPS["woodipedia"]
    for path in ["/", "/all", "/recent", "/new"]:
        visit(pg, wiki + path, 600)
    visit(pg, wiki + "/all", 600)
    slugs = pg.evaluate("[...document.querySelectorAll('main a[href^=\"/wiki/\"]')].map(a => a.getAttribute('href').split('/')[2])")
    for slug in sorted(set(slugs)):
        for path in [f"/wiki/{slug}", f"/wiki/{slug}/edit", f"/wiki/{slug}/history"]:
            visit(pg, wiki + path, 500)
        versions = pg.evaluate("[...document.querySelectorAll('a[href*=\"?v=\"]')].map(a => a.getAttribute('href'))")
        for v in versions:
            visit(pg, wiki + v, 400)
    b.close()

json.dump(records, open(f"{OUT}/records.json", "w"))
print(len(records), "responses")
for k in sorted(records):
    print(records[k]["status"], k[:110])
