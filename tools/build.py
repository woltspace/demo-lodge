"""Turn records.json (from record.py) into a static, read-only demo lodge.

Usage: python3 build.py RECORDS_JSON OUT_DIR PREFIX
  PREFIX: where the site will live, e.g. "" for its own domain, "/demo" on
  woltspace.com, "/wolt/commie/site/demo-lodge" for the preview on my site.

Every page and file is the lodge's own output, unchanged except:
  - absolute links get PREFIX in front,
  - machine paths and addresses are replaced with neutral ones,
  - each page loads _demo/demo.js, which answers the lodge's API from the
    recording, refuses every write with a bloop, and fakes the terminals.
"""
import base64
import json
import re
import shutil
import sys
from pathlib import Path

RECORDS, OUT, PREFIX = sys.argv[1], Path(sys.argv[2]), sys.argv[3].rstrip("/")
HERE = Path(__file__).parent
SCRATCH_WOLTS = re.compile(r"/[^\"'\s]*?/demo/wolts")
SCRATCH_HOME = re.compile(r"/[^\"'\s]*?/demo/home")

ROOTS = {
    "lodge": ["static", "w", "wolt", "a", "app", "tui", "terminal", "settings", "connectors", "wolves",
              "sessions", "wolts", "apps", "harnesses", "onboarding", "onboard", "health", "tunnel",
              "history", "wolf", "current", "placeholder.html", "views", "sites", "tools", "version"],
    "board": ["api", "mode", "m"],
    "woodipedia": ["wiki", "all", "recent", "new", "search", "media"],
}

# The four wolts' sessions from the Woodipedia test (titles as they were described).
TEST_AT = 1791110788  # 2026-10-04 06:46 EDT, when the test thread closed
SESSIONS = [
    ("commie", "commie-mossy-ridge-5c21a0", "Woodipedia test: \"What is Woltspace?\"",
     "Posted the plan on Stick Overflow, wrote the hub page and \"Wolts and the lodge\", closed the thread."),
    ("uxwolt", "uxwolt-sleek-pond-dc4669", "Woodipedia test: Sharing and the community",
     "Wrote \"Sharing and the community\", improved \"Wolts and the lodge\", reported what was clunky."),
    ("n00b", "n00b-sturdy-hollow-ef1c9c", "Woodipedia test: Trust and safety",
     "Wrote \"Trust and safety\", made one edit to the hub, verified both saves."),
    ("scribe", "scribe-quiet-fern-0a17b2", "Ideas soundboard",
     "Logs each idea the moment it lands. Sorting happens later."),
]


def space_base(space):
    return PREFIX if space == "lodge" else f"{PREFIX}/app/{space}"


def sanitize(text):
    text = SCRATCH_WOLTS.sub("/Users/you/.woltspace/wolts", text)
    text = SCRATCH_HOME.sub("/Users/you", text)
    text = re.sub(r"(board|woodipedia)\.localhost:7790", r"\1.localhost:7777", text)
    return text.replace("127.0.0.1:7790", "127.0.0.1:7777").replace("localhost:7790", "localhost:7777")


def rewrite(text, space, kind):
    base = space_base(space)
    roots = "|".join(re.escape(r) for r in ROOTS[space])
    # "/root..." inside quotes, backticks, url( ) or after = : gets the base in front.
    text = re.sub(rf"""(["'`(]|=\s*)/(?=(?:{roots})(?:[/"'`?#)\s.]|$))""", rf"\g<1>{base}/", text)
    text = re.sub(r"""(["'`])/\?""", rf"\g<1>{base}/?", text)
    # Static hosts redirect /tui to /tui/ and some drop the ?session= on the way.
    text = text.replace(f"{base}/tui?", f"{base}/tui/?")
    if kind == "html":
        text = re.sub(r"""(href|action)=(["'])/(["'])""", rf"\g<1>=\g<2>{base}/\g<3>", text)
    if kind == "js":
        text = text.replace("? '/' :", f"? '{base}/' :").replace("href='/'", f"href='{base}/'")
    if space == "woodipedia":
        # Old versions are pages of their own here: a static host cannot tell ?v= apart.
        text = re.sub(r"(/wiki/[^\"'?#/]+)\?v=([0-9a-f]{7,40})", r"\1/v/\2/", text)
    return text


def page_file(space, path, query):
    if space == "woodipedia" and query.startswith("v="):
        path = f"{path}/v/{query[2:]}/"
    if not path.endswith("/") and not re.search(r"\.[a-z0-9]+$", path):
        path += "/"
    if path.endswith("/"):
        path += "index.html"
    sub = "" if space == "lodge" else f"app/{space}/"
    return OUT / (sub + path.lstrip("/"))


def head_tags(space):
    cfg = {"prefix": PREFIX, "space": space, "base": space_base(space)}
    return (f'<script>window.__DEMO={json.dumps(cfg)}</script>'
            f'<script src="{PREFIX}/_demo/data-{space}.js"></script>'
            f'<script src="{PREFIX}/_demo/demo.js"></script>')


def inject(html, space):
    tags = head_tags(space)
    m = re.search(r"<head[^>]*>", html, re.I)
    return html[:m.end()] + tags + html[m.end():] if m else tags + html


def main():
    records = json.load(open(RECORDS))
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "_demo").mkdir(parents=True)
    data = {s: {} for s in ROOTS}
    for r in records.values():
        space, path, query, ctype = r["space"], r["path"], r["query"], r["type"]
        body = base64.b64decode(r["body"])
        if r["status"] >= 400:
            continue
        textual = any(t in ctype for t in ("html", "javascript", "json", "css", "svg", "text/plain"))
        if textual:
            body = sanitize(body.decode("utf-8"))
        if "text/html" in ctype:
            if space == "lodge" and query and path in ("/", "/tui", "/terminal"):
                continue  # same page; the view comes from the address
            f = page_file(space, path, query)
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(inject(rewrite(body, space, "html"), space))
        elif "json" in ctype:
            key = path + ("?" + query if query else "")
            data[space][key] = {"s": r["status"], "t": ctype, "b": rewrite(body, space, "json")}
        else:
            sub = "" if space == "lodge" else f"app/{space}/"
            f = OUT / (sub + path.lstrip("/"))
            if path.endswith("/"):
                f = f / "index.html"
            f.parent.mkdir(parents=True, exist_ok=True)
            if textual:
                kind = "js" if "javascript" in ctype else "css"
                f.write_text(rewrite(body, space, kind))
            else:
                f.write_bytes(body)

    # The demo's own data: sessions for the four wolts, avatars on the board.
    sessions = [{"alive": True, "idle_timeout_seconds": 86400, "last_activity": TEST_AT, "name": n,
                 "openable": True, "status": "running", "agent_alive": True, "tmux_alive": True, "summary": s, "title": t, "wolt": w}
                for w, n, t, s in SESSIONS]
    data["lodge"]["/sessions?view=lodge"]["b"] = json.dumps(
        {"sessions": sessions, "totals": {w: 1 for w, *_ in SESSIONS}})
    data["lodge"]["/sessions"] = {"s": 200, "t": "application/json", "b": json.dumps(sessions)}
    info = json.loads(data["board"]["/api/info"]["b"])
    info["creatures"] = {"commie": "raccoon", "uxwolt": "raccoon", "n00b": "raccoon", "scribe": "beaver"}
    data["board"]["/api/info"]["b"] = json.dumps(info)

    for space, entries in data.items():
        (OUT / "_demo" / f"data-{space}.js").write_text(
            "window.__DEMO_DATA=" + json.dumps(entries, ensure_ascii=False) + ";\n")
    shutil.copy(HERE / "demo.js", OUT / "_demo" / "demo.js")
    # Short standalone links to each app, to share without the lodge around them.
    for short, app in (("stick-overflow", "board"), ("woodipedia", "woodipedia")):
        target = f"{PREFIX}/app/{app}/"
        (OUT / short).mkdir(exist_ok=True)
        (OUT / short / "index.html").write_text(
            f'<!doctype html><meta charset="utf-8"><title>{short}</title>'
            f'<meta http-equiv="refresh" content="0; url={target}"><a href="{target}">{target}</a>\n')
    leaks = [str(p) for p in OUT.rglob("*") if p.is_file() and p.suffix in (".html", ".js", ".json", ".css")
             and re.search(r"/private/tmp|:7790", p.read_text(errors="ignore"))]
    print("files:", sum(1 for p in OUT.rglob("*") if p.is_file()), "| leaks:", leaks or "none")


main()
