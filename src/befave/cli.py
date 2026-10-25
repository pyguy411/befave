"""befave: interactive wrapper around the puller and pusher."""
import argparse
import os
import shlex
import sys

from .pusher import BROWSER_TOOLBAR, run_push
from .puller import DEFAULT_DB, list_sources, run_pull

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


def do_pull(args):
    files = args.files
    if not files:
        if not INTERACTIVE:
            raise SystemExit("befave: error: no bookmark files given")
        files = shlex.split(ask("Browser export file(s) to pull (.html or .zip, space separated)"))
    db = pick_db(args.db)
    db = os.path.expanduser(db)
    return run_pull([os.path.expanduser(f) for f in files], db,
                    lambda path: pick_source(db, args.source), args.yes, confirm)


def do_push(args):
    browser = pick_browser(args.browser)
    output = need(args.output, "output file is required", "Output file (.html)")
    db = pick_db(args.db)
    db = os.path.expanduser(db)
    return run_push(os.path.expanduser(output), browser, db, pick_source(db, args.source))


def build_parser():
    ap = argparse.ArgumentParser(
        prog="befave",
        description="Pull browser bookmark export files into a database, or push the "
                    "database out as a file a browser can import. Any missing details "
                    "are asked interactively.")
    sub = ap.add_subparsers(dest="action", metavar="{pull,push}")

    pull = sub.add_parser("pull", help="pull browser export file(s) into the database")
    pull.add_argument("files", nargs="*", help="bookmark export(s): .html or .zip")
    pull.add_argument("--db", help=f"database file (default: {DEFAULT_DB})")
    pull.add_argument("--source", help="name of the browser profile the file(s) come from")
    pull.add_argument("--yes", action="store_true",
                      help="accept deletion and restore confirmations")
    pull.set_defaults(func=do_pull)

    push = sub.add_parser("push", help="push the database out as a file for a target browser")
    push.add_argument("output", nargs="?", help="output .html file")
    push.add_argument("--browser", choices=sorted(BROWSER_TOOLBAR), help="target browser")
    push.add_argument("--db", help=f"database file (default: {DEFAULT_DB})")
    push.add_argument("--source", help="name of the browser profile the file is for")
    push.set_defaults(func=do_push)
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if not args.action:
        if not INTERACTIVE:
            ap.error("an action (pull or push) is required")
        action = ["pull", "push"][choose("What would you like to do?", [
            "pull - read a browser's exported bookmarks file into the database",
            "push - write the database out as a file for a browser to import",
        ])]
        args = ap.parse_args([action])
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
