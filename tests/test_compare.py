import os
import tempfile
import unittest

from befave.compare import compare, run_compare
from befave.dumper import run_dump
from befave.ingester import run_ingest
from test_deletions import url, write_export


class CompareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "f.db")
        for name, urls in (("a", [1, 2, 3]), ("b", [3, 4])):
            path = os.path.join(self.tmp.name, f"{name}.html")
            write_export(path, [url(n) for n in urls])
            run_ingest([path], self.db, name)

    def test_two_profiles(self):
        both, only_a, only_b, _ = compare(self.db, "a", "b")
        self.assertEqual(both, {url(3)})
        self.assertEqual(only_a, {url(1), url(2)})
        self.assertEqual(only_b, {url(4)})

    def test_against_database(self):
        both, only_a, only_b, _ = compare(self.db, "a")
        self.assertEqual(both, {url(1), url(2), url(3)})
        self.assertEqual(only_a, set())
        self.assertEqual(only_b, {url(4)})

    def test_dump_is_not_assumed_imported(self):
        run_dump(os.path.join(self.tmp.name, "out.html"), "chrome", self.db, "a")
        _, _, only_b, _ = compare(self.db, "a")
        self.assertEqual(only_b, {url(4)})

    def test_unknown_profile(self):
        with self.assertRaises(ValueError):
            compare(self.db, "nope")
        self.assertEqual(run_compare(self.db, "a", "nope"), 1)


if __name__ == "__main__":
    unittest.main()
