# ADR-004: Storage = one JSON file with atomic saves

Status: Accepted
Date: 2026-10-26

## Context
The app must remember roll-on dates, the last good rows of each file, each file's ETag, hidden joiners, and recent
sync results. Data is small: at most about 50 files and a few thousand rows (well under a few MB). One user, one
process. Data must survive app upgrades (US-15). `store/` is the only layer that touches storage.

## Options in plain English

**(a) SQLite.** A small database in one file, built into Python. Safe against crashes by itself, can update one row at
a time, and handles many readers and writers. Costs: we write table definitions, SQL and migration steps, and the data
cannot be opened and read by hand without a tool.

**(b) JSON file with atomic saves.** The whole data is loaded into memory at start. On each change, the app writes it
to `tracker.json.tmp`, then replaces `tracker.json` in one step (`os.replace`), after copying the previous version to
`tracker.json.bak`. A `schema_version` field says which layout the file has; small Python functions upgrade older
layouts. One in-process lock makes sure only one save happens at a time. Costs: the whole file is rewritten on every
save, and it would get slow with much more data.

## Decision
Option (b), JSON. The data is small and has one writer, so SQLite's strengths (partial updates, many writers, large
data) are not needed. JSON means less code, no SQL, and a file the maintainer can read when debugging. Rewriting a few
MB every 5 minutes at most is cheap.

Rules:
- Files: `%LOCALAPPDATA%\RIROTracker\data\tracker.json` and `tracker.json.bak`.
- Save = write `.tmp`, flush to disk, copy current to `.bak`, `os.replace(.tmp, tracker.json)`. If Windows refuses the
  replace because antivirus holds the file, retry up to 5 times, 200 ms apart, then report the error. Old data stays.
- Load: `tracker.json`; if it is missing or broken, `tracker.json.bak`, and the app says so; if both fail, start empty
  and keep the broken file renamed with a date.
- Every save happens under one lock inside `store/datafile.py`. Only `store/` reads or writes these files.
- `schema_version` starts at 1. A newer app upgrades the file on load and keeps a copy of the old one first.

## Alternatives considered
SQLite (above). Revisit if the data grows past about 20 MB, or if a second process ever needs to write.

## Consequences
Simple to build and inspect. A crash during save loses at most the last change, never the file. Swapping to SQLite
later touches only `store/`.
