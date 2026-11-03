# ADR-013: A data file from a newer version is opened read-only

Status: Accepted
Date: 2026-11-03

## Context
ADR-004 says a newer app upgrades an older data file on load. It does not say what an older app does with a file
that a newer one wrote (`schema_version` higher than it knows). That happens when she goes back to `app.prev` after
an upgrade. Today such a file counts as broken: it is renamed `.broken-<time>` and the app starts with no data, so
her roll-on dates disappear from view until someone renames the file back (US-15: an upgrade keeps her data).

## Decision
- A `tracker.json` (or `.bak`) whose `schema_version` is higher than this version knows is never renamed and never
  written.
- The app opens with that data if its layout check passes, else with no data, and in read-only mode: every save
  raises `SaveFailed`, which the services already report in plain words.
- The load note says: "Your data was saved by a newer version of the tracker. Install the newer version again;
  nothing was changed."

## Alternatives considered
- Treat it as broken (today): hides her data and makes the newer version start from the `.broken` copy by hand.
- Refuse to start: she cannot see anything, not even the note in the report.
- Read it and save in the old layout: silently drops whatever the newer version added.

## Consequences
- Syncs in that state fail with `SaveFailed` until the newer version is installed again. Nothing is lost.
- Adds to ADR-004; does not change it.
