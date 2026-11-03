# ADR-015: No upgrade without its safety copy

Status: Accepted
Date: 2026-11-03

## Context
ADR-004 says a newer app upgrades the data file on load and keeps a copy of the old one first. Slice 8a writes that
copy, but if it cannot be written (disk full, no permission, every name taken) the upgrade still runs. After two
saves the old layout would then exist nowhere, so a faulty upgrade step could not be undone (US-15).

## Decision
- If the copy `tracker.json.v<n>-<time>` (or of `.bak`) cannot be written in full, no upgrade step runs. A half-written
  copy is deleted.
- The app opens read-only, like a file from a newer version (ADR-013): nothing is renamed or written, every save raises
  `SaveFailed`.
- The note says: "Your data could not be upgraded safely. Restart the PC and open the tracker again; nothing was
  changed." It is shown on the page and in the report.

## Alternatives considered
- Upgrade anyway (slice 8a): loses the safety copy without a word.
- Treat the file as broken: renames it and may start empty, which hides her data.

## Consequences
- In that rare state she sees no data until the copy can be written. Nothing is lost.
- Adds to ADR-004 and ADR-013; does not change them.
