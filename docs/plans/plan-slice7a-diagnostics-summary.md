# Plan: Slice 7a, diagnostics summary (US-16, measures US-08)

Status: Approved 2026-10-30
Date: 2026-10-30
Source: `docs/architecture.md` section 11 phase 7, `docs/requirements.md` US-08 (target: about one visible sign-in
per working day, measured on the PMO's laptop) and US-16, ADR-007 (redaction at write time, allowed fields only).
Branch `feature/slice7-renewal-and-diagnostics` from `developer` after PR #7 (slice 6) was merged.

## 1. Context and goal

The report already has versions, the last 300 steps and the last file header check. It does not answer the two
questions the maintainer will ask first:
- How often did she have to sign in, and did silent renewal work? (US-08 target)
- Which syncs failed or skipped files, over more than the last few minutes?

7a adds three short summary sections at the top of the report. Renewal tuning (US-08, slice 7b) waits for the real
Day 1 / Day 2 run, which needs your yes.

## 2. Out of scope

- Any change to the 45 s renewal limit or the renewal steps (7b, after real data).
- New events in the connector. The existing `sign_in` and `renewal` events (with result and duration) are enough.
- No new package, no ADR change. ADR-007 is followed: summaries are built from our own numbers and fixed words.

## 3. Design

### 3.1 Sign-in summary (`services/diagnostics.py`)
- `Diagnostics.report()` gains "Sign-in summary (last 7 days):" first. One line per day that has events, newest first:
  `2026-10-30: visible sign-ins 1 (failed 0), silent renewals 3 (failed 1), longest renewal 12.4 s`
- Built from our own lines: the rotating log files in `logs\` when there is a log (so it survives restarts and
  covers several days), else the in-memory lines. Only lines in our format are counted (date, time, step, k=v);
  anything else is ignored. Days are counted from the date in each line; "last 7 days" ends at `now()`.
- The rest of the report is unchanged.

### 3.2 Extra sections from other services (`Diagnostics.add_section`)
- `add_section(title, lines_fn)`: `lines_fn()` returns a list of lines. Called inside `report()`. A section that
  raises shows "(not available)", so the report always copies.
- Wired in `__main__.py` with two functions in a new `services/report_sections.py`:
  - "Recent syncs (newest first):" from `repo.runs()`, up to 20:
    `2026-10-30 09:00 ok: files read 12, updated 2, unchanged 10, skipped 1`. Skipped file names are never shown,
    only their count.
  - "Data:" `joiners 12, waiting 2, hidden 1, imported 1`, plus the store's load note when it is one of the two
    fixed sentences in `store/datafile.py` (restored from backup, started empty). Counts only, no names.
- The bridge `copy_report()` is unchanged.

## 4. Tests first (test-writer, synthetic data only)
1. Sign-in summary counts `sign_in` and `renewal` ok / failed per day, the longest renewal, newest day first, days
   older than 7 are left out, no line for a day without events.
2. The summary reads the log files after a restart (a new Diagnostics on the same `logs\` folder) and ignores
   lines not in our format.
3. Without a log folder, it uses the in-memory lines; with no events it shows "(none)".
4. Recent syncs: newest first, at most 20, skipped shows a count, never a file name (feed synthetic names and check
   they are absent).
5. Data: counts of visible, waiting, hidden and imported joiners; the load note only when it is a known sentence.
6. A section function that raises gives "(not available)" and the rest of the report is still there.
7. Redaction (ADR-007): known names, ids and a token fed through records, joiners and events never reach the report.

## 5. Changes to existing tests
- None expected. If an existing test asserts the report's exact first lines, I will stop and ask.

## 6. Done when
- `tools\check.ps1` passes, code-reviewer run, Critical and High fixed test first.
- No window needed: the report is checked by tests. You can see it in the real run (7b).
