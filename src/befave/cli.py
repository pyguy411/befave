"""befave: interactive wrapper around the ingester and dumper."""

import argparse
import glob
import os
import shlex
import sys
import time

from .compare import run_compare
from .dumper import BROWSER_TOOLBAR, run_dump
from .query import VIEWS, run_query
from .ingester import DEFAULT_DB, has_history, list_profiles, run_ingest

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
    if (
        choose(
            "Which database should be used?",
            [f"Use the default database: {DEFAULT_DB}", "Use a different database"],
        )
        == 0
    ):
        return DEFAULT_DB
    return ask("Path to the database file")


def pick_browser(browser):
    if browser:
        return browser
    if not INTERACTIVE:
        raise SystemExit("befave: error: --browser is required")
    names = sorted(BROWSER_TOOLBAR)
    return names[choose("Which browser will import this file?", names)]


def pick_profile(db, given=None):
    """Return the named profile, or let the user pick an existing one or add a new one."""
    if given:
        return given
    if not INTERACTIVE:
        raise SystemExit("befave: error: --profile is required")
    existing = list_profiles(db)
    if existing:
        i = choose(
            "Which profile is this? (a name you pick for the browser profile you exported from)",
            existing + ["Add a new profile"],
        )
        if i < len(existing):
            return existing[i]
    else:
        print(
            "No profiles yet. A profile is just a name you pick for this file, e.g. "
            '"Work Chrome". befave does not read or need any browser profile or '
            "account information. The name only lets it tell when a favorite should be "
            "deleted."
        )
    return ask("Name for the new profile (e.g. work-chrome)")


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


def describe(c):
    seen = "earlier ingest (before the upgrade)"
    if c["files"]:
        seen = ", ".join(os.path.basename(f) for f in c["files"])
    when = time.strftime("%Y-%m-%d", time.localtime(c["taken_at"]))
    added = (
        time.strftime("%Y-%m-%d", time.localtime(c["add_date"]))
        if c["add_date"]
        else "unknown"
    )
    return (
        f"  {c['title'] or c['url']}\n    {c['url']}\n"
        f"    folder: {c['folder'] or '(none)'}   added: {added}\n"
        f"    last seen: {seen}, ingest of {when}"
    )


def review_candidates(candidates):
    """Ask what to do with favorites that are missing; returns (delete, keep) url lists."""
    print(
        f"{len(candidates)} favorite(s) from earlier ingests of this profile are not in "
        "this file:"
    )
    for c in candidates[:20]:
        print(describe(c))
    if len(candidates) > 20:
        print(f"  ... and {len(candidates) - 20} more")
    urls = [c["url_norm"] for c in candidates]
    choice = choose(
        "What should happen to them?",
        [
            "Delete all of them (they were deleted in the browser)",
            "Keep all of them (not asked about these again)",
            "Review one by one",
        ],
    )
    if choice == 0:
        return urls, []
    if choice == 1:
        return [], urls
    delete, keep = [], []
    for c in candidates:
        print(describe(c))
        (
            delete
            if choose("This favorite is not in the file:", ["Delete it", "Keep it"])
            == 0
            else keep
        ).append(c["url_norm"])
    return delete, keep


def do_ingest(args):
    files = args.files
    if not files:
        if not INTERACTIVE:
            raise SystemExit("befave: error: no bookmark files given")
        files = shlex.split(
            ask("Browser export file(s) to ingest (.html or .zip, space separated)")
        )
    files = expand_files(files)
    profiles = args.profile
    if len(profiles) == 1:
        profiles = profiles * len(files)
    if profiles and len(profiles) != len(files):
        raise SystemExit(
            f"befave: error: {len(files)} file(s) need one --profile for all "
            f"or {len(files)} in file order; got {len(profiles)}"
        )
    given = dict(zip(files, profiles))
    db = pick_db(args.db)
    db = os.path.expanduser(db)

    last = []

    def profile_for(path):
        if given.get(path):
            return given[path]
        if INTERACTIVE and last:
            if (
                choose(
                    f"{path}\nUse the same profile as the previous file, '{last[-1]}'?",
                    ["Yes", "No - pick another profile"],
                )
                == 0
            ):
                last.append(last[-1])
                return last[-1]
        name = pick_profile(db, None)
        last.append(name)
        return name

    def track_for(name):
        if args.track_deletions:
            return True
        if not INTERACTIVE or not has_history(db, name):
            return False
        return (
            choose(
                f"'{name}' was ingested before. Check this file for favorites you deleted? "
                "(Only needed if you want deletions noticed.)",
                [
                    "Yes - offer to delete favorites that are missing from this file",
                    "No - only add favorites",
                ],
            )
            == 0
        )

    decide = review_candidates if INTERACTIVE and not args.yes else None
    return run_ingest(files, db, profile_for, track_for, args.yes, confirm, decide)


def do_dump(args):
    browser = pick_browser(args.browser)
    output = need(args.output, "output file is required", "Output file (.html)")
    db = os.path.expanduser(pick_db(args.db))
    profiles = args.profile
    if not profiles and INTERACTIVE:
        existing = list_profiles(db)
        if (
            existing
            and choose(
                "Which favorites should the file contain?",
                ["All favorites in the database", "Only the favorites of one profile"],
            )
            == 1
        ):
            profiles = [existing[choose("Which profile?", existing)]]
    return run_dump(os.path.expanduser(output), browser, db, profiles)


def do_compare(args):
    db = os.path.expanduser(pick_db(args.db))
    a = pick_profile(db, args.profile_a)
    show = (
        "common"
        if args.common
        else "only_a"
        if args.only_a
        else "only_b"
        if args.only_b
        else None
    )
    return run_compare(db, a, args.profile_b, show)


VIEW_LABELS = {
    "show_deleted": "Deleted favorites",
    "profiles": "Profiles and how many favorites each holds",
    "history": "Ingest history",
    "safe": "Favorites you chose to keep",
    "search": "Search favorites",
    "stats": "Totals",
}


def do_query(args):
    db = os.path.expanduser(pick_db(args.db))
    chosen = [v for v in VIEWS if getattr(args, v) not in (None, False)]
    if len(chosen) > 1:
        raise SystemExit(
            "befave: error: choose only one of --show-deleted, --profiles, "
            "--history, --safe, --search, --stats"
        )
    if chosen:
        view = chosen[0]
    elif INTERACTIVE:
        view = VIEWS[
            choose("What do you want to see?", [VIEW_LABELS[v] for v in VIEWS])
        ]
    else:
        view = "stats"
    text = args.search
    if view == "search" and text is None:
        text = ask("Text to search for in titles and URLs")
    return run_query(db, view, text, args.profile, args.folder, args.urls)


def build_parser():
    ap = argparse.ArgumentParser(
        prog="befave",
        description="Ingest browser bookmark export files into a database, or dump the "
        "database out as a file a browser can import. Any missing details "
        "are asked interactively.",
    )
    sub = ap.add_subparsers(dest="action", metavar="{ingest,dump,compare,query}")

    ingest = sub.add_parser(
        "ingest", help="ingest browser export file(s) into the database"
    )
    ingest.add_argument(
        "files",
        nargs="*",
        help="bookmark export(s): .html or .zip; globs like 'exports/*' work",
    )
    ingest.add_argument("--db", help=f"database file (default: {DEFAULT_DB})")
    ingest.add_argument(
        "--profile",
        action="append",
        default=[],
        help="browser profile a file comes from; repeat once per file, in file order",
    )
    ingest.add_argument(
        "--track-deletions",
        action="store_true",
        help="the profile was ingested before: offer to delete favorites "
        "that are missing from this file",
    )
    ingest.add_argument(
        "--yes",
        action="store_true",
        help="accept restore confirmations and delete every missing favorite",
    )
    ingest.set_defaults(func=do_ingest)

    dump = sub.add_parser(
        "dump", help="dump the database out as a file for a target browser"
    )
    dump.add_argument("output", nargs="?", help="output .html file")
    dump.add_argument(
        "--browser", choices=sorted(BROWSER_TOOLBAR), help="target browser"
    )
    dump.add_argument("--db", help=f"database file (default: {DEFAULT_DB})")
    dump.add_argument(
        "--profile",
        action="append",
        default=[],
        help="only dump the favorites this profile holds; repeat to merge "
        "several profiles",
    )
    dump.set_defaults(func=do_dump)

    cmp = sub.add_parser(
        "compare",
        help="compare the favorites ingested from two profiles, "
        "or from one profile and the whole database",
    )
    cmp.add_argument("profile_a", nargs="?", help="first profile")
    cmp.add_argument(
        "profile_b",
        nargs="?",
        help="second profile; leave out to compare with the whole database",
    )
    cmp.add_argument("--db", help=f"database file (default: {DEFAULT_DB})")
    show = cmp.add_mutually_exclusive_group()
    show.add_argument(
        "--common", action="store_true", help="print only the shared URLs"
    )
    show.add_argument(
        "--only-a", action="store_true", help="print only URLs only in the first"
    )
    show.add_argument(
        "--only-b", action="store_true", help="print only URLs only in the second"
    )
    cmp.set_defaults(func=do_compare)

    q = sub.add_parser(
        "query", help="show deleted favorites, profiles, history and more"
    )
    q.add_argument("--db", help=f"database file (default: {DEFAULT_DB})")
    views = q.add_mutually_exclusive_group()
    views.add_argument(
        "--show-deleted",
        dest="show_deleted",
        action="store_true",
        help="list deleted favorites",
    )
    views.add_argument(
        "--profiles",
        action="store_true",
        help="list profiles with favorite counts and last ingest",
    )
    views.add_argument(
        "--history", action="store_true", help="list ingest runs and files"
    )
    views.add_argument(
        "--safe",
        action="store_true",
        help="list favorites you chose to keep when asked about deleting",
    )
    views.add_argument(
        "--search", metavar="TEXT", help="find favorites by title or URL"
    )
    views.add_argument("--stats", action="store_true", help="show totals (the default)")
    q.add_argument("--profile", help="only this profile (--history, --safe, --search)")
    q.add_argument("--folder", help="only folders containing this text (--search)")
    q.add_argument("--urls", action="store_true", help="print bare URLs, for scripts")
    q.set_defaults(func=do_query)
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if not args.action:
        if not INTERACTIVE:
            ap.error("an action (ingest, dump, compare or query) is required")
        action = ["ingest", "dump", "compare", "query"][
            choose(
                "What would you like to do?",
                [
                    "ingest - feed a browser's exported bookmarks file into the database",
                    "dump - dump the database out as a file for a browser to import",
                    "compare - see which favorites a profile shares with another profile or the database",
                    "query - show deleted favorites, profiles, ingest history and more",
                ],
            )
        ]
        args = ap.parse_args([action])
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
