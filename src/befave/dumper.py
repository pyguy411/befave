"""Dump the favorites db to a Netscape bookmark HTML file that any browser can import."""

import os
import sqlite3
import sys
from html import escape

from .ingester import TOOLBAR, clean_folder, list_profiles, open_db

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
        for name in filter(None, clean_folder(row["folder"]).split("/")):
            node = node["folders"].setdefault(name, {"folders": {}, "links": []})
        node["links"].append(row)
    return root


def attr(name, value):
    return (
        f' {name}="{escape(str(value), quote=True)}"' if value not in (None, "") else ""
    )


def render(node, out, depth, toolbar_name=None):
    pad = "    " * depth
    out.append(f"{pad}<DL><p>")
    for name, child in node["folders"].items():
        if toolbar_name and name == TOOLBAR:
            flag = (
                "" if toolbar_name == "Favorites" else ' PERSONAL_TOOLBAR_FOLDER="true"'
            )
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


def dump(db, path, browser, profiles=None):
    """Write the favorites to path; `profiles` limits it to what those profiles hold."""
    conn = open_db(db)
    conn.row_factory = sqlite3.Row
    if profiles:
        marks = ",".join("?" * len(profiles))
        rows = conn.execute(
            "SELECT * FROM bookmarks WHERE deleted = 0 AND url_norm IN ("
            "SELECT pb.url_norm FROM profile_bookmarks pb JOIN profiles p "
            f"ON p.id = pb.profile_id WHERE p.name IN ({marks})) ORDER BY id",
            list(profiles),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM bookmarks WHERE deleted = 0 ORDER BY id"
        ).fetchall()
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
    conn.close()
    return len(rows)


def run_dump(output, browser, db, profiles=None):
    """Dump db to output for the target browser; returns a process exit status."""
    if not os.path.exists(db):
        print(f"error: database not found: {db}", file=sys.stderr)
        return 1
    known = list_profiles(db)
    unknown = [p for p in profiles or [] if p not in known]
    if unknown:
        print(
            f"error: no such profile: {', '.join(unknown)}"
            f" (known: {', '.join(known) or 'none'})",
            file=sys.stderr,
        )
        return 1
    print(f"{output}: {dump(db, output, browser, profiles)} bookmarks dumped")
    return 0
