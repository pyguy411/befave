"""Dump the favorites db to a Netscape bookmark HTML file that any browser can import."""
import os
import sqlite3
import sys
from html import escape

from .ingester import SCHEMA, TOOLBAR, baseline_items, record_snapshot, source_id

# Name each browser uses for its toolbar folder on import.
BROWSER_TOOLBAR = {
    "chrome": "Bookmarks Bar",
    "opera": "Bookmarks Bar",
    "firefox": "Bookmarks Toolbar",
    "safari": "Favorites",
}


def build_tree(rows):
    root = {"folders": {}, "links": []}
    for row in rows:
        node = root
        for name in filter(None, (row["folder"] or "").split("/")):
            node = node["folders"].setdefault(name, {"folders": {}, "links": []})
        node["links"].append(row)
    return root


def attr(name, value):
    return f' {name}="{escape(str(value), quote=True)}"' if value not in (None, "") else ""


def render(node, out, depth, toolbar_name=None):
    pad = "    " * depth
    out.append(f"{pad}<DL><p>")
    for name, child in node["folders"].items():
        if toolbar_name and name == TOOLBAR:
            flag = "" if toolbar_name == "Favorites" else ' PERSONAL_TOOLBAR_FOLDER="true"'
            out.append(f"{pad}    <DT><H3{flag}>{escape(toolbar_name)}</H3>")
        else:
            out.append(f"{pad}    <DT><H3>{escape(name)}</H3>")
        render(child, out, depth + 1)
    for r in node["links"]:
        out.append(
            f"{pad}    <DT><A{attr('HREF', r['url'])}{attr('ADD_DATE', r['add_date'])}"
            f"{attr('LAST_MODIFIED', r['last_modified'])}{attr('TAGS', r['tags'])}"
            f"{attr('ICON', r['icon'])}>{escape(r['title'] or r['url'])}</A>"
        )
    out.append(f"{pad}</DL><p>")


def dump(db, path, browser, source):
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM bookmarks ORDER BY id").fetchall()
    out = [
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
        "<TITLE>Bookmarks</TITLE>",
        "<H1>Bookmarks</H1>",
    ]
    root = build_tree(rows)
    if TOOLBAR in root["folders"]:  # toolbar first
        root["folders"] = {TOOLBAR: root["folders"].pop(TOOLBAR), **root["folders"]}
    render(root, out, 0, BROWSER_TOOLBAR[browser])
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    # Browsers add imported bookmarks to what they already have, so the source's
    # new baseline is its previous one plus everything just dumped.
    sid = source_id(conn, source)
    record_snapshot(conn, sid, "dump",
                    (baseline_items(conn, sid) or set()) | {r["url_norm"] for r in rows})
    conn.commit()
    conn.close()
    return len(rows)


def run_dump(output, browser, db, source):
    """Dump db to output for the target browser; returns a process exit status."""
    if not os.path.exists(db):
        print(f"error: database not found: {db}", file=sys.stderr)
        return 1
    print(f"{output}: {dump(db, output, browser, source)} bookmarks dumped")
    return 0
