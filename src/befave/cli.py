"""befave: interactive wrapper around the ingester and dumper."""
import argparse
import glob
import os
import shlex
import sys

from .dumper import BROWSER_TOOLBAR, run_dump
from .ingester import DEFAULT_DB, list_sources, run_ingest

INTERACTIVE = sys.stdin.isatty()


def ask(question, default=None, choices=None):
    """Prompt until a non-empty answer (or the default) is given."""
    hint = f" [{'/'.join(choices)}]" if choices else ""
    hint += f" (default: {default})" if default else ""
    while True:
        try:
            answer = input(f"{question}{hint}: ").strip()
        except EOFError:
            raise SystemExit("\naborted")
        answer = answer or default
        if answer and (not choices or answer.lower() in choices):
            return answer.lower() if choices else answer
        print("  please enter a valid answer")


def choose(question, options):
    """Show numbered options and return the index of the one picked."""
    print(question)
    for i, option in enumerate(options, 1):
        print(f"  {i}. {option}")
    numbers = [str(i) for i in range(1, len(options) + 1)]
    return int(ask("Choose a number", choices=numbers)) - 1


def need(value, missing_msg, prompt, **kw):
    """Return value if given; otherwise prompt, or fail when not interactive."""
    if value:
        return value
    if not INTERACTIVE:
        raise SystemExit(f"befave: error: {missing_msg}")
    return ask(prompt, **kw)


def pick_db(db):
    if db:
        return db
    if not INTERACTIVE:
        return DEFAULT_DB
    if choose("Which database should be used?",
              [f"Use the default database: {DEFAULT_DB}", "Use a different database"]) == 0:
        return DEFAULT_DB
    return ask("Path to the database file")


def pick_browser(browser):
    if browser:
        return browser
    if not INTERACTIVE:
        raise SystemExit("befave: error: --browser is required")
    names = sorted(BROWSER_TOOLBAR)
    return names[choose("Which browser will import this file?", names)]


def pick_source(db, given=None):
    """Return the named source, or let the user pick an existing one or add a new one."""
    if given:
        return given
    if not INTERACTIVE:
        raise SystemExit("befave: error: --source is required")
    existing = list_sources(db)
    if existing:
        i = choose("Which source is this? (one browser profile on one computer)",
                   existing + ["Add a new source"])
        if i < len(existing):
            return existing[i]
    else:
        print("No sources yet. A source is one browser profile on one computer.")
    return ask("Name for the new source (e.g. work-chrome)")


def confirm(msg):
    if not INTERACTIVE:
        print(f"  {msg} (not confirmed; pass --yes to accept)")
        return False
    return choose(msg, ["Yes", "No"]) == 0


def expand_files(patterns):
    """Expand ~ and glob patterns; matches are sorted by name, duplicates dropped."""
    files = []
    for pattern in patterns:
        pattern = os.path.expanduser(pattern)
        matches = sorted(glob.glob(pattern)) if glob.has_magic(pattern) else [pattern]
        if not matches:
            raise SystemExit(f"befave: error: no files match {pattern}")
        files += [m for m in matches if m not in files]
    return files


def do_ingest(args):
    files = args.files
    if not files:
        if not INTERACTIVE:
            raise SystemExit("befave: error: no bookmark files given")
        files = shlex.split(
            ask("Browser export file(s) to ingest (.html or .zip, space separated)"))
    files = expand_files(files)
    if args.source and len(args.source) != len(files):
        raise SystemExit(f"befave: error: {len(files)} file(s) need {len(files)} --source "
                         f"option(s), in the same order; got {len(args.source)}")
    given = dict(zip(files, args.source))
    db = pick_db(args.db)
    db = os.path.expanduser(db)
    used = set()

    def source_for(path):
        # Each file is a full snapshot of its source, so two files from one source
        # would make the second look like it deleted everything missing from it.
        name = pick_source(db, given.get(path))
        if name in used:
            raise ValueError(f"{path}: source '{name}' was already used by an earlier "
                             "file in this run; each file needs its own source")
        used.add(name)
        return name

    return run_ingest(files, db, source_for, args.yes, confirm)


def do_dump(args):
    browser = pick_browser(args.browser)
    output = need(args.output, "output file is required", "Output file (.html)")
    db = pick_db(args.db)
    db = os.path.expanduser(db)
    return run_dump(os.path.expanduser(output), browser, db, pick_source(db, args.source))


def build_parser():
    ap = argparse.ArgumentParser(
        prog="befave",
        description="Ingest browser bookmark export files into a database, or dump the "
                    "database out as a file a browser can import. Any missing details "
                    "are asked interactively.")
    sub = ap.add_subparsers(dest="action", metavar="{ingest,dump}")

    ingest = sub.add_parser("ingest", help="ingest browser export file(s) into the database")
    ingest.add_argument("files", nargs="*",
                      help="bookmark export(s): .html or .zip; globs like 'exports/*' work")
    ingest.add_argument("--db", help=f"database file (default: {DEFAULT_DB})")
    ingest.add_argument("--source", action="append", default=[],
                      help="browser profile a file comes from; repeat once per file, "
                           "in file order")
    ingest.add_argument("--yes", action="store_true",
                      help="accept deletion and restore confirmations")
    ingest.set_defaults(func=do_ingest)

    dump = sub.add_parser("dump", help="dump the database out as a file for a target browser")
    dump.add_argument("output", nargs="?", help="output .html file")
    dump.add_argument("--browser", choices=sorted(BROWSER_TOOLBAR), help="target browser")
    dump.add_argument("--db", help=f"database file (default: {DEFAULT_DB})")
    dump.add_argument("--source", help="name of the browser profile the file is for")
    dump.set_defaults(func=do_dump)
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if not args.action:
        if not INTERACTIVE:
            ap.error("an action (ingest or dump) is required")
        action = ["ingest", "dump"][choose("What would you like to do?", [
            "ingest - feed a browser's exported bookmarks file into the database",
            "dump - dump the database out as a file for a browser to import",
        ])]
        args = ap.parse_args([action])
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
