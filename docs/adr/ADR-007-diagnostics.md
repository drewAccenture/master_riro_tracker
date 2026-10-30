# ADR-007: Diagnostics = one redacted event log and a copyable report

Status: Accepted
Date: 2026-10-26

## Context
US-16: the PMO copies a report with one click so the maintainer can find sync problems. It must never hold tokens,
cookies, joiner names or enterprise ids. Slice 1 depends on this report as its evidence.

## Decision
- Services and the connector write structured events (time, step, duration, result, error kind, counts) to
  `services/diagnostics.py`, which keeps the recent ones in memory and in a rotating log in `logs\`.
- Redaction happens when an event is written: events take only allowed fields (numbers, step names, error kinds,
  HTTP status codes, versions). Free text from files or from SharePoint is not accepted. URLs are logged without
  query strings and without the folder path.
- Files are called "file 1 of N", never by name (file names usually contain the joiner's name).
- Allowed template wording: column headers, the distinct Deadline texts and the distinct Completion Status values,
  with counts. Never names, ids, remarks or task descriptions.
- The report adds: app, Python, pywebview, renderer, WebView2 and Edge versions.
- A test feeds known names, ids, cookies and tokens through the system and checks that none reach the report or log.

## Alternatives considered
A plain text log with redaction by search and replace: easy to miss a case. Rejected.

## Consequences
Less detail than a free log, on purpose. A new field in the report needs a code change and a test.
