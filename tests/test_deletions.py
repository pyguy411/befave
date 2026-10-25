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

    def imp(self, profile, urls, yes=False):
        path = os.path.join(self.tmp.name, f"{profile}.html")
        write_export(path, urls)
        return run_ingest([path], self.db, profile, yes)

    def urls(self):
        conn = sqlite3.connect(self.db)
        try:
            return {r[0] for r in conn.execute("SELECT url FROM bookmarks")}
        finally:
            conn.close()

    def export(self, profile):
        out = os.path.join(self.tmp.name, "out.html")
        run_dump(out, "chrome", self.db, profile)
        with open(out) as f:
            return f.read()

    def test_delete_propagates(self):
        self.imp("a", [url(1), url(2), url(3)])
        self.imp("b", [url(1), url(2), url(3)])
        self.imp("a", [url(1), url(3)])
        self.assertEqual(self.urls(), {url(1), url(3)})
        self.assertNotIn(url(2), self.export("b"))

    def test_stale_profile_does_not_resurrect(self):
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

    def test_files_sharing_a_profile_are_one_snapshot(self):
        f1 = os.path.join(self.tmp.name, "1.html")
        f2 = os.path.join(self.tmp.name, "2.html")
        write_export(f1, [url(1), url(2)])
        write_export(f2, [url(2), url(3)])
        self.assertEqual(run_ingest([f1, f2], self.db, "all"), 0)
        self.assertEqual(self.urls(), {url(1), url(2), url(3)})
        write_export(f2, [url(3)])
        self.assertEqual(run_ingest([f1, f2], self.db, "all"), 0)
        self.assertEqual(self.urls(), {url(1), url(2), url(3)})
        write_export(f1, [url(1)])
        self.assertEqual(run_ingest([f1, f2], self.db, "all"), 0)
        self.assertEqual(self.urls(), {url(1), url(3)})

    def test_browser_imported_folder_is_not_kept(self):
        path = os.path.join(self.tmp.name, "o.html")
        with open(path, "w") as f:
            f.write("<!DOCTYPE NETSCAPE-Bookmark-file-1>\n<DL><p><DT><H3 PERSONAL_TOOLBAR_FOLDER=\"true\">Bookmarks Bar</H3><DL><p>"
                    "<DT><H3>Imported</H3><DL><p><DT><H3>work</H3><DL><p>"
                    "<DT><A HREF=\"https://a.example/\">a</A></DL><p></DL><p>"
                    "<DT><H3>mine</H3><DL><p><DT><H3>Imported</H3><DL><p>"
                    "<DT><A HREF=\"https://b.example/\">b</A></DL><p></DL><p></DL><p></DL><p>")
        run_ingest([path], self.db, "o")
        conn = sqlite3.connect(self.db)
        folders = dict(conn.execute("SELECT url, folder FROM bookmarks"))
        conn.close()
        self.assertEqual(folders["https://a.example/"], "Bookmarks Bar/work")
        self.assertEqual(folders["https://b.example/"], "Bookmarks Bar/mine/Imported")
        self.assertEqual(self.export("o").count("<H3>Imported</H3>"), 1)

if __name__ == "__main__":
    unittest.main()
