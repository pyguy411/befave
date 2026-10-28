"""Show what is in the favorites database, without changing any favorites."""

import os
import sqlite3
import sys
import time

from .ingester import open_db

VIEWS = ("show_deleted", "profiles", "history", "safe", "search", "stats")


def _date(ts):
    return time.strftime("%Y-%m-%d", time.localtime(ts)) if ts else ""


def _like(text):
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _profile_filter(column, profile, args):
    if profile:
        args.append(profile)
        return f" AND {column} = ?"
    return ""


def run_view(conn, view, text=None, profile=None, folder=None):
    """Return (headers, rows, url_column) for a view; url_column is None if no URLs."""
    if view == "show_deleted":
        rows = conn.execute(
            "SELECT title, url, folder, deleted_at FROM bookmarks WHERE deleted = 1 "
            "ORDER BY deleted_at DESC, id"
        ).fetchall()
        return (
            ["Title", "URL", "Folder", "Deleted"],
            [(t or "", u, f or "", _date(d)) for t, u, f, d in rows],
            1,
        )
    if view == "profiles":
        rows = conn.execute(
            "SELECT p.name, (SELECT count(*) FROM profile_bookmarks pb JOIN bookmarks b "
            "ON b.url_norm = pb.url_norm WHERE pb.profile_id = p.id AND b.deleted = 0), "
            "(SELECT max(taken_at) FROM ingests WHERE profile_id = p.id) "
            "FROM profiles p ORDER BY p.name"
        ).fetchall()
        return (
            ["Profile", "Favorites", "Last ingest"],
            [(n, c, _date(t)) for n, c, t in rows],
            None,
        )
    if view == "history":
        args = []
        where = _profile_filter("p.name", profile, args)
        rows = conn.execute(
            "SELECT i.taken_at, p.name, i.tracked, "
            "(SELECT group_concat(path, ', ') FROM ingest_files WHERE ingest_id = i.id) "
            "FROM ingests i JOIN profiles p ON p.id = i.profile_id WHERE 1 = 1"
            f"{where} ORDER BY i.taken_at DESC",
            args,
        ).fetchall()
        return (
            ["Date", "Profile", "Tracked", "Files"],
            [(_date(t), n, "yes" if k else "no", f or "") for t, n, k, f in rows],
            None,
        )
    if view == "safe":
        args = []
        where = _profile_filter("p.name", profile, args)
        rows = conn.execute(
            "SELECT b.title, b.url, p.name, s.marked_at FROM safe_urls s "
            "JOIN profiles p ON p.id = s.profile_id "
            "JOIN bookmarks b ON b.url_norm = s.url_norm WHERE 1 = 1"
            f"{where} ORDER BY s.marked_at DESC",
            args,
        ).fetchall()
        return (
            ["Title", "URL", "Profile", "Marked"],
            [(t or "", u, n, _date(m)) for t, u, n, m in rows],
            1,
        )
    if view == "search":
        args = [_like(text or ""), _like(text or "")]
        sql = (
            "SELECT b.title, b.url, b.folder FROM bookmarks b WHERE b.deleted = 0 "
            "AND (b.title LIKE ? ESCAPE '\\' OR b.url LIKE ? ESCAPE '\\')"
        )
        if folder:
            sql += " AND b.folder LIKE ? ESCAPE '\\'"
            args.append(_like(folder))
        if profile:
            sql += (
                " AND b.url_norm IN (SELECT pb.url_norm FROM profile_bookmarks pb "
                "JOIN profiles p ON p.id = pb.profile_id WHERE p.name = ?)"
            )
            args.append(profile)
        rows = conn.execute(sql + " ORDER BY b.folder, b.title", args).fetchall()
        return (
            ["Title", "URL", "Folder"],
            [(t or "", u, f or "") for t, u, f in rows],
            1,
        )
    one = lambda sql: conn.execute(sql).fetchone()[0]
    stats = [
        ("Favorites", one("SELECT count(*) FROM bookmarks WHERE deleted = 0")),
        ("Deleted", one("SELECT count(*) FROM bookmarks WHERE deleted = 1")),
        ("Profiles", one("SELECT count(*) FROM profiles")),
        ("Ingests", one("SELECT count(*) FROM ingests")),
        (
            "Held by no profile",
            one(
                "SELECT count(*) FROM bookmarks WHERE deleted = 0 AND url_norm NOT IN "
                "(SELECT url_norm FROM profile_bookmarks)"
            ),
        ),
    ]
    return ["Item", "Count"], stats, None


def format_table(headers, rows):
    cells = [[str(c) for c in r] for r in rows]
    widths = [max([len(h)] + [len(r[i]) for r in cells]) for i, h in enumerate(headers)]
    line = lambda r: "  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip()
    return "\n".join(
        [line(headers), line(["-" * w for w in widths])] + [line(r) for r in cells]
    )


def run_query(db, view, text=None, profile=None, folder=None, urls=False):
    """Print one view; returns a process exit status."""
    if not os.path.exists(db):
        print(f"error: database not found: {db}", file=sys.stderr)
        return 1
    if view == "show_deleted" and profile:
        print(
            "error: --profile cannot be used with --show-deleted; the database does "
            "not record which profile deleted a favorite",
            file=sys.stderr,
        )
        return 1
    if view == "search" and not text:
        print("error: --search needs some text", file=sys.stderr)
        return 1
    conn = open_db(db)
    try:
        headers, rows, url_col = run_view(conn, view, text, profile, folder)
    except sqlite3.Error as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    if urls:
        if url_col is None:
            print(
                "error: --urls only works with --show-deleted, --safe and --search",
                file=sys.stderr,
            )
            return 1
        for r in rows:
            print(r[url_col])
        return 0
    if not rows:
        print("Nothing to show.")
        return 0
    print(format_table(headers, rows))
    return 0
