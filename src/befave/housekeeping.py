"""Check saved URLs and record their HTTP response codes."""

import os
import sys
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import urlopen

from .ingester import open_db

TIMEOUT = 15


def run_url_validation(db):
    """Check URLs without a saved response, returning a process exit status."""
    if not os.path.exists(db):
        print(f"error: database not found: {db}", file=sys.stderr)
        return 1

    conn = open_db(db)
    checked = skipped = failed = 0
    try:
        rows = conn.execute(
            "SELECT id, url FROM bookmarks WHERE http_status IS NULL ORDER BY id"
        ).fetchall()
        for bookmark_id, url in rows:
            try:
                if urlsplit(url).scheme.lower() not in ("http", "https"):
                    print(f"  skipped (not HTTP/HTTPS): {url}", file=sys.stderr)
                    skipped += 1
                    continue
                try:
                    with urlopen(url, timeout=TIMEOUT) as response:
                        code = response.status
                except HTTPError as response:
                    code = response.code
                    response.close()
            except (HTTPException, URLError, OSError, ValueError) as e:
                print(f"  error checking {url}: {e}", file=sys.stderr)
                failed += 1
                continue
            conn.execute(
                "UPDATE bookmarks SET http_status = ? WHERE id = ?",
                (code, bookmark_id),
            )
            conn.commit()
            checked += 1
            print(f"  {code}  {url}")
    finally:
        conn.close()
    print(f"Checked {checked} URL(s); {skipped} skipped, {failed} failed.")
    return 1 if failed else 0
