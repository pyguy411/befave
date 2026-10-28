# befave

Keep your favorites in sync across browsers.
`befave` manages the bookmark files that browsers export.
It **never talks to a browser directly**: you export an HTML bookmarks file from the
browser yourself, and you import the file `befave` writes back into the browser
yourself. No browser profile, login or personal data is read, only the HTML file you
provide.

In between, `befave` keeps one sqlite3 database with no duplicates, and remembers what
you deleted. Think of it as a bucket for your favorites, with two commands:

- **`ingest`** feeds a browser’s exported HTML file into the bucket.
- **`dump`** pours the bucket out as an HTML file for a browser to import.

(Browsers call their steps “export” and “import”; `befave` uses its own words so the two
aren’t confused.) Ingest from as many browsers as you like, dump to any of them, and
repeat. Favorites round trip between Chrome, Firefox, Safari and Opera:

```
browser --(you export)--> bookmarks.html --(befave ingest)--> database
database --(befave dump)--> out.html --(you import)--> browser
```

## Why

- Frustrated that the browser on your work computer doesn’t have the same favorites as
  your home computer? Export from each browser, ingest both files into `befave`, dump the
  merged set, and import that file into either browser.
- Added new favorites in a new browser after you ingested your favorites from another
  one? Export the new browser’s bookmarks, ingest them (only the new ones are added),
  then dump the full set and import it into any browser.
- Switching browsers, or using several at once?
  Keep one master list and load it into whichever browser you pick up.

## Install

`befave` needs Python 3.9 or newer and has no other dependencies.
Install it with either of these:

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

To upgrade later, use `pip install --upgrade befave` (or `uv tool upgrade befave`).

## Usage

Run `befave` and it asks what it needs to know.
Most questions are numbered choices: type the number and press Enter.
Anything you pass as an argument is not asked again.

```
befave                      # asks: ingest, dump or compare?
befave ingest               # asks for the file(s), profile and database
befave ingest --db a.sqlite3 --profile home-firefox example_formats/0_firefox_bookmarks.html
befave dump                 # asks for the target browser, output file, database
befave dump out.html --browser firefox --db a.sqlite3
```

### Options

| Command | Argument or option | Meaning |
| --- | --- | --- |
| `ingest` | `FILE...` | Export file(s) or globs, `.html` or `.zip` |
| `ingest` | `--profile NAME` | Profile a file comes from; once per file, in order |
| `ingest` | `--db PATH` | Database file (default `~/.befave/favorites.db`) |
| `ingest` | `--track-deletions` | Review favorites missing since the profile’s last ingest |
| `ingest` | `--yes` | Delete all missing favorites and accept restores |
| `dump` | `OUTPUT` | Path of the `.html` file to write |
| `dump` | `--browser NAME` | `chrome`, `firefox`, `opera` or `safari` |
| `dump` | `--profile NAME` | Only favorites this profile holds; repeat to merge |
| `dump` | `--db PATH` | Database file (default `~/.befave/favorites.db`) |
| `compare` | `PROFILE [PROFILE]` | Two profiles, or one profile and the whole database |
| `compare` | `--common`, `--only-a`, `--only-b` | Print just that set of URLs |
| `query` | `--show-deleted` | List deleted favorites |
| `query` | `--profiles` | Profiles, favorites held, last ingest |
| `query` | `--history` | Ingest runs and their files |
| `query` | `--safe` | Favorites you chose to keep when asked about deleting |
| `query` | `--search TEXT` | Find favorites by title or URL |
| `query` | `--stats` | Totals (the default) |
| `query` | `--profile`, `--folder` | Filters (see [Querying](#querying-the-database)) |
| `query` | `--urls` | Bare URLs, for scripts |
| `query` | `--db PATH` | Database file (default `~/.befave/favorites.db`) |
| `compare` | `--db PATH` | Database file (default `~/.befave/favorites.db`) |

### Ingesting several files at once

`ingest` takes any number of files, and globs are expanded by `befave` itself (quote
them, or let your shell expand them, as on Windows where it won’t):

```
befave ingest example_formats/*
befave ingest --profile ff --profile safari --profile chrome --profile opera 'example_formats/*'
```

- **Order matters.** Files are ingested in name order, and when the same URL is in
  several files the first one wins (title, folder, dates).
  Name the files so the one you trust most sorts first, such as
  `0_firefox_bookmarks.html`. Uppercase names sort before lowercase ones, so
  `Safari_bookmarks.zip` comes before `chrome_bookmarks.html`.
- **One profile per file, or several files for one profile.** Interactively you are
  asked for each file’s profile in turn, with the option to reuse the previous file’s
  profile. In a script, give one `--profile` to use it for every file, or one per file in
  the same order as the files.
  Files given the same profile are ingested together as one combined list of that
  profile’s favorites, so none of them counts as deleting the favorites in another.
- A pattern that matches nothing is an error, and a file matched twice is ingested once.

### Scripts and cron jobs

When not run from a terminal, `befave` never prompts.
It uses the default database unless you pass `--db`, and exits with an error if a
required argument is missing: the file(s) for `ingest`, `--browser`, and the output file
for `dump`, and `--profile` for `ingest`. Without `--yes`, favorites that need a
deletion decision (see [Deletions](#deletions)) are left alone.

```
befave ingest --profile work-chrome --track-deletions --yes bookmarks.html
befave dump --browser chrome out.html
```

### Step by step

**Ingest**: read a browser’s exported bookmarks file into the database.

1. In your browser, export your bookmarks as an HTML file (see below).
2. Run `befave` and choose `1` (ingest), or run `befave ingest`.
3. Enter the path to the exported file (`.html` or `.zip`). You can give several files
   or a glob such as `exports/*`; see
   [Ingesting several files at once](#ingesting-several-files-at-once).
4. **Which database?** Choose `1` to use the default database (its path is shown), or
   `2` to type the path to a different one.
5. **Which profile is this?** A profile is a name you pick for the browser profile you
   exported from, such as `work-chrome`. befave reads no browser profile data.
   Pick an existing one from the list, or choose “Add a new profile” and type a name.
   Use the same name every time you ingest from that browser, because `befave` compares
   each ingest with the previous one to spot favorites you deleted.
   See [Profiles](#profiles).
6. If this profile was ingested before, you are asked whether to look for deleted
   favorites; see [Deletions](#deletions).

**Dump**: write the database out as a file a browser can import.

1. Run `befave` and choose `2` (dump), or run `befave dump`.
2. **Which browser will import this file?** Choose the browser.
   This only sets the name of the toolbar folder in the file, so your toolbar favorites
   land on that browser’s real toolbar (see [What dump does](#what-dump-does)). It does
   not change which favorites are included.
3. Enter the path for the output `.html` file.
4. Choose the database, as in ingest.
5. In the browser, import the file with its bookmark manager’s import option.

### Getting an export file from your browser

`befave` only reads and writes HTML files; it does not open, read or change your
browser’s own bookmarks.
Before an ingest, export your bookmarks from the browser’s bookmark manager as an HTML
file. After a dump, import the file `befave` wrote using the same bookmark manager.
Importing adds to the browser’s existing bookmarks, so `befave` does not remove anything
from the browser for you: to delete a favorite everywhere, delete it in the browser,
export again, and ingest.

Safari’s export can be a `.zip`, which `befave` opens itself.

### Database

The default is `~/.befave/favorites.db`; use `--db` to choose another file.
One table, `bookmarks`, holds the URL, title, folder path, add and last-modified dates,
tags (Firefox) and the icon (base64 data).
The other tables (`profiles`, `ingests`, `ingest_files`, `profile_bookmarks`,
`safe_urls`) record which profile held which favorite and which ingest last saw it.
A favorite you delete is kept in `bookmarks` with `deleted = 1`.

### Using more than one computer

The database is a single file on one machine; `befave` does not sync over the network.
To share favorites between, say, a work and a home computer, keep the database in a
folder you already sync (Dropbox, iCloud Drive, a USB stick, etc.)
and point both computers at it with `--db`:

```
befave ingest --db ~/Dropbox/favorites.db --profile work-chrome bookmarks.html
befave dump out.html --browser chrome --db ~/Dropbox/favorites.db
```

Or copy `~/.befave/favorites.db` between machines.
Use it from one computer at a time, and let the sync finish before running `befave` on
another, so two copies don’t diverge.

## What ingest does

- **No duplicates.** URLs are compared after lowercasing the scheme and host, dropping
  the `#fragment`, and removing `utm_*` tracking parameters.
  The path and the rest of the query keep their case.
  The first URL processed wins, including across files and runs; the same URL in several
  folders is saved once.
- **Web links only.** Only `http`, `https` and `ftp` links are kept.
  Browser internals such as `chrome://`, `about:`, `javascript:`, `moz-extension://`,
  `place:` and `file://` are skipped.
- **Browser defaults are skipped.** Firefox’s “Mozilla Firefox” folder (and its stray
  help/customize links) and the 12 links Safari ships in Favorites.
  The lists are `BUNDLED_FOLDERS` and `SAFARI_DEFAULTS` in `ingester.py`.
- **Toolbar folders are normalized.** Chrome/Opera “Bookmarks Bar”, Firefox “Bookmarks
  Toolbar” and Safari “Favorites” are all stored as `Bookmarks Bar`.
- **The “Imported” wrapper folder is dropped.** See the [FAQ](#faq).

## Profiles

A **profile** is just a label you choose for one browser profile on one computer, such
as `work-chrome` or `home-firefox`. `befave` never reads your browser profile, account,
passwords, history or sync data.
It only reads the exported bookmarks HTML file you give it, and the label has one
purpose: to let it know when a favorite should be deleted, by comparing each file with
what that profile held before.
`befave` keeps a separate history for each profile, and asks which one you mean on every
ingest (or pass `--profile NAME`).

You need a separate profile for each place favorites live, because each one holds a
different set of favorites.
With a single shared history, a favorite that is missing from one browser would look
like something you deleted.

How a profile behaves:

- Every ingest records which favorites that profile held, tracked or not.
- A tracked ingest compares the file with that record.
  Favorites that are missing now are offered for deletion (see [Deletions](#deletions)).
- Dumping records nothing.
  `befave` cannot know whether you imported the file.
- The first ingest of a profile never deletes anything.

### Example

Work Chrome has favorites A, B and C. Home Firefox has A, B and D.

1. Ingest Chrome’s export with `--profile work-chrome`, then Firefox’s with
   `--profile home-firefox`. The database now has A, B, C and D.
2. Later, you delete B in Chrome, export again, and ingest with
   `--profile work-chrome --track-deletions`. B was held by that profile and is gone
   from the file, so `befave` lists it and asks.
   If you choose delete, B is removed from the database and later dumps leave it out.
3. Dump the database for Firefox.
   The file leaves B out, and it has C, which Firefox didn’t have before.
4. Ingesting Firefox’s export again as `home-firefox` does not offer C for deletion,
   because that profile never held C.

### Tips

- Always use exactly the same name for the same browser profile.
  A typo creates a new profile with no history, so its deletions go unnoticed.
- The same browser on two computers needs two profiles, for example `work-chrome` and
  `laptop-chrome`.
- Different profiles in one browser (for example two Chrome profiles) are also separate
  profiles.

## Comparing profiles

```
befave compare work-chrome home-firefox   # shared, only in work, only in home
befave compare work-chrome                # work-chrome against the whole database
befave compare a b --common               # bare URLs, for scripts
```

`compare` may upgrade an old database (see [Deletions](#deletions)) but never changes
favorites. It uses what each profile held at its ingests, meaning the favorites in the
export files you gave `befave`. A dump does not count: `befave` cannot know whether you
imported the file, so if you want to see what a browser really holds, export a new file
from it and ingest it.
Comparing one profile with the database shows what a dump would add to that browser.

## Querying the database

```
befave query --show-deleted               # what was deleted, and when
befave query --profiles                   # favorites held per profile
befave query --history --profile work-chrome
befave query --search django --folder dev
befave query --show-deleted --urls        # bare URLs for scripts
```

`query` only reads the database.
Pick one view per run; with none, a terminal asks which you want and a script gets
`--stats`. `--profile` filters `--history`, `--safe` and `--search`. It cannot be used
with `--show-deleted`, because the database does not record which profile a deletion
came from. `--urls` works with `--show-deleted`, `--safe` and `--search`.

## Deletions

Deletion tracking is optional and only matters if you want favorites you delete in a
browser to disappear from the database too.
It works by asking you.

1. Every ingest records a run (a UUID, the profile, the file names and the time) and
   marks each favorite the file contains with that run.
2. When you ingest a profile that has been ingested before, `befave` asks: “Has this
   profile been ingested before and do you want to check for deleted favorites?”
   (or pass `--track-deletions`). Answer No to just add favorites.
3. At the end of a tracked run, favorites that profile held but that are not in the file
   are listed with their title, URL, folder, date added and the file and date they were
   last seen in. You choose delete all, keep all, or decide one by one.
4. A deleted favorite is flagged `deleted` in the database and left out of dumps.
   Other profiles are not changed, and an ingest of another profile that still has it
   does not bring it back.
5. A favorite you keep is remembered as safe for that profile, so you are not asked
   about it again.

`--yes` deletes every missing favorite without asking.
Without a terminal and without `--yes`, missing favorites are left alone.

**Restoring:** a file contains a favorite that was deleted earlier and that the profile
did not hold. You are asked whether to restore it (`--yes` restores).

**Limit:** the first ingest of a profile has nothing to compare, and a favorite deleted
in a browser right after importing a dump is only noticed once that browser has been
ingested once after the import.

**Upgrading:** a database from an older version is upgraded in place the next time it is
opened, and a copy is saved as `<database>.bak`.

## What dump does

By default the file has every favorite in the database.
With `--profile NAME` it has only the favorites that profile held at its last ingest,
minus any you deleted.
Repeat the option to merge several profiles into one file, for example a work and a
personal profile:

```
befave dump out.html --browser chrome --profile work-chrome --profile home-chrome
```

An unknown profile name is an error.

The database stores each normalized URL once, even if several profiles hold it.
So a dump without `--profile` includes that URL once, not once per profile.
Its saved title, folder and other bookmark details come from the first ingest that added
it to the database; later ingests from other profiles do not replace them.
With `--profile`, the URL appears in each dump for a profile that holds it.

Writes a Netscape-format HTML file with the folder hierarchy rebuilt.
The toolbar folder is named for the target browser (`--browser`):

| Browser | Toolbar folder |
| --- | --- |
| chrome, opera | Bookmarks Bar |
| firefox | Bookmarks Toolbar |
| safari | Favorites |

The file has no wrapper folder.
Other root folders sit beside the toolbar.

## FAQ

### Why is there an “Imported” folder in my browser after I import a dump?

Some browsers, Opera in particular, put everything they import from a bookmarks file
into a new `Imported` folder instead of merging it with what you already have.
If you ingest that browser’s export later, the `Imported` folder is part of the file,
and it would be dumped back out and wrapped again on the next import.

To stop this, `befave` removes a top-level `Imported` folder when it ingests and when it
dumps. Its contents move up one level, for example `Bookmarks Bar/Imported/work` becomes
`Bookmarks Bar/work`, so the database and every dump keep your own folder layout.

- Only the browser-made folder is removed: the one directly under the toolbar or at the
  root. An `Imported` folder deeper in the tree is kept.
- If you named a top-level folder `Imported` yourself, it is flattened too, because the
  file cannot show who created it.
  Rename it to avoid this.
- Bookmarks already in the database are cleaned when you dump, so a new dump has no
  wrapper even if the database was filled before this change.
- Delete the `Imported` folder in the browser after checking that everything came
  across, or it stays there as a duplicate copy.

## Possible future feature: hosted sync

Today you share the database file yourself (see above).
A paid hosted service could do that for you: sign in, and your favorites sync between
all your computers and browsers without moving files around.
This is only an idea and nothing is built yet.
If you would be interested, please get in touch at pyguy411 (at) gmail (dot) com.

## Development

Example exports live in `example_formats/`, named after their browser.
They contain real bookmarks and are git-ignored: **never commit sample bookmarks or test
databases.**

```
uv run befave -h
uv build
```

## License

MIT. See [LICENSE](LICENSE). The software is provided “as is”, without warranty of any
kind.
