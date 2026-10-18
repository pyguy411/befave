"""befave: interactive wrapper around the importer and exporter."""
import argparse
import os
import shlex
import sys

from .exporter import BROWSER_TOOLBAR, run_export
from .importer import DEFAULT_DB, run_import

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
    return ask("Database file", default=DEFAULT_DB) if INTERACTIVE else DEFAULT_DB


def do_import(args):
    files = args.files
    if not files:
        if not INTERACTIVE:
            raise SystemExit("befave: error: no bookmark files given")
        files = shlex.split(ask("Bookmark file(s) to import (.html or .zip, space separated)"))
    db = pick_db(args.db)
    return run_import([os.path.expanduser(f) for f in files], os.path.expanduser(db))


def do_export(args):
    browser = need(args.browser, "--browser is required", "Target browser",
                   choices=sorted(BROWSER_TOOLBAR))
    output = need(args.output, "output file is required", "Output file (.html)")
    db = pick_db(args.db)
    return run_export(os.path.expanduser(output), browser, os.path.expanduser(db))


def build_parser():
    ap = argparse.ArgumentParser(
        prog="befave",
        description="Import browser bookmark exports into a database, or export them "
                    "for a browser. Any missing details are asked interactively.")
    sub = ap.add_subparsers(dest="action", metavar="{import,export}")

    imp = sub.add_parser("import", help="import bookmark export file(s) into the database")
    imp.add_argument("files", nargs="*", help="bookmark export(s): .html or .zip")
    imp.add_argument("--db", help=f"database file (default: {DEFAULT_DB})")
    imp.set_defaults(func=do_import)

    exp = sub.add_parser("export", help="export the database for a target browser")
    exp.add_argument("output", nargs="?", help="output .html file")
    exp.add_argument("--browser", choices=sorted(BROWSER_TOOLBAR), help="target browser")
    exp.add_argument("--db", help=f"database file (default: {DEFAULT_DB})")
    exp.set_defaults(func=do_export)
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if not args.action:
        if not INTERACTIVE:
            ap.error("an action (import or export) is required")
        action = ask("Are you importing or exporting?", choices=["import", "export"])
        args = ap.parse_args([action])
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
