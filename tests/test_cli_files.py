import os
import tempfile
import unittest

from befave.cli import expand_files


class ExpandFilesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for name in ("chrome.html", "0_firefox.html", "opera.html"):
            open(os.path.join(self.tmp.name, name), "w").close()

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def test_glob_is_sorted_by_name(self):
        got = expand_files([self.path("*.html")])
        self.assertEqual([os.path.basename(p) for p in got],
                         ["0_firefox.html", "chrome.html", "opera.html"])

    def test_duplicates_dropped_and_order_kept(self):
        got = expand_files([self.path("opera.html"), self.path("*.html")])
        self.assertEqual([os.path.basename(p) for p in got],
                         ["opera.html", "0_firefox.html", "chrome.html"])

    def test_plain_path_passes_through(self):
        self.assertEqual(expand_files(["missing.html"]), ["missing.html"])

    def test_unmatched_glob_is_an_error(self):
        with self.assertRaises(SystemExit):
            expand_files([self.path("*.zip")])


if __name__ == "__main__":
    unittest.main()
