import os
import sqlite3
import tempfile
import unittest

from befave.dumper import run_dump
from befave.ingester import run_ingest


def write_export(path, urls):
    links = "\n".join(f'<DT><A HREF="{u}">{u}</A>' for u in urls)
    with open(path, "w") as f:
        f.write("<!DOCTYPE NETSCAPE-Bookmark-file-1>\n<DL><p>\n" + links + "\n</DL><p>\n")


def url(n):
    return f"https://example.com/{n}"


class DeletionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "f.db")

    def imp(self, source, urls, yes=False):
        path = os.path.join(self.tmp.name, f"{source}.html")
        write_export(path, urls)
        return run_ingest([path], self.db, source, yes)

    def urls(self):
        conn = sqlite3.connect(self.db)
        try:
            return {r[0] for r in conn.execute("SELECT url FROM bookmarks")}
        finally:
            conn.close()

    def export(self, source):
        out = os.path.join(self.tmp.name, "out.html")
        run_dump(out, "chrome", self.db, source)
        with open(out) as f:
            return f.read()

    def test_delete_propagates(self):
        self.imp("a", [url(1), url(2), url(3)])
        self.imp("b", [url(1), url(2), url(3)])
        self.imp("a", [url(1), url(3)])
        self.assertEqual(self.urls(), {url(1), url(3)})
        self.assertNotIn(url(2), self.export("b"))

    def test_stale_source_does_not_resurrect(self):
        self.imp("a", [url(1), url(2)])
        self.imp("b", [url(1), url(2)])
        self.imp("a", [url(1)])
        self.imp("b", [url(1), url(2)])
        self.assertEqual(self.urls(), {url(1)})

    def test_readd_requires_confirmation(self):
        self.imp("a", [url(1), url(2)])
        self.imp("a", [url(1)])
        self.imp("a", [url(1), url(2)])
        self.assertEqual(self.urls(), {url(1)})
        self.imp("a", [url(1)])
        self.imp("a", [url(1), url(2)], yes=True)
        self.assertEqual(self.urls(), {url(1), url(2)})

    def test_dump_then_delete_in_target(self):
        self.imp("a", [url(1), url(2)])
        self.export("b")
        self.imp("b", [url(1)])
        self.assertEqual(self.urls(), {url(1)})

    def test_first_import_deletes_nothing(self):
        self.imp("a", [url(1)])
        self.imp("b", [url(2)])
        self.assertEqual(self.urls(), {url(1), url(2)})

    def test_partial_export_guard(self):
        urls = [url(i) for i in range(20)]
        self.imp("a", urls)
        self.assertEqual(self.imp("a", urls[:5]), 1)
        self.assertEqual(len(self.urls()), 20)
        self.assertEqual(self.imp("a", urls[:5], yes=True), 0)
        self.assertEqual(len(self.urls()), 5)

    def test_small_deletion_needs_no_confirmation(self):
        urls = [url(i) for i in range(20)]
        self.imp("a", urls)
        self.assertEqual(self.imp("a", urls[:15]), 0)
        self.assertEqual(len(self.urls()), 15)


if __name__ == "__main__":
    unittest.main()
