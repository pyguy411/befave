import sqlite3

import pytest

from befave import cli
from befave.ingester import BookmarkParser, SCHEMA, open_db


@pytest.fixture
def favorites_db(tmp_path):
    db = tmp_path / "favorites.db"
    conn = open_db(str(db))
    with conn:
        conn.executemany(
            "INSERT INTO bookmarks (url_norm, url, title, http_status, deleted) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (f"https://example.test/{name}", f"https://example.test/{name}",
                 name, status, deleted)
                for name, status, deleted in [
                    ("ok-a", 200, 0), ("ok-b", 200, 0), ("missing", 404, 0),
                    ("auth", 401, 0), ("forbidden", 403, 0), ("error", 500, 0),
                    ("unchecked", None, 0), ("deleted", 200, 1),
                ]
            ],
        )
        conn.execute(
            "INSERT INTO bookmarks (url_norm, url, title) VALUES (?, ?, ?)",
            ("ftp://example.test/file", "ftp://example.test/file", "ftp"),
        )
        conn.executemany("INSERT INTO profiles (id, name) VALUES (?, ?)", [(1, "a"), (2, "b")])
        conn.executemany(
            "INSERT INTO profile_bookmarks (profile_id, url_norm, ingest_id) VALUES (?, ?, ?)",
            [
                (profile, f"https://example.test/{name}", "run")
                for profile, name in [
                    (1, "ok-a"), (1, "missing"), (1, "unchecked"), (1, "deleted"),
                    (2, "ok-b"), (2, "missing"), (2, "auth"),
                ]
            ],
        )
    conn.close()
    return db


@pytest.mark.parametrize(
    "profiles,include_invalid,expected",
    [
        ([], False, {"ok-a", "ok-b"}),
        ([], True, {"ok-a", "ok-b", "missing", "auth", "forbidden", "error", "unchecked", "ftp"}),
        (["a"], False, {"ok-a"}),
        (["a"], True, {"ok-a", "missing", "unchecked"}),
        (["a", "b"], False, {"ok-a", "ok-b"}),
        (["a", "b"], True, {"ok-a", "ok-b", "missing", "auth", "unchecked"}),
    ],
)
def test_dump_filters_status_and_profiles(
    favorites_db, tmp_path, monkeypatch, capsys, profiles, include_invalid, expected
):
    monkeypatch.setattr(cli, "INTERACTIVE", False)
    output = tmp_path / "out.html"
    args = ["dump", str(output), "--browser", "chrome", "--db", str(favorites_db)]
    for profile in profiles:
        args.extend(["--profile", profile])
    if include_invalid:
        args.append("--include-invalid")
    assert cli.main(args) == 0
    parser = BookmarkParser()
    parser.feed(output.read_text())
    assert {bookmark["title"] for bookmark in parser.bookmarks} == expected
    assert len(parser.bookmarks) == len(expected)
    assert f"{len(expected)} bookmarks dumped" in capsys.readouterr().out


@pytest.mark.parametrize("include_invalid", [False, True])
def test_old_database_unchecked_bookmarks(tmp_path, monkeypatch, include_invalid):
    db = tmp_path / "old.db"
    old_schema = SCHEMA.replace(",\n    http_status INTEGER", "")
    with sqlite3.connect(db) as conn:
        conn.executescript(old_schema)
        conn.execute(
            "INSERT INTO bookmarks (url_norm, url) VALUES (?, ?)",
            ("https://example.test/", "https://example.test/"),
        )
    monkeypatch.setattr(cli, "INTERACTIVE", False)
    output = tmp_path / "out.html"
    args = ["dump", str(output), "--browser", "chrome", "--db", str(db)]
    if include_invalid:
        args.append("--include-invalid")
    assert cli.main(args) == 0
    parser = BookmarkParser()
    parser.feed(output.read_text())
    assert len(parser.bookmarks) == int(include_invalid)
