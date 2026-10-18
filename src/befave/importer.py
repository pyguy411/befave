"""Import Netscape-format bookmark exports (.html or .zip) into a sqlite3 db."""
import os
import re
import sqlite3
import sys
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
)
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


def import_file(conn, path):
    found = added = 0
    for b in parse_export(path):
        if is_bundled(b) or urlsplit(b["url"]).scheme.lower() not in WEB_SCHEMES:
            continue
        found += 1
        cur = conn.execute(
            "INSERT OR IGNORE INTO bookmarks "
            "(url_norm, url, title, folder, add_date, last_modified, tags, icon) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (normalize_url(b["url"]), b["url"], b["title"], b["folder"],
             b["add_date"], b["last_modified"], b["tags"], b["icon"]),
        )
        added += cur.rowcount
    conn.commit()
    return found, added


def run_import(files, db):
    """Import each file into db; returns a process exit status."""
    os.makedirs(os.path.dirname(os.path.abspath(db)), exist_ok=True)
    conn = sqlite3.connect(db)
    conn.execute(SCHEMA)
    status = 0
    for path in files:
        try:
            found, added = import_file(conn, path)
        except (OSError, ValueError, zipfile.BadZipFile) as e:
            print(f"error: {e}", file=sys.stderr)
            status = 1
            continue
        print(f"{path}: {found} found, {added} new, {found - added} duplicates skipped")
    conn.close()
    return status
