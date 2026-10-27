import contextlib
import io
import os
import unittest

from befave.query import run_query
import test_deletions
from test_deletions import url


class QueryTests(unittest.TestCase):
    def q(self, view, **kw):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = run_query(self.db, view, **kw)
        return status, out.getvalue(), err.getvalue()

    def setUp(self):
        self.h = test_deletions.DeletionTests()
        self.h.setUp()
        self.addCleanup(self.h.tmp.cleanup)
        self.db = self.h.db
        self.imp = self.h.imp
        self.delete_all = self.h.delete_all
        self.keep_all = self.h.keep_all
        self.imp("a", [url(1), url(2), url(3)])
        self.imp("b", [url(3)])
        self.imp("a", [url(1), url(3)], track=True, decide=self.delete_all)
        self.imp("b", [url(3)], track=True, decide=self.keep_all)

    def test_show_deleted(self):
        status, out, _ = self.q("show_deleted")
        self.assertEqual(status, 0)
        self.assertIn(url(2), out)
        self.assertNotIn(url(1), out)

    def test_urls_are_bare(self):
        _, out, _ = self.q("show_deleted", urls=True)
        self.assertEqual(out.split(), [url(2)])

    def test_urls_not_for_profiles(self):
        self.assertEqual(self.q("profiles", urls=True)[0], 1)

    def test_show_deleted_rejects_profile(self):
        self.assertEqual(self.q("show_deleted", profile="a")[0], 1)

    def test_profiles_counts(self):
        _, out, _ = self.q("profiles")
        self.assertRegex(out, r"a\s+2")
        self.assertRegex(out, r"b\s+1")

    def test_history_lists_runs_and_filters(self):
        _, out, _ = self.q("history")
        self.assertEqual(out.count("a.html") + out.count("b.html"), 4)
        _, out, _ = self.q("history", profile="b")
        self.assertNotIn("a.html", out)

    def test_safe_empty_and_filled(self):
        self.assertIn("Nothing", self.q("safe", profile="a")[1])
        self.imp("a", [url(1)], track=True, decide=self.keep_all)
        self.assertIn(url(3), self.q("safe", profile="a")[1])

    def test_search_and_filters(self):
        self.assertEqual(self.q("search", text="/1", urls=True)[1].split(), [url(1)])
        self.assertIn("Nothing", self.q("search", text="/2")[1])
        self.assertIn("Nothing", self.q("search", text="example", profile="nope")[1])
        self.assertEqual(self.q("search", text="")[0], 1)

    def test_search_wildcards_are_literal(self):
        self.assertIn("Nothing", self.q("search", text="%")[1])

    def test_stats(self):
        _, out, _ = self.q("stats")
        self.assertRegex(out, r"Favorites\s+2")
        self.assertRegex(out, r"Deleted\s+1")

    def test_missing_database(self):
        os.remove(self.db)
        self.assertEqual(self.q("stats")[0], 1)


if __name__ == "__main__":
    unittest.main()
