#!/usr/bin/env python3
"""Export the favorites db to a Netscape bookmark HTML file importable by any browser."""
import argparse
import os
import sqlite3
import sys
from html import escape

from import_bookmarks import DEFAULT_DB


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


def render(node, out, depth):
    pad = "    " * depth
    out.append(f"{pad}<DL><p>")
    for name, child in node["folders"].items():
        out.append(f"{pad}    <DT><H3>{escape(name)}</H3>")
        render(child, out, depth + 1)
    for r in node["links"]:
        out.append(
            f"{pad}    <DT><A{attr('HREF', r['url'])}{attr('ADD_DATE', r['add_date'])}"
            f"{attr('LAST_MODIFIED', r['last_modified'])}{attr('TAGS', r['tags'])}"
            f"{attr('ICON', r['icon'])}>{escape(r['title'] or r['url'])}</A>"
        )
    out.append(f"{pad}</DL><p>")


def export(db, path):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM bookmarks ORDER BY id").fetchall()
    out = [
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
        "<TITLE>Bookmarks</TITLE>",
        "<H1>Bookmarks</H1>",
    ]
    render(build_tree(rows), out, 0)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    return len(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("output", help="output .html file")
    ap.add_argument("--db", default=DEFAULT_DB, help="default: %(default)s")
    args = ap.parse_args()
    if not os.path.exists(args.db):
        print(f"error: database not found: {args.db}", file=sys.stderr)
        return 1
    print(f"{args.output}: {export(args.db, args.output)} bookmarks exported")
    return 0


if __name__ == "__main__":
    sys.exit(main())
