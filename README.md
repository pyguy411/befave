# befave

Keep your favorites in sync across browsers. `befave` manages the bookmark
files that browsers export. It **never talks to a browser directly**: you
export an HTML bookmarks file from the browser yourself, and you import the
file `befave` writes back into the browser yourself.

In between, `befave` merges the files from Chrome, Firefox, Safari or Opera into
one sqlite3 database with no duplicates, and remembers what you deleted. Two
commands do this: `pull` reads a browser's exported HTML file into the database,
and `push` writes the database out as an HTML file for a browser to import. (Browsers call their steps "export" and
"import"; `befave` uses its own words so
the two aren't confused.) The cycle repeats, so favorites can round trip between
browsers:

```
browser --(you export)--> bookmarks.html --(befave pull)--> database
database --(befave push)--> out.html --(you import)--> browser
```

## Why

- Frustrated that the browser on your work computer doesn't have the same
  favorites as your home computer? Export from each browser, pull both files
  into `befave`, push the merged set, and import that file into either browser.
- Added new favorites in a new browser after you pulled your favorites from
  another one? Export the new browser's bookmarks, pull them (only the new
  ones are added), then push the full set and import it into any browser.
- Switching browsers, or using several at once? Keep one master list and
  load it into whichever browser you pick up.

## Install

`befave` needs Python 3.9 or newer and has no other dependencies. Install it
with either of these:

```
pip install befave
```

or, with [uv](https://docs.astral.sh/uv/):

```
uv tool install befave
```

Check that it works:

```
befave --help
```

To run it from a checkout of this repository instead, without installing:

```
uv run befave
```

To upgrade later, use `pip install --upgrade befave` (or
`uv tool upgrade befave`).

## Usage

Run `befave` and it asks what it needs to know. Most questions are numbered
choices: type the number and press Enter. Anything you pass as an argument is
not asked again.

```
befave                      # asks: pull or push?
befave pull                 # asks for the file(s), source and database
befave pull --db a.sqlite3 --source home-firefox example_formats/firefox_bookmarks.html
befave push                 # asks for the target browser, output file, source, database
befave push out.html --browser firefox --source home-firefox --db a.sqlite3
```

### Options

| Command | Argument or option | Meaning                                          |
|---------|--------------------|--------------------------------------------------|
| `pull`  | `FILE...`          | Browser export file(s), `.html` or `.zip`        |
| `pull`  | `--source NAME`    | Browser profile the file(s) come from            |
| `pull`  | `--db PATH`        | Database file (default `~/.befave/favorites.db`) |
| `pull`  | `--yes`            | Accept the delete and restore confirmations      |
| `push`  | `OUTPUT`           | Path of the `.html` file to write                |
| `push`  | `--browser NAME`   | `chrome`, `firefox`, `opera` or `safari`         |
| `push`  | `--source NAME`    | Browser profile the file is for                  |
| `push`  | `--db PATH`        | Database file (default `~/.befave/favorites.db`) |

### Scripts and cron jobs

When not run from a terminal, `befave` never prompts. It uses the default
database unless you pass `--db`, and exits with an error if a required argument
is missing: the file (s) for `pull`, `--browser`, the output file and `--source`
for `push`, and `--source` for both. Without `--yes`, a pull that needs
confirmation (see [Deletions](#deletions)) is cancelled and nothing is changed.

```
befave pull --source work-chrome --yes bookmarks.html
befave push --source work-chrome --browser chrome out.html
```

### Step by step

**Pull**: read a browser's exported bookmarks file into the database.

1. In your browser, export your bookmarks as an HTML file (see below).
2. Run `befave` and choose `1` (pull), or run `befave pull`.
3. Enter the path to the exported file (`.html` or `.zip`).
4. **Which database?** Choose `1` to use the default database (its path is
   shown), or `2` to type the path to a different one.
5. **Which source is this?** A source is one browser profile on one computer,
   such as `work-chrome`. Pick an existing one from the list, or choose "Add a
   new source" and type a name. Use the same name every time you pull from that
   browser, because `befave` compares each pull with the previous one to spot
   favorites you deleted. See [Sources](#sources).
6. If asked to confirm deletions or restores, choose `1` (Yes) or `2` (No); see
   [Deletions](#deletions).

**Push**: write the database out as a file a browser can import.

1. Run `befave` and choose `2` (push), or run `befave push`.
2. **Which browser will import this file?** Choose the browser. This only sets
   the name of the toolbar folder in the file, so your toolbar favorites land
   on that browser's real toolbar (see [What push does](#what-push-does)). It
   does not change which favorites are included.
3. Enter the path for the output `.html` file.
4. Choose the database, as in pull.
5. Choose the source the file is for, usually the browser profile you are about
   to import it into. Pushing records what that source now has, so a favorite
   you later delete there is recognized as a deletion and not re-added.
6. In the browser, import the file with its bookmark manager's import option.

### Getting an export file from your browser

`befave` only reads and writes HTML files; it does not open, read or change
your browser's own bookmarks. Before a pull, export your bookmarks from the
browser's bookmark manager as an HTML file. After a push, import the file
`befave` wrote using the same bookmark manager. Importing adds to the browser's
existing bookmarks, so `befave` does not remove anything from the browser for
you: to delete a favorite everywhere, delete it in the browser, export again,
and pull.

Safari's export can be a `.zip`, which `befave` opens itself.

### Database

The default is `~/.befave/favorites.db`; use `--db` to choose
another file. One table, `bookmarks`, holds the URL, title, folder path, add
and last-modified dates, tags (Firefox) and the icon (base64 data). The other
tables (`sources`, `snapshots`, `source_items`, `tombstones`) track deletions.

### Using more than one computer

The database is a single file on one machine; `befave` does not sync over the
network. To share favorites between, say, a work and a home computer, keep the
database in a folder you already sync (Dropbox, iCloud Drive, a USB stick, etc.)
and point both computers at it with `--db`:

```
befave pull --db ~/Dropbox/favorites.db --source work-chrome bookmarks.html
befave push out.html --browser chrome --source work-chrome --db ~/Dropbox/favorites.db
```

Or copy `~/.befave/favorites.db` between machines. Use it from
one computer at a time, and let the sync finish before running `befave` on
another, so two copies don't diverge.

## What pull does

- **No duplicates.** URLs are compared after lowercasing the scheme and host,
  dropping the `#fragment`, and removing `utm_*` tracking parameters. The path
  and the rest of the query keep their case. The first URL processed wins,
  including across files and runs; the same URL in several folders is saved once.
- **Web links only.** Only `http`, `https` and `ftp` links are kept. Browser
  internals such as `chrome://`, `about:`, `javascript:`, `moz-extension://`,
  `place:` and `file://` are skipped.
- **Browser defaults are skipped.** Firefox's "Mozilla Firefox" folder (and its
  stray help/customize links) and the 12 links Safari ships in Favorites.
  The lists are `BUNDLED_FOLDERS` and `SAFARI_DEFAULTS` in `puller.py`.
- **Toolbar folders are normalized.** Chrome/Opera "Bookmarks Bar", Firefox
  "Bookmarks Toolbar" and Safari "Favorites" are all stored as `Bookmarks Bar`.

## Sources

A **source** is a name you give to one browser profile on one computer, such as
`work-chrome` or `home-firefox`. `befave` keeps a separate history for each
source, and asks which one you mean on every pull and push (or pass
`--source NAME`).

You need a separate source for each place favorites live, because each one holds
a different set of favorites. With a single shared history, a favorite that is
missing from one browser would look like something you deleted.

How a source behaves:

- Each pull is treated as that source's complete list of favorites.
- A favorite that was in the source's previous pull but is missing now counts as
  deleted (see [Deletions](#deletions)).
- A push records what that source now has, so a favorite you later delete in that
  browser is noticed.
- The first pull of a source never deletes anything.

### Example

Work Chrome has favorites A, B and C. Home Firefox has A, B and D.

1. Pull Chrome's export with `--source work-chrome`, then Firefox's with
   `--source home-firefox`. The database now has A, B, C and D. Nothing is
   deleted, because both were first pulls.
2. Later, you delete B in Chrome, export again, and pull with
   `--source work-chrome`. B was in that source's last pull and is gone now, so B
   is removed from the database.
3. Push for Firefox. The file leaves B out, and it has C, which Firefox didn't
   have before.
4. Pulling Firefox's export again as `home-firefox` does not delete C. C was never
   in that source's history, so it is not missing from it.

### Tips

- Always use exactly the same name for the same browser profile. A typo creates a
  new source with no history, so its deletions go unnoticed.
- The same browser on two computers needs two sources, for example `work-chrome`
  and `laptop-chrome`.
- Different profiles in one browser (for example two Chrome profiles) are also
  separate sources.

## Deletions

Each pull is treated as the full list of that source's favorites. A favorite
that was in the source's previous pull but is missing now counts as deleted
and is removed from the database, so it is no longer pushed to your other
browsers. A deleted favorite is not brought back by a pull of another source
that still has it.

Two safeguards ask for confirmation (`pull --yes` accepts them):

- **Mass deletion:** if more than 30% of a source's favorites (for sources with
  more than 10) are missing, it may be a partial export, such as a single folder.
- **Restoring:** a file contains a favorite that was deleted earlier and that
  source did not have in its last pull. Declining keeps it deleted.

The first pull of a source never deletes anything.

## What push does

Writes a Netscape-format HTML file with the folder hierarchy rebuilt. The
toolbar folder is named for the target browser (`--browser`):

| Browser       | Toolbar folder    |
|---------------|-------------------|
| chrome, opera | Bookmarks Bar     |
| firefox       | Bookmarks Toolbar |
| safari        | Favorites         |

The file has no wrapper folder. Other root folders sit beside the toolbar.

## Possible future feature: hosted sync

Today you share the database file yourself (see above). A paid hosted service
could do that for you: sign in, and your favorites sync between all your
computers and browsers without moving files around. This is only an idea and
nothing is built yet. If you would be interested, please get in touch at
pyguy411 (at) gmail (dot) com.

## Development

Example exports live in `example_formats/`, named after their browser. They
contain real bookmarks and are git-ignored: **never commit sample bookmarks or
test databases.**

```
uv run befave -h
uv build
```

## License

MIT. See [LICENSE](LICENSE). The software is provided "as is", without warranty of any kind.
