"""Ingest Netscape-format bookmark exports (.html or .zip) into a sqlite3 db."""
import os
import re
import sqlite3
import sys
import time
import zipfile
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

DEFAULT_DB = os.path.join(os.path.expanduser("~"), ".befave", "favorites.db")
WEB_SCHEMES = ("http", "https", "ftp")

# Folders browsers ship by default; the whole subtree is skipped.
BUNDLED_FOLDERS = {"mozilla firefox"}
# Links Safari pre-populates in its top-level Favorites folder.
SAFARI_DEFAULTS = {
    "https://www.apple.com/", "https://www.icloud.com/", "https://www.yahoo.com/",
    "https://www.bing.com/", "https://www.google.com/?client=safari&channel=mac_bm",
    "https://www.wikipedia.org/", "https://www.facebook.com/", "https://twitter.com/",
    "https://www.linkedin.com/", "https://www.weather.com/", "https://www.yelp.com/",
    "https://www.tripadvisor.com/",
}

BUNDLED_URL = re.compile(r"^https://www\.mozilla\.org/(?:[\w-]+/)?firefox/(?:customize|help)/?$")

# All browsers' toolbar folders are stored under this one name.
TOOLBAR = "Bookmarks Bar"

SCHEMA = """
CREATE TABLE IF NOT EXISTS bookmarks (
    id INTEGER PRIMARY KEY,
    url_norm TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    title TEXT,
    folder TEXT,
    add_date INTEGER,
    last_modified INTEGER,
    tags TEXT,
    icon TEXT
);
CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    taken_at INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('ingest', 'dump'))
);
CREATE TABLE IF NOT EXISTS profile_items (
    snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
    url_norm TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, url_norm)
);
CREATE TABLE IF NOT EXISTS tombstones (
    url_norm TEXT PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    deleted_at INTEGER NOT NULL
);
"""

# Guard against partial exports being mistaken for mass deletion.
MASS_DELETE_FRACTION = 0.3
MASS_DELETE_MIN_ITEMS = 10


def normalize_url(url):
    """Lowercase scheme/host, drop fragment, drop utm_* query parameters."""
    url = url.strip()
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if not parts.scheme or not parts.netloc:
        return urlunsplit((parts.scheme.lower(), parts.netloc, parts.path, parts.query, ""))
    host = parts.netloc
    if "@" in host:
        userinfo, _, hostport = host.rpartition("@")
        host = userinfo + "@" + hostport.lower()
    else:
        host = host.lower()
    query = parts.query
    if "utm_" in query.lower():
        pairs = parse_qsl(query, keep_blank_values=True)
        query = urlencode([(k, v) for k, v in pairs if not k.lower().startswith("utm_")])
    return urlunsplit((parts.scheme.lower(), host, parts.path, query, ""))


def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class BookmarkParser(HTMLParser):
    """Walks <DL>/<H3>/<A> nesting; yields dicts in file order."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.bookmarks = []
        self.folders = []
        self.pending_folder = None
        self.capture = None  # "h3" or "a"
        self.buf = []
        self.attrs = {}
        self.folder_attrs = {}

    def handle_starttag(self, tag, attrs):
        if tag == "h3":
            self.capture, self.buf = "h3", []
            self.folder_attrs = {k.lower(): v for k, v in attrs}
        elif tag == "a":
            self.capture, self.buf = "a", []
            self.attrs = {k.lower(): v for k, v in attrs}
        elif tag == "dl":
            self.folders.append(self.pending_folder)
            self.pending_folder = None

    def handle_endtag(self, tag):
        if tag == "h3" and self.capture == "h3":
            name = "".join(self.buf).strip()
            top_level = not any(self.folders)
            if top_level and (
                    self.folder_attrs.get("personal_toolbar_folder", "").lower() == "true"
                    or name == "Favorites"  # Safari's toolbar folder
            ):
                name = TOOLBAR
            self.pending_folder = name
            self.capture = None
        elif tag == "a" and self.capture == "a":
            self._finish_link()
        elif tag == "dl" and self.folders:
            self.folders.pop()

    def handle_data(self, data):
        if self.capture:
            self.buf.append(data)

    def _finish_link(self):
        a = self.attrs
        self.capture = None
        url = a.get("href")
        if not url or not url.strip():
            return
        self.bookmarks.append({
            "url": url.strip(),
            "title": "".join(self.buf).strip(),
            "folder": "/".join(f for f in self.folders if f),
            "add_date": to_int(a.get("add_date")),
            "last_modified": to_int(a.get("last_modified")),
            "tags": a.get("tags"),
            "icon": a.get("icon"),
        })


def is_bundled(b):
    if any(p.lower() in BUNDLED_FOLDERS for p in b["folder"].split("/")):
        return True
    if BUNDLED_URL.match(b["url"]):
        return True
    return b["folder"] == TOOLBAR and b["url"] in SAFARI_DEFAULTS


def read_export(path):
    """Return the HTML text of an export file, unzipping if needed."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist()
                     if n.lower().endswith((".html", ".htm")) and not n.startswith("__MACOSX")]
            if not names:
                raise ValueError(f"no html file found in {path}")
            return z.read(names[0]).decode("utf-8", errors="replace")
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def parse_export(path):
    text = read_export(path)
    if "NETSCAPE-BOOKMARK-FILE-1" not in text[:500].upper():
        raise ValueError(f"{path} is not a Netscape bookmark export")
    parser = BookmarkParser()
    parser.feed(text)
    parser.close()
    return parser.bookmarks


def profile_id(conn, name):
    conn.execute("INSERT OR IGNORE INTO profiles (name) VALUES (?)", (name,))
    return conn.execute("SELECT id FROM profiles WHERE name = ?", (name,)).fetchone()[0]


def baseline_items(conn, sid):
    """URLs in the profile's latest snapshot (None if it has none)."""
    row = conn.execute(
        "SELECT id FROM snapshots WHERE profile_id = ? ORDER BY id DESC LIMIT 1", (sid,)
    ).fetchone()
    if not row:
        return None
    return {r[0] for r in conn.execute(
        "SELECT url_norm FROM profile_items WHERE snapshot_id = ?", (row[0],))}


def record_snapshot(conn, sid, kind, items):
    cur = conn.execute(
        "INSERT INTO snapshots (profile_id, taken_at, kind) VALUES (?,?,?)",
        (sid, int(time.time()), kind))
    conn.executemany("INSERT INTO profile_items VALUES (?,?)",
                     [(cur.lastrowid, u) for u in items])


def list_profiles(db):
    if not os.path.exists(db):
        return []
    conn = sqlite3.connect(db)
    try:
        return [r[0] for r in conn.execute("SELECT name FROM profiles ORDER BY name")]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def import_files(conn, paths, profile, assume_yes=False, confirm=None):
    """Ingest browser export file(s) as one combined snapshot of `profile`.

    With several files the earliest one wins when they hold the same URL.

    Returns (found, added, deleted). Raises ValueError if a confirmation is declined.
    """
    confirm = confirm or (lambda msg: False)
    ok = lambda msg: assume_yes or confirm(msg)
    rows = {}
    for path in paths:
        for b in parse_export(path):
            if is_bundled(b) or urlsplit(b["url"]).scheme.lower() not in WEB_SCHEMES:
                continue
            rows.setdefault(normalize_url(b["url"]), b)
    items = set(rows)

    sid = profile_id(conn, profile)
    baseline = baseline_items(conn, sid) or set()
    vanished = baseline - items
    if (len(baseline) > MASS_DELETE_MIN_ITEMS
            and len(vanished) / len(baseline) > MASS_DELETE_FRACTION
            and not ok(f"{len(vanished)} of {len(baseline)} bookmarks from '{profile}' are "
                       "missing from this file and would be deleted everywhere. "
                       "Is this a partial export? Delete them anyway?")):
        raise ValueError(f"{', '.join(paths)}: ingest cancelled (too many deletions)")

    tombstoned = {r[0] for r in conn.execute("SELECT url_norm FROM tombstones")}
    # A tombstoned URL the profile already had is just a stale copy; one it did not
    # have before was re-added (or comes from a profile never ingested before).
    revived = (items & tombstoned) - baseline
    if revived and not ok(f"{len(revived)} bookmark(s) in this file were deleted earlier. "
                          "Restore them?"):
        revived = set()
    blocked = (items & tombstoned) - revived

    now = int(time.time())
    for url in vanished:
        conn.execute("INSERT OR REPLACE INTO tombstones VALUES (?,?,?)", (url, sid, now))
        conn.execute("DELETE FROM bookmarks WHERE url_norm = ?", (url,))
    for url in revived:
        conn.execute("DELETE FROM tombstones WHERE url_norm = ?", (url,))
    added = 0
    for url in items - blocked:
        b = rows[url]
        cur = conn.execute(
            "INSERT OR IGNORE INTO bookmarks "
            "(url_norm, url, title, folder, add_date, last_modified, tags, icon) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (url, b["url"], b["title"], b["folder"],
             b["add_date"], b["last_modified"], b["tags"], b["icon"]),
        )
        added += cur.rowcount
    record_snapshot(conn, sid, "ingest", items)
    conn.commit()
    return len(rows), added, len(vanished)


def run_ingest(files, db, profile=None, assume_yes=False, confirm=None):
    """Ingest each file into db as a snapshot of `profile`; returns an exit status.

    `profile` may be a name or a callable taking the file path.
    """
    os.makedirs(os.path.dirname(os.path.abspath(db)), exist_ok=True)
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA)
    status = 0
    # Files that share a profile are one snapshot of it, so group them (in order).
    groups = {}
    for path in files:
        name = profile(path) if callable(profile) else profile
        groups.setdefault(name, []).append(path)
    for name, paths in groups.items():
        try:
            found, added, deleted = import_files(conn, paths, name, assume_yes, confirm)
        except (OSError, ValueError, zipfile.BadZipFile) as e:
            conn.rollback()
            print(f"error: {e}", file=sys.stderr)
            status = 1
            continue
        print(f"{', '.join(paths)} (profile {name}): {found} found, {added} new, "
              f"{found - added} duplicates skipped, {deleted} deleted")
    conn.close()
    return status
