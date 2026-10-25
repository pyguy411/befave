"""Compare what the database knows about a profile, read-only."""
import os
import sqlite3
import sys


def _ingested(conn, name):
    """URLs from the profile's latest ingest, or None if it was never ingested."""
    row = conn.execute(
        "SELECT s.id FROM snapshots s JOIN profiles p ON p.id = s.profile_id "
        "WHERE p.name = ? AND s.kind = 'ingest' ORDER BY s.id DESC LIMIT 1", (name,)
    ).fetchone()
    if not row:
        return None
    return {r[0] for r in conn.execute(
        "SELECT url_norm FROM profile_items WHERE snapshot_id = ?", (row[0],))}


def compare(db, a, b=None):
    """Return (both, only_a, only_b, titles) for profile `a` and profile `b`.

    Without `b`, `a` is compared with every bookmark in the database.
    """
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        left = _ingested(conn, a)
        if left is None:
            raise ValueError(f"profile '{a}' has no ingest in this database")
        if b is None:
            right = {r[0] for r in conn.execute("SELECT url_norm FROM bookmarks")}
        else:
            right = _ingested(conn, b)
            if right is None:
                raise ValueError(f"profile '{b}' has no ingest in this database")
        titles = {r[0]: (r[1], r[2]) for r in conn.execute(
            "SELECT url_norm, url, title FROM bookmarks")}
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
