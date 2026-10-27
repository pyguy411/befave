# Changelog

All notable changes to `befave` are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added

- `dump --profile NAME` writes only the favorites a profile holds. Repeat it to
  merge several profiles into one file. Interactive dumps offer the choice.

## [0.1.1] - 2026-10-26

### Added

- **Deletion tracking.** `befave` can now tell when a favorite you deleted in a
  browser should be deleted from the database too.
  - Every ingest is recorded as a run (UUID, profile, file names, time).
  - `ingest --track-deletions` (or the interactive question, asked only for a
    profile that was ingested before) lists the favorites that profile held but
    that are missing from the new file, with title, URL, folder, date added and
    where they were last seen.
  - You choose delete all, keep all, or decide one by one. Kept favorites are
    remembered as safe for that profile and are not asked about again.
  - Deleted favorites are flagged `deleted` and left out of dumps. Other profiles
    are not changed, and an ingest of a profile that still has the favorite does
    not bring it back.
  - `--yes` deletes every missing favorite without asking.
- `compare` command: shared and unique favorites between two profiles, or one
  profile and the whole database.
- Interactive ingest of several files offers to reuse the previous file's profile.
- A single `--profile` applies to every ingested file.
- Files given the same profile are ingested as one combined run.
- FAQ in the README about the "Imported" folder.

### Changed

- Terms: pull/push (earlier import/export) are now `ingest` and `dump`; "source"
  is now "profile".
- `dump` no longer asks for a profile and records nothing, so it never assumes a
  file was imported into a browser.
- Older databases are upgraded in place on first use, with a copy saved as
  `<database>.bak`.
- Browser-made top-level `Imported` wrapper folders are dropped on ingest and dump.

### Removed

- The 30% mass-deletion guard; the review step always asks first.
- `dump --profile`.

### Known limits

- The first ingest of a profile has nothing to compare, so it deletes nothing.
- A favorite deleted right after importing a dump is only noticed once that
  browser has been ingested once after the import.
