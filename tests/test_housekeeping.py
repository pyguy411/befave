import sqlite3
import threading
from http.client import InvalidURL
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import URLError

import pytest

from befave import cli, housekeeping
from befave.ingester import SCHEMA, open_db
from befave.query import run_query


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "favorites.db")
    conn = open_db(path)
    conn.close()
    return path


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        requests = []

        def do_GET(self):
            self.requests.append(self.path)
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/200")
            else:
                self.send_response(int(self.path[1:]))
            self.end_headers()

        def log_message(self, format, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}", Handler.requests
    httpd.shutdown()
    thread.join()
    httpd.server_close()


def insert(db, url, status=None, deleted=0):
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO bookmarks (url_norm, url, http_status, deleted) "
            "VALUES (?, ?, ?, ?)",
            (url, url, status, deleted),
        )


def statuses(db):
    with sqlite3.connect(db) as conn:
        return dict(conn.execute("SELECT url, http_status FROM bookmarks"))


@pytest.mark.parametrize("code", [200, 404, 401, 403, 500])
@pytest.mark.parametrize("deleted", [0, 1])
def test_response_codes_are_saved_once(db, server, code, deleted, capsys):
    base, requests = server
    url = f"{base}/{code}"
    insert(db, url, deleted=deleted)

    assert cli.main(["housekeeping", "--validate-urls", "--db", db]) == 0
    assert statuses(db)[url] == code
    assert requests == [f"/{code}"]
    assert cli.main(["housekeeping", "--validate-urls", "--db", db]) == 0
    assert requests == [f"/{code}"]
    assert run_query(db, "url_status") == 0
    output = capsys.readouterr().out
    assert url in output
    assert str(code) in output


def test_redirect_records_final_response(db, server):
    base, requests = server
    url = f"{base}/redirect"
    insert(db, url)
    assert housekeeping.run_url_validation(db) == 0
    assert statuses(db)[url] == 200
    assert requests == ["/redirect", "/200"]


def test_failure_does_not_stop_remaining_urls(db, server, monkeypatch, capsys):
    base, requests = server
    failed, checked, saved = f"{base}/failure", f"{base}/200", f"{base}/404"
    insert(db, failed)
    insert(db, checked)
    insert(db, saved, status=404)
    real_urlopen = housekeeping.urlopen

    def request(url, timeout):
        if url == failed:
            raise URLError("offline")
        return real_urlopen(url, timeout=timeout)

    monkeypatch.setattr(housekeeping, "urlopen", request)
    assert housekeeping.run_url_validation(db) == 1
    assert statuses(db) == {failed: None, checked: 200, saved: 404}
    assert requests == ["/200"]
    assert run_query(db, "url_status") == 0
    assert "unchecked" in capsys.readouterr().out


@pytest.mark.parametrize(
    "error", [URLError("offline"), TimeoutError("timed out"), InvalidURL("invalid")]
)
def test_failed_requests_are_reported_and_retried(db, monkeypatch, capsys, error):
    url = "https://example.test/"
    insert(db, url)
    calls = []

    def fail(url, timeout):
        calls.append(url)
        raise error

    monkeypatch.setattr(housekeeping, "urlopen", fail)
    assert housekeeping.run_url_validation(db) == 1
    assert housekeeping.run_url_validation(db) == 1
    assert calls == [url, url]
    assert statuses(db)[url] is None
    assert "error checking" in capsys.readouterr().err


def test_non_http_is_reported_without_request(db, monkeypatch, capsys):
    url = "ftp://example.test/file"
    insert(db, url)

    def unexpected_request(*args, **kwargs):
        pytest.fail("non-HTTP URL was requested")

    monkeypatch.setattr(housekeeping, "urlopen", unexpected_request)
    assert housekeeping.run_url_validation(db) == 0
    assert statuses(db)[url] is None
    assert "not HTTP/HTTPS" in capsys.readouterr().err


def test_responses_survive_interruption(db, server, monkeypatch):
    base, requests = server
    first, second = f"{base}/200", f"{base}/404"
    insert(db, first)
    insert(db, second)
    real_urlopen = housekeeping.urlopen

    def interrupt(url, timeout):
        if url == second:
            raise KeyboardInterrupt
        return real_urlopen(url, timeout=timeout)

    monkeypatch.setattr(housekeeping, "urlopen", interrupt)
    with pytest.raises(KeyboardInterrupt):
        housekeeping.run_url_validation(db)
    assert statuses(db) == {first: 200, second: None}
    monkeypatch.setattr(housekeeping, "urlopen", real_urlopen)
    assert housekeeping.run_url_validation(db) == 0
    assert requests == ["/200", "/404"]


def test_upgrade_existing_database(tmp_path):
    path = str(tmp_path / "old.db")
    old_schema = SCHEMA.replace(",\n    http_status INTEGER", "")
    with sqlite3.connect(path) as conn:
        conn.executescript(old_schema)
        conn.execute(
            "INSERT INTO bookmarks (url_norm, url) VALUES (?, ?)",
            ("https://example.test/", "https://example.test/"),
        )
    for _ in range(2):
        conn = open_db(path)
        assert conn.execute("SELECT http_status FROM bookmarks").fetchone() == (None,)
        conn.close()
    assert statuses(path) == {"https://example.test/": None}


def test_interactive_housekeeping(db, server, monkeypatch):
    base, _ = server
    url = f"{base}/200"
    insert(db, url)
    answers = iter(["5", "2", db, "1"])
    monkeypatch.setattr(cli, "INTERACTIVE", True)
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    assert cli.main([]) == 0
    assert statuses(db)[url] == 200


def test_missing_database_and_option(tmp_path, monkeypatch, capsys):
    db = str(tmp_path / "missing.db")
    monkeypatch.setattr(cli, "INTERACTIVE", False)
    assert cli.main(["housekeeping", "--validate-urls", "--db", db]) == 1
    assert "database not found" in capsys.readouterr().err
    with pytest.raises(SystemExit, match="--validate-urls"):
        cli.main(["housekeeping", "--db", db])
