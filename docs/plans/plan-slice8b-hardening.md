# Plan: Slice 8b, hardening from the real runs (US-06, US-07, US-15)

Status: Approved 2026-11-03 (with ADR-014 and ADR-015)
Date: 2026-11-03
Source: real reports of 2026-10-30 and 2026-11-03 (0.1.0 and 0.7.0), slice 8a review (Low and open Medium), ADR-003,
ADR-004, ADR-013. Branch `feature/slice8b-hardening` from `developer` after PR #11 (slice 8a) was merged.

## 1. What the real runs showed

- The hidden Edge's first page load: 22 s, >30 s (three times, 2026-10-30 08:02), ~6 s, >30 s then 7.9 s on the
  retry (2026-11-03 09:29). The 30 s limit cuts loads that would finish; on Day 1 the sync failed because of it.
- The first sync after the app opens failed twice in one day (03:51, and 09:26 right after the 0.7.0 install: Edge
  never answered, 3 x 10 s). Both times the next sync worked, but she waited 5-6 minutes for data.
- Slice 8a review: in read-only mode (ADR-013) the sync box says "Close other programs that may use it", which is
  wrong advice; an upgrade goes ahead even when its safety copy could not be written.

## 2. Out of scope

- Silent renewal (45 s), visible sign-in (3 min), Edge start (30 s), whole sync (3 min): unchanged.
- Any real data layout change.

## 3. Design

### 3.1 Hidden Edge page load 60 s (ADR-014, `connectors/sharepoint/edge.py`)
- `PAGE_S` 30 -> 60 s for the headless first page. One Edge start is then at most 30 + 60 s; the whole-sync limit
  (3 min) still ends any sync, so a sync never waits longer than today's worst case.

### 3.2 One early retry after a failed first sync (ADR-014, `services/autosync.py`, `__main__.py`)
- `AutoSync.start(first_delay_s=...)`. When the sync on app start fails (state "failed", any kind except a sign-in
  that expired), the first auto-sync runs after 60 s instead of 5 minutes. Later ticks stay at 5 minutes.
- "Sync now" is unchanged.

### 3.3 Read-only words (`store/`, `services/sync_messages.py`, `sync.py`, `joiners.py`, `local_import.py`)
- `DataFile.read_only` and `Repo.read_only` (properties, no file access).
- When the repo is read-only, a `SaveFailed` shows `READ_ONLY` = "Your data was saved by a newer version of the
  tracker. Install the newer version again; nothing was changed." instead of `SAVE_FAILED`. Same for a roll-on edit
  and an import.

### 3.4 No upgrade without its copy (`store/datafile.py`, ADR-015)
- If the `.v<n>-<time>` copy cannot be written in full (error, or no free name), the upgrade does not run: the file
  is opened read-only like a newer file, nothing is renamed, with the note `UPGRADE_NOT_SAFE` = "Your data could not
  be upgraded safely. Restart the PC and open the tracker again; nothing was changed." A half-written copy is deleted.
- The note also reaches the report (`report_sections._KNOWN_NOTES`).

### 3.5 Version
- `APP_VERSION = "0.9.0"`.

## 4. Tests first (test-writer)
1. Headless start: a page that loads after 45 s succeeds; one that never loads ends at 60 s, Edge killed. Visible
   start unchanged (180 s).
2. Whole sync with a never-loading page still ends by 3 minutes.
3. AutoSync: `first_delay_s` used once, then the interval; app start with a failed first sync uses 60 s; an ok first
   sync uses 5 minutes; "not_connected" starts nothing (as today).
4. Read-only: a sync, a roll-on edit and an import show `READ_ONLY`, never `SAVE_FAILED`; a normal `SaveFailed`
   still shows `SAVE_FAILED`.
5. Copy failure (open refused, write fails, all names taken): no step runs, file unchanged and not renamed, no
   partial copy left, read-only, note `UPGRADE_NOT_SAFE`, also in the report.
6. `APP_VERSION == "0.9.0"`.

## 5. Changes to existing tests
- `test_app_version.py` and `test_main_build_info.py` assert "0.8.0". Tests that pin `PAGE_S` == 30 or the old
  start deadline may exist. I list each one and ask before changing it.

## 6. Decisions for you
- ADR-014 "hidden Edge page load 60 s, one early retry 60 s after a failed first sync" (tunes ADR-003).
- ADR-015 "no upgrade without its safety copy" (adds to ADR-004 and ADR-013).

## 7. Done when
- `tools\check.ps1` passes, code-reviewer run, Critical and High fixed test first.
- Real check: install 0.9.0. The report shows `app: 0.9.0`; over a few days no sync fails on a `page_load` under
  60 s, and a failed first sync is followed by one about a minute later.
