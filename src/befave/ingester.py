"""Ingest Netscape-format bookmark exports (.html or .zip) into a sqlite3 db."""
import os
import re
import shutil
import sqlite3
import sys
import time
import uuid
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
    icon TEXT,
    deleted INTEGER NOT NULL DEFAULT 0,
    deleted_at INTEGER
);
CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS ingests (
    id TEXT PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    taken_at INTEGER NOT NULL,
    tracked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ingest_files (
    ingest_id TEXT NOT NULL REFERENCES ingests(id),
    path TEXT NOT NULL,
    found INTEGER NOT NULL,
    file_mtime INTEGER,
    ingested_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS profile_bookmarks (
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    url_norm TEXT NOT NULL,
    ingest_id TEXT NOT NULL REFERENCES ingests(id),
    title TEXT,
    folder TEXT,
    add_date INTEGER,
    PRIMARY KEY (profile_id, url_norm)
);
CREATE TABLE IF NOT EXISTS safe_urls (
    profile_id INTEGER NOT NULL REFERENCES profiles(id),
    url_norm TEXT NOT NULL,
    ingest_id TEXT NOT NULL REFERENCES ingests(id),
    marked_at INTEGER NOT NULL,
    PRIMARY KEY (profile_id, url_norm)
);
"""


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


def clean_folder(folder):
    """Drop the "Imported" wrapper folder that a browser adds when it imports a file.

    Only the top-level one (directly under the toolbar, or at the root) is dropped.
    """
    parts = [p for p in (folder or "").split("/") if p]
    i = 1 if parts[:1] == [TOOLBAR] else 0
    if len(parts) > i and parts[i].lower() == "imported":
        del parts[i]
    return "/".join(parts)


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
            "folder": clean_folder("/".join(f for f in self.folders if f)),
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


def open_db(db):
    """Open the database, creating or upgrading the schema as needed."""
    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if "snapshots" in tables:
        migrate(conn, db)
    conn.executescript(SCHEMA)
    return conn


def migrate(conn, db):
    """Upgrade a database that tracked deletions with snapshots and tombstones.

    Favorites and profiles are kept. Each profile's latest ingest becomes its set of
    held favorites, tombstones become favorites marked deleted, and dump snapshots
    are dropped. A copy of the original file is saved next to it as `.bak`.
    """
    conn.commit()
    backup = db + ".bak"
    if not os.path.exists(backup):
        shutil.copyfile(db, backup)
    columns = {r[1] for r in conn.execute("PRAGMA table_info(bookmarks)")}
    if "deleted" not in columns:
        conn.execute("ALTER TABLE bookmarks ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE bookmarks ADD COLUMN deleted_at INTEGER")
    conn.executescript(SCHEMA)
    for pid, in conn.execute("SELECT id FROM profiles").fetchall():
        snap = conn.execute(
            "SELECT id, taken_at FROM snapshots WHERE profile_id = ? AND kind = 'ingest' "
            "ORDER BY id DESC LIMIT 1", (pid,)).fetchone()
        if not snap:
            continue
        run = str(uuid.uuid4())
        conn.execute("INSERT INTO ingests (id, profile_id, taken_at, tracked) VALUES (?,?,?,0)",
                     (run, pid, snap[1]))
        conn.execute(
            "INSERT OR IGNORE INTO profile_bookmarks "
            "SELECT ?, pi.url_norm, ?, b.title, b.folder, b.add_date "
            "FROM profile_items pi JOIN bookmarks b ON b.url_norm = pi.url_norm "
            "WHERE pi.snapshot_id = ?", (pid, run, snap[0]))
    conn.execute(
        "INSERT OR IGNORE INTO bookmarks (url_norm, url, deleted, deleted_at) "
        "SELECT url_norm, url_norm, 1, deleted_at FROM tombstones")
    for table in ("profile_items", "snapshots", "tombstones"):
        conn.execute(f"DROP TABLE {table}")
    conn.commit()


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


def has_history(db, name):
    """True if the profile has been ingested before."""
    if not os.path.exists(db):
        return False
    conn = sqlite3.connect(db)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
        if "ingests" in tables:
            return conn.execute(
                "SELECT 1 FROM ingests i JOIN profiles p ON p.id = i.profile_id "
                "WHERE p.name = ?", (name,)).fetchone() is not None
        if "snapshots" in tables:
            return conn.execute(
                "SELECT 1 FROM snapshots s JOIN profiles p ON p.id = s.profile_id "
                "WHERE p.name = ? AND s.kind = 'ingest'", (name,)).fetchone() is not None
        return False
    finally:
        conn.close()


def _candidates(conn, sid, items, previous):
    """Favorites this profile held before that are not in `items` and are not marked safe."""
    safe = {r[0] for r in conn.execute("SELECT url_norm FROM safe_urls WHERE profile_id = ?", (sid,))}
    files = {}
    out = []
    for url_norm, row in previous.items():
        if url_norm in items or url_norm in safe or row["deleted"]:
            continue
        run = row["ingest_id"]
        if run not in files:
            files[run] = [r[0] for r in conn.execute(
                "SELECT path FROM ingest_files WHERE ingest_id = ? ORDER BY rowid", (run,))]
        out.append({
            "url_norm": url_norm,
            "url": row["url"],
            "title": row["title"] or row["bookmark_title"] or "",
            "folder": row["folder"] or "",
            "add_date": row["add_date"],
            "files": files[run],
            "taken_at": row["taken_at"],
        })
    return sorted(out, key=lambda c: (c["folder"].lower(), c["title"].lower(), c["url"]))


def import_files(conn, paths, profile, track=False, assume_yes=False, confirm=None, decide=None):
    """Ingest browser export file(s) as one run for `profile`.

    With several files the earliest one wins when they hold the same URL. When `track`
    is true, favorites the profile held before that are missing now are offered for
    deletion: `decide(candidates)` returns (delete, keep) as lists of url_norm; with
    `assume_yes` they are all deleted; otherwise they are left alone.

    Returns a dict of counts: found, added, missing, deleted, kept, first.
    """
    confirm = confirm or (lambda msg: False)
    ok = lambda msg: assume_yes or confirm(msg)
    rows = {}
    file_info = []
    for path in paths:
        before = len(rows)
        parsed = 0
        for b in parse_export(path):
            if is_bundled(b) or urlsplit(b["url"]).scheme.lower() not in WEB_SCHEMES:
                continue
            parsed += 1
            rows.setdefault(normalize_url(b["url"]), b)
        file_info.append((os.path.abspath(path), parsed, int(os.path.getmtime(path))))
    items = set(rows)

    sid = profile_id(conn, profile)
    conn.row_factory = sqlite3.Row
    previous = {r["url_norm"]: r for r in conn.execute(
        "SELECT pb.url_norm, pb.ingest_id, pb.title, pb.folder, pb.add_date, "
        "b.url, b.title AS bookmark_title, b.deleted, i.taken_at "
        "FROM profile_bookmarks pb JOIN bookmarks b ON b.url_norm = pb.url_norm "
        "JOIN ingests i ON i.id = pb.ingest_id WHERE pb.profile_id = ?", (sid,))}
    deleted_in_db = {r[0] for r in conn.execute("SELECT url_norm FROM bookmarks WHERE deleted = 1")}
    conn.row_factory = None

    now = int(time.time())
    run = str(uuid.uuid4())
    conn.execute("INSERT INTO ingests (id, profile_id, taken_at, tracked) VALUES (?,?,?,?)",
                 (run, sid, now, int(track)))
    conn.executemany("INSERT INTO ingest_files VALUES (?,?,?,?,?)",
                     [(run, path, n, mtime, now) for path, n, mtime in file_info])

    # A deleted favorite this profile still holds is a stale copy; one it did not
    # hold was added again, so ask before bringing it back.
    stale = {u for u in items & deleted_in_db if u in previous}
    revived = (items & deleted_in_db) - stale
    if revived and not ok(f"{len(revived)} bookmark(s) in this file were deleted earlier. "
                          "Restore them?"):
        revived = set()
    blocked = ((items & deleted_in_db) - revived) | stale

    missing = deleted = kept = 0
    if track and previous:
        candidates = _candidates(conn, sid, items, previous)
        missing = len(candidates)
        if candidates and assume_yes:
            to_delete, to_keep = [c["url_norm"] for c in candidates], []
        elif candidates and decide:
            to_delete, to_keep = decide(candidates)
        else:
            to_delete, to_keep = [], []
        for url in to_delete:
            conn.execute("UPDATE bookmarks SET deleted = 1, deleted_at = ? WHERE url_norm = ?",
                         (now, url))
            conn.execute("DELETE FROM profile_bookmarks WHERE profile_id = ? AND url_norm = ?",
                         (sid, url))
        for url in to_keep:
            conn.execute("INSERT OR REPLACE INTO safe_urls VALUES (?,?,?,?)", (sid, url, run, now))
        deleted, kept = len(to_delete), len(to_keep)

    for url in revived:
        conn.execute("UPDATE bookmarks SET deleted = 0, deleted_at = NULL WHERE url_norm = ?", (url,))
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
        conn.execute("INSERT OR REPLACE INTO profile_bookmarks VALUES (?,?,?,?,?,?)",
                     (sid, url, run, b["title"], b["folder"], b["add_date"]))
    # Stale copies of deleted favorites stop being held once a file no longer has them.
    for url in deleted_in_db - items:
        conn.execute("DELETE FROM profile_bookmarks WHERE profile_id = ? AND url_norm = ?",
                     (sid, url))
    conn.commit()
    return {"found": len(rows), "added": added, "missing": missing, "deleted": deleted,
            "kept": kept, "first": not previous}


def run_ingest(files, db, profile=None, track=False, assume_yes=False, confirm=None,
               decide=None):
    """Ingest each file into db; returns an exit status.

    `profile` may be a name or a callable taking the file path. `track` may be a bool or
    a callable taking the profile name. Files sharing a profile are ingested as one run.
    """
    os.makedirs(os.path.dirname(os.path.abspath(db)), exist_ok=True)
    conn = open_db(db)
    status = 0
    groups = {}
    for path in files:
        name = profile(path) if callable(profile) else profile
        groups.setdefault(name, []).append(path)
    for name, paths in groups.items():
        try:
            tracking = track(name) if callable(track) else track
            r = import_files(conn, paths, name, tracking, assume_yes, confirm, decide)
        except (OSError, ValueError, zipfile.BadZipFile) as e:
            conn.rollback()
            print(f"error: {e}", file=sys.stderr)
            status = 1
            continue
        line = (f"{', '.join(paths)} (profile {name}): {r['found']} found, {r['added']} new, "
                f"{r['found'] - r['added']} duplicates skipped")
        if tracking and r["first"]:
            line += f"; no earlier ingest of '{name}', nothing to compare"
        elif tracking:
            line += f"; {r['missing']} missing, {r['deleted']} deleted, {r['kept']} kept"
            if r["missing"] and not (r["deleted"] or r["kept"]):
                line += " (left alone; pass --yes to delete them)"
        print(line)
    conn.close()
    return status
