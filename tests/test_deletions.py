import os
import shutil
import sqlite3
import tempfile
import unittest

from befave.dumper import run_dump
from befave.ingester import has_history, open_db, run_ingest


def write_export(path, urls):
    links = "\n".join(f'<DT><A HREF="{u}">title of {u}</A>' for u in urls)
    with open(path, "w") as f:
        f.write("<!DOCTYPE NETSCAPE-Bookmark-file-1>\n<DL><p>\n" + links + "\n</DL><p>\n")


def url(n):
    return f"https://example.com/{n}"


class DeletionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "f.db")

    def imp(self, profile, urls, track=False, yes=False, decide=None, confirm=None):
        path = os.path.join(self.tmp.name, f"{profile}.html")
        write_export(path, urls)
        return run_ingest([path], self.db, profile, track, yes, confirm, decide)

    def query(self, sql, *args):
        conn = sqlite3.connect(self.db)
        try:
            return conn.execute(sql, args).fetchall()
        finally:
            conn.close()

    def urls(self):
        return {r[0] for r in self.query("SELECT url FROM bookmarks WHERE deleted = 0")}

    def dump(self):
        out = os.path.join(self.tmp.name, "out.html")
        self.assertEqual(run_dump(out, "chrome", self.db), 0)
        with open(out) as f:
            return f.read()

    @staticmethod
    def delete_all(candidates):
        return [c["url_norm"] for c in candidates], []

    @staticmethod
    def keep_all(candidates):
        return [], [c["url_norm"] for c in candidates]

    def test_untracked_ingest_never_deletes(self):
        self.imp("a", [url(1), url(2)])
        self.imp("a", [url(1)])
        self.assertEqual(self.urls(), {url(1), url(2)})

    def test_first_ingest_has_nothing_to_compare(self):
        calls = []
        self.imp("a", [url(1)], track=True, decide=lambda c: calls.append(c) or ([], []))
        self.assertEqual(calls, [])

    def test_delete_propagates_to_other_profiles(self):
        self.imp("a", [url(1), url(2), url(3)])
        self.imp("b", [url(1), url(2), url(3)])
        self.imp("a", [url(1), url(3)], track=True, decide=self.delete_all)
        self.assertEqual(self.urls(), {url(1), url(3)})
        self.assertNotIn(url(2), self.dump())

    def test_candidates_show_title_folder_and_file(self):
        self.imp("a", [url(1), url(2)])
        seen = []
        self.imp("a", [url(1)], track=True, decide=lambda c: seen.extend(c) or ([], []))
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]["url"], url(2))
        self.assertEqual(seen[0]["title"], f"title of {url(2)}")
        self.assertEqual([os.path.basename(f) for f in seen[0]["files"]], ["a.html"])

    def test_not_in_file_and_not_held_is_not_a_candidate(self):
        self.imp("a", [url(1), url(2)])
        self.imp("b", [url(3)])
        seen = []
        self.imp("b", [url(3)], track=True, decide=lambda c: seen.extend(c) or ([], []))
        self.assertEqual(seen, [])

    def test_keep_marks_safe_and_is_not_asked_again(self):
        self.imp("a", [url(1), url(2)])
        self.imp("a", [url(1)], track=True, decide=self.keep_all)
        self.assertEqual(self.urls(), {url(1), url(2)})
        self.assertEqual(self.query("SELECT count(*) FROM safe_urls")[0][0], 1)
        seen = []
        self.imp("a", [url(1)], track=True, decide=lambda c: seen.extend(c) or ([], []))
        self.assertEqual(seen, [])

    def test_decline_leaves_favorites_alone(self):
        self.imp("a", [url(1), url(2)])
        self.imp("a", [url(1)], track=True)
        self.assertEqual(self.urls(), {url(1), url(2)})
        self.assertEqual(self.query("SELECT count(*) FROM safe_urls")[0][0], 0)

    def test_yes_deletes_all_candidates(self):
        self.imp("a", [url(1), url(2)])
        self.imp("a", [url(1)], track=True, yes=True)
        self.assertEqual(self.urls(), {url(1)})

    def test_one_by_one_choices(self):
        self.imp("a", [url(1), url(2), url(3)])
        self.imp("a", [url(1)], track=True,
                 decide=lambda c: ([c[0]["url_norm"]], [c[1]["url_norm"]]))
        self.assertEqual(len(self.urls()), 2)

    def test_stale_profile_does_not_resurrect(self):
        self.imp("a", [url(1), url(2)])
        self.imp("b", [url(1), url(2)])
        self.imp("a", [url(1)], track=True, decide=self.delete_all)
        self.imp("b", [url(1), url(2)])
        self.assertEqual(self.urls(), {url(1)})

    def test_readd_requires_confirmation(self):
        self.imp("a", [url(1), url(2)])
        self.imp("a", [url(1)], track=True, decide=self.delete_all)
        self.imp("a", [url(1), url(2)])
        self.assertEqual(self.urls(), {url(1)})
        self.imp("a", [url(1), url(2)], yes=True)
        self.assertEqual(self.urls(), {url(1), url(2)})

    def test_dump_never_imported_causes_no_false_deletion(self):
        self.imp("a", [url(1), url(2)])
        self.imp("b", [url(3)])
        self.dump()
        self.imp("a", [url(1), url(2)], track=True, decide=self.delete_all)
        self.assertEqual(self.urls(), {url(1), url(2), url(3)})

    def test_dump_imported_then_delete_is_noticed_after_one_ingest(self):
        self.imp("a", [url(1), url(2)])
        self.imp("b", [url(3)])
        self.dump()
        self.imp("a", [url(1), url(2), url(3)])
        self.imp("a", [url(1), url(2)], track=True, decide=self.delete_all)
        self.assertEqual(self.urls(), {url(1), url(2)})

    def test_dump_skips_deleted_and_records_nothing(self):
        self.imp("a", [url(1), url(2)])
        self.imp("a", [url(1)], track=True, decide=self.delete_all)
        self.assertNotIn(url(2), self.dump())
        self.assertEqual(self.query("SELECT count(*) FROM ingests")[0][0], 2)

    def test_files_sharing_a_profile_are_one_run(self):
        f1 = os.path.join(self.tmp.name, "1.html")
        f2 = os.path.join(self.tmp.name, "2.html")
        write_export(f1, [url(1), url(2)])
        write_export(f2, [url(2), url(3)])
        self.assertEqual(run_ingest([f1, f2], self.db, "all"), 0)
        self.assertEqual(self.query("SELECT count(*) FROM ingests")[0][0], 1)
        self.assertEqual(len(self.query("SELECT path FROM ingest_files")), 2)
        write_export(f2, [url(3)])
        self.assertEqual(run_ingest([f1, f2], self.db, "all", True, False, None,
                                    self.delete_all), 0)
        self.assertEqual(self.urls(), {url(1), url(2), url(3)})
        write_export(f1, [url(1)])
        self.assertEqual(run_ingest([f1, f2], self.db, "all", True, False, None,
                                    self.delete_all), 0)
        self.assertEqual(self.urls(), {url(1), url(3)})

    def test_dump_single_and_merged_profiles(self):
        self.imp("a", [url(1), url(2)])
        self.imp("b", [url(2), url(3)])
        self.imp("c", [url(4)])
        out = os.path.join(self.tmp.name, "p.html")
        self.assertEqual(run_dump(out, "chrome", self.db, ["a"]), 0)
        text = open(out).read()
        self.assertIn(url(1), text)
        self.assertNotIn(url(3), text)
        self.assertEqual(run_dump(out, "chrome", self.db, ["a", "b"]), 0)
        text = open(out).read()
        self.assertEqual(sum(url(n) in text for n in (1, 2, 3, 4)), 3)
        self.assertEqual(text.count(f'HREF="{url(2)}"'), 1)

    def test_dump_unknown_profile_is_an_error(self):
        self.imp("a", [url(1)])
        self.assertEqual(run_dump(os.path.join(self.tmp.name, "x.html"), "chrome",
                                  self.db, ["nope"]), 1)

    def test_has_history(self):
        self.assertFalse(has_history(self.db, "a"))
        self.imp("a", [url(1)])
        self.assertTrue(has_history(self.db, "a"))
        self.assertFalse(has_history(self.db, "b"))

    def test_browser_imported_folder_is_not_kept(self):
        path = os.path.join(self.tmp.name, "o.html")
        with open(path, "w") as f:
            f.write("<!DOCTYPE NETSCAPE-Bookmark-file-1>\n"
                    "<DL><p><DT><H3 PERSONAL_TOOLBAR_FOLDER=\"true\">Bookmarks Bar</H3><DL><p>"
                    "<DT><H3>Imported</H3><DL><p><DT><H3>work</H3><DL><p>"
                    "<DT><A HREF=\"https://a.example/\">a</A></DL><p></DL><p>"
                    "<DT><H3>mine</H3><DL><p><DT><H3>Imported</H3><DL><p>"
                    "<DT><A HREF=\"https://b.example/\">b</A></DL><p></DL><p></DL><p></DL><p>")
        run_ingest([path], self.db, "o")
        folders = dict(self.query("SELECT url, folder FROM bookmarks"))
        self.assertEqual(folders["https://a.example/"], "Bookmarks Bar/work")
        self.assertEqual(folders["https://b.example/"], "Bookmarks Bar/mine/Imported")
        self.assertEqual(self.dump().count("<H3>Imported</H3>"), 1)

    def test_trash_folder_and_subfolders_are_skipped(self):
        path = os.path.join(self.tmp.name, "trash.html")
        with open(path, "w") as f:
            f.write("<!DOCTYPE NETSCAPE-Bookmark-file-1>\n"
                    "<DL><p><DT><H3>tRaSh</H3><DL><p>"
                    f'<DT><A HREF="{url(1)}">trashed</A>'
                    "<DT><H3>nested</H3><DL><p>"
                    f'<DT><A HREF="{url(2)}">also trashed</A>'
                    "</DL><p></DL><p>"
                    "<DT><H3>regular</H3><DL><p>"
                    f'<DT><A HREF="{url(3)}">kept</A>'
                    "</DL><p></DL><p>")
        self.assertEqual(run_ingest([path], self.db, "o"), 0)
        self.assertEqual(self.urls(), {url(3)})


OLD_SCHEMA = """
CREATE TABLE bookmarks (id INTEGER PRIMARY KEY, url_norm TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL, title TEXT, folder TEXT, add_date INTEGER, last_modified INTEGER,
    tags TEXT, icon TEXT);
CREATE TABLE profiles (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE snapshots (id INTEGER PRIMARY KEY, profile_id INTEGER NOT NULL,
    taken_at INTEGER NOT NULL, kind TEXT NOT NULL);
CREATE TABLE profile_items (snapshot_id INTEGER NOT NULL, url_norm TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, url_norm));
CREATE TABLE tombstones (url_norm TEXT PRIMARY KEY, profile_id INTEGER NOT NULL,
    deleted_at INTEGER NOT NULL);
"""


class MigrationTests(unittest.TestCase):
    def test_old_database_is_upgraded_in_place(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = os.path.join(tmp.name, "old.db")
        conn = sqlite3.connect(db)
        conn.executescript(OLD_SCHEMA)
        conn.executemany("INSERT INTO bookmarks (url_norm, url, title, folder) VALUES (?,?,?,?)",
                         [(url(1), url(1), "one", "f"), (url(2), url(2), "two", "f")])
        conn.execute("INSERT INTO profiles VALUES (1, 'work')")
        conn.execute("INSERT INTO snapshots VALUES (1, 1, 100, 'ingest')")
        conn.execute("INSERT INTO snapshots VALUES (2, 1, 200, 'dump')")
        conn.executemany("INSERT INTO profile_items VALUES (?,?)",
                         [(1, url(1)), (2, url(1)), (2, url(2)), (2, url(9))])
        conn.execute("INSERT INTO tombstones VALUES (?, 1, 150)", (url(5),))
        conn.commit()
        conn.close()

        conn = open_db(db)
        self.assertTrue(os.path.exists(db + ".bak"))
        held = conn.execute("SELECT url_norm, title FROM profile_bookmarks").fetchall()
        self.assertEqual(held, [(url(1), "one")])
        self.assertEqual(conn.execute(
            "SELECT url_norm FROM bookmarks WHERE deleted = 1").fetchall(), [(url(5),)])
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
        self.assertFalse({"snapshots", "profile_items", "tombstones"} & tables)
        conn.close()
        open_db(db).close()


if __name__ == "__main__":
    unittest.main()
