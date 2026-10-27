"""Compare the favorites each profile holds, without changing any data."""
import os
import sqlite3
import sys

from .ingester import open_db


def _held(conn, name):
    """URLs the profile holds (not deleted), or None if it was never ingested."""
    if not conn.execute(
            "SELECT 1 FROM ingests i JOIN profiles p ON p.id = i.profile_id WHERE p.name = ?",
            (name,)).fetchone():
        return None
    return {r[0] for r in conn.execute(
        "SELECT pb.url_norm FROM profile_bookmarks pb "
        "JOIN profiles p ON p.id = pb.profile_id "
        "JOIN bookmarks b ON b.url_norm = pb.url_norm "
        "WHERE p.name = ? AND b.deleted = 0", (name,))}


def compare(db, a, b=None):
    """Return (both, only_a, only_b, titles) for profile `a` and profile `b`.

    Without `b`, `a` is compared with every bookmark in the database.
    """
    conn = open_db(db)
    try:
        left = _held(conn, a)
        if left is None:
            raise ValueError(f"profile '{a}' has no ingest in this database")
        if b is None:
            right = {r[0] for r in conn.execute("SELECT url_norm FROM bookmarks WHERE deleted = 0")}
        else:
            right = _held(conn, b)
            if right is None:
                raise ValueError(f"profile '{b}' has no ingest in this database")
        titles = {r[0]: (r[1], r[2]) for r in conn.execute(
            "SELECT url_norm, url, title FROM bookmarks WHERE deleted = 0")}
    finally:
        conn.close()
    return left & right, left - right, right - left, titles


def run_compare(db, a, b=None, show=None):
    """Print the comparison; `show` is one of common/only_a/only_b for bare URLs."""
    if not os.path.exists(db):
        print(f"error: database not found: {db}", file=sys.stderr)
        return 1
    try:
        both, only_a, only_b, titles = compare(db, a, b)
    except (ValueError, sqlite3.Error) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    sets = {"common": both, "only_a": only_a, "only_b": only_b}

    def url(n):
        return titles.get(n, (n, ""))[0]

    if show:
        for n in sorted(sets[show]):
            print(url(n))
        return 0
    right = f"profile '{b}'" if b else "the database"
    for label, items in ((f"In both '{a}' and {right}", both),
                         (f"Only in '{a}'", only_a),
                         (f"Only in {right}", only_b)):
        print(f"{label}: {len(items)}")
        for n in sorted(items):
            u, title = titles.get(n, (n, ""))
            print(f"  {u}" + (f"  ({title})" if title else ""))
    return 0
