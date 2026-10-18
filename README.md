# befave

Keep your favorites in sync across browsers. `befave` reads the bookmark export
from Chrome, Firefox, Safari or Opera, merges everything into one sqlite3
database with no duplicates, and writes it back out as a file any of those
browsers can import. Import and export can be repeated in cycles, so favorites
can round trip between browsers.

## Why

- Frustrated that the browser on your work computer doesn't have the same
  favorites as your home computer? Export from each, import both into `befave`,
  and export the merged set back to either one.
- Added new favorites in a new browser after you imported your favorites from
  another one? Export the new browser's bookmarks, import them (only the new
  ones are added), then export the full set to any browser.
- Switching browsers, or using several at once? Keep one master list and
  load it into whichever browser you pick up.

## Install

```
uv tool install befave   # once published
# or from a checkout
uv run befave
```

## Usage

Run `befave` and it asks what it needs to know. Anything you pass as an
argument is not asked again.

```
befave                      # asks: import or export?
befave import               # asks for the file(s) and database
befave import --db a.sqlite3 example_formats/firefox_bookmarks.html
befave export               # asks for the target browser, output file, database
befave export out.html --browser firefox --db a.sqlite3
```

When not run from a terminal, `befave` never prompts. It uses the default
database and fails with a message if something required is missing.

### Getting an export file from your browser

Use the browser's bookmark manager export (HTML). Safari's export can be a
`.zip`, which `befave` opens itself. The browser is detected by reading the
file, so you never say which one it came from.

### Database

The default is `~/.befave/favorites.db`; use `--db` to choose
another file. One table, `bookmarks`, holds the URL, title, folder path, add
and last-modified dates, tags (Firefox) and the icon (base64 data).

### Using more than one computer

The database is a single file on one machine; `befave` does not sync over the
network. To share favorites between, say, a work and a home computer, keep the
database in a folder you already sync (Dropbox, iCloud Drive, a USB stick, etc.)
and point both computers at it with `--db`:

```
befave import --db ~/Dropbox/favorites.db bookmarks.html
befave export out.html --browser chrome --db ~/Dropbox/favorites.db
```

Or copy `~/.befave/favorites.db` between machines. Use it from
one computer at a time, and let the sync finish before running `befave` on
another, so two copies don't diverge.

## What import does

- **No duplicates.** URLs are compared after lowercasing the scheme and host,
  dropping the `#fragment`, and removing `utm_*` tracking parameters. The path
  and the rest of the query keep their case. The first URL processed wins,
  including across files and runs; the same URL in several folders is saved once.
- **Web links only.** Only `http`, `https` and `ftp` links are kept. Browser
  internals such as `chrome://`, `about:`, `javascript:`, `moz-extension://`,
  `place:` and `file://` are skipped.
- **Browser defaults are skipped.** Firefox's "Mozilla Firefox" folder (and its
  stray help/customize links) and the 12 links Safari ships in Favorites.
  The lists are `BUNDLED_FOLDERS` and `SAFARI_DEFAULTS` in `importer.py`.
- **Toolbar folders are normalized.** Chrome/Opera "Bookmarks Bar", Firefox
  "Bookmarks Toolbar" and Safari "Favorites" are all stored as `Bookmarks Bar`.

## Known limitation: deletions

`befave` only adds. If you delete a favorite in one browser, it is not removed
from the database, so it comes back the next time you export and import
elsewhere. To get rid of one for good, delete it in every browser you use and
then delete the database (or start a new one with `--db`) and re-import. Proper
deletion handling is planned.

## What export does

Writes a Netscape-format HTML file with the folder hierarchy rebuilt. The
toolbar folder is named for the target browser (`--browser`):

| Browser | Toolbar folder |
|---|---|
| chrome, opera | Bookmarks Bar |
| firefox | Bookmarks Toolbar |
| safari | Favorites |

The file has no wrapper folder. Other root folders sit beside the toolbar.

## Possible future feature: hosted sync

Today you share the database file yourself (see above). A paid hosted service
could do that for you: sign in, and your favorites sync between all your
computers and browsers without moving files around. This is only an idea and
nothing is built yet. If you would be interested, please get in touch at
pyguy411@gmail.com.

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
