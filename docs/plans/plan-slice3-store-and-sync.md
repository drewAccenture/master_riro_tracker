# Plan: Slice 3, store and full sync (US-06, US-07, US-09, US-10)

Status: Approved 2026-10-29
Date: 2026-10-29
Source: `docs/architecture.md` sections 7 and 11 phase 3, `docs/workflows.md` US-06, 07, 09, 10, ADR-003, ADR-004,
ADR-005 (file id = SharePoint UniqueId), ADR-007.

## 1. Context and goal

Slice 1 syncs and checks only the headers of the first file, and keeps nothing after the app closes. Slice 2 added
`core.checklist.read()` and `core.status`. Slice 3 makes sync read every checklist file in the folder and keep the
result on disk:
- Unchanged files (same ETag) are not downloaded again.
- A file that cannot be read keeps its last good data. A file that leaves the folder is hidden, not deleted.
- Each sync ends with a summary that names the skipped files and why.
- The sync runs on start and then every 5 minutes.

Everything is kept per **file** (by its SharePoint UniqueId). Turning files into joiners is slice 4 (owner, duplicates,
re-upload, roll-on dates). That slice will read what this slice stores.

## 2. Out of scope

- `services/joiners.py`, roll-on dates, waiting list, duplicate owners, re-upload matching (ADR-005): slice 4.
- The tracker screens (sidebar, tiles, joiner page) and "data changed" to the page: slice 5. The slice 1 page only
  shows the new summary lines.
- Silent renewal tuning (US-08) and the full diagnostics report: slice 7. Connector code: unchanged.
- No new package, no ADR change.

## 3. Design

### 3.1 `store/datafile.py`: ADR-004, as written
- `DataFile(path, *, now, replace=os.replace, sleep=time.sleep)`: `load() -> (dict, note)` and `save(dict)`.
- Save: write `tracker.json.tmp`, flush and `fsync`, copy the current file to `.bak`, then `os.replace`. If Windows
  refuses the replace, retry 5 times, 200 ms apart, then raise `SaveFailed`. The old file stays.
- Load: if `tracker.json` is missing, start empty. If it is broken, load `.bak` and return the note "data restored from
  backup". If both are broken, start empty, rename the broken file to `tracker.json.broken-YYYYMMDD-HHMMSS`, and
  return a note. `schema_version: 1`.
- One `threading.Lock` around load and save. `now` and `replace` can be passed in, so tests can control time and
  simulate a refused replace.

### 3.2 `store/repo.py`: the data, in plain dataclasses
- The layout stored per file id:
  - `name`, `etag`, `modified`, `present`
  - `checklist`: the last good `Checklist`, serialized with ISO dates
  - `read_at`: when that data was read
  - `problem`: None, or the reason of the last failed read
- Also stored: `last_success` (ISO), and `sync_runs`, the last 20 run records (time, result, counts, skipped files
  with reasons).
- `Repo(datafile)` with:
  - `file(id)`, `files()`, `last_success()`, `apply(sync_outcome)` (one save per sync), `add_run(record)`
  - `in_memory()`, for tests and for the existing sync tests that build `SyncService(connector, diagnostics)`.
- `store` imports `core.models` only (architecture section 5). The page and services never see the JSON layout.

### 3.3 `services/sync.py` + new `services/sync_files.py` (sync.py is 248 lines; split before it passes 300)
The lock, watchdog, ping and plain-word errors in `sync.py` stay as they are. Its body changes:
1. List the folder. Keep the `.xlsx` files.
2. For each file: same ETag as stored and stored data exists -> unchanged, no download. Otherwise download ->
   `read()`.
3. Per-file results (`sync_files.py`, pure apart from the connector call):
   - **updated**: new `Checklist`, new ETag, `problem` cleared.
   - **skipped, could not be read** (US-09): `UnreadableFile` or a per-file `NotFound`/`NoAccess` on download.
     Old data is kept, the ETag is not saved (so the next sync tries again), and `problem` is set to the reason.
   - **skipped, not a checklist**: missing required headers. Same handling; reason "missing headers: Role, Deadline".
   - **unchanged**.
4. Stored ids missing from the listing -> `present = False` (US-10). Back -> `present = True`. Data is never deleted.
5. One `repo.apply(...)` save. `last_success` changes only when the sync did not fail. A partial sync (some files
   skipped) still counts as a success.
6. `NeedsSignIn`, `Unreachable`, `TimedOut`, `EdgeMissing`, or going over the whole-sync limit fails the whole sync.
   Nothing is applied and the last good data stays. A failed-run record is still added.

Summary (`SyncResult` gets new fields: `updated`, `unchanged`, `skipped: tuple[(file name, reason)]`):
- All read: "Sync OK: 12 files read (3 updated, 9 unchanged)."
- Partial: "Sync partly worked: 10 of 12 files read. 2 files were skipped." The skipped list is shown below it with
  the file names. File names are shown on her own screen only. Diagnostics still say "file 2 of 12" (ADR-007).
- In slice 3, "joiners updated" (US-07) is counted as files. Slice 4 turns this into joiners.

Diagnostics:
- A `file_read` step with allowed counts only: `index`, `tasks_count`, `skipped_rows_count`,
  `unknown_status_count`, `result`, `error_kind` (`UnreadableFile`, `NotAChecklist`).
- `file_report` keeps showing file 1's header check (slice 1 behaviour, so the first real-file evidence stays).
- openpyxl's "Data Validation extension is not supported" warning is filtered at the `read()` call in services only,
  so it never shows in the log.

### 3.4 US-06 timer (`services/sync.py`)
- `AutoSync(service, interval_s=300, timer_factory=threading.Timer)`: `start()` after the start-up sync, then every 5
  minutes. A tick while a sync is running does nothing (the existing lock). It stops when the result is
  `not_connected` (US-08: auto-sync stops until she signs in). Connect starts it again. App exit cancels it.
- `__main__.py`:
  - Wire `DataFile(root/"data"/"tracker.json")`, `Repo` and `AutoSync`.
  - `last_success` is loaded from the store, so "Last successful sync" survives a restart.

### 3.5 Bridge and page (minimal)
- `_plain()` gets `updated`, `unchanged`, `skipped`. The existing keys stay, so the bridge tests stay.
- `app.js` shows the skipped list under the message. No other UI work.

## 4. Files

| File | Change |
|---|---|
| `src/riro/store/datafile.py` | new content: atomic save, .bak, lock, retries, load fallbacks (about 120 lines) |
| `src/riro/store/repo.py` | new content: file records, last success, runs, (de)serializing `Checklist` (about 180) |
| `src/riro/services/sync.py` | full-folder sync, summary, `AutoSync`, uses `Repo` (stays under 300) |
| `src/riro/services/sync_files.py` (new) | per-file decide / download / read / outcome, skipped reasons |
| `src/riro/services/diagnostics.py` | `file_read` step and `NotAChecklist` error kind in the allow lists |
| `src/riro/ui/bridge.py`, `src/riro/ui/web/app.js` | new summary fields, skipped list |
| `src/riro/__main__.py` | wire store and timer |
| `tests/unit/test_datafile.py`, `test_repo.py` (new) | ADR-004 rules, round trip of a `Checklist`, schema_version |
| `tests/unit/test_sync_files.py`, `test_sync_store.py` (new) | ETag skip, US-09, US-10, partial summary, failed sync keeps data |
| `tests/unit/test_autosync.py` (new) | start, every 5 min with a fake timer, stops on not_connected, cancel |
| `tests/unit/test_sync_more.py`, `test_sync_messages.py` | assertion changes, see section 7 (your yes needed) |
| `docs/plans/plan-slice3-store-and-sync.md` (new) | this plan |

## 5. Tests first

Written by the `test-writer` from US-06, 07, 09, 10 and ADR-004. They are run red first, then the code is written until
they pass. They use a fake connector and synthetic files built with `build_xlsx`. The store tests use `tmp_path`, never
`%LOCALAPPDATA%`.

## 6. End-to-end check (no Edge, no window)

`test_sync_store.py`: a fake folder with 3 synthetic files, a repo on `tmp_path`:
1. Sync 1: all read.
2. Sync 2: nothing downloaded.
3. Sync 3: file B is changed to broken bytes and file C is removed. B keeps its old data with a problem; C is
   `present=False`; the summary names B.
4. A new `Repo` on the same folder (an app restart) still has `last_success` and B's old data.

Then `tools\check.ps1`, then the code-reviewer.

## 7. Changes to existing test assertions (your yes needed, CLAUDE.md)

1. `test_sync_more.py::test_us07_unreadable_file_fails_in_plain_words_and_keeps_last_success` expects one unreadable
   file to fail the whole sync. US-09 says other files go on, so it becomes: state `ok`, the summary lists the file as
   skipped with the unreadable reason, and the old data is kept. Recommended: yes.
2. `test_sync_messages.py`: the `TimedOut` text goes back to the US-07 wording, "SharePoint did not answer in time. The
   app will try again in 5 minutes.", because the timer now exists (the slice 1 comment in `sync.py` says so).
   Recommended: yes.
3. `test_sync_service.py::test_us07_sync_ok_reads_first_xlsx_and_sets_last_success`: both `.xlsx` files (ids "2" and
   "3") are downloaded, not only the first. Everything else in the test stays.
4. `test_sync_service.py::test_us07_connector_error_gives_failed_with_plain_message`: the `download` + `NoAccess` /
   `NotFound` cases leave it (default 2: only that file is skipped) and are covered by the new tests. The other 13 cases
   stay.

All four approved 2026-10-29.

## 8. Defaults I took (change any with a `> NOTE:`)

1. Storage is per file, by UniqueId. Joiners come in slice 4 and read these records.
2. A per-file `NotFound`/`NoAccess` on download skips only that file. Sign-in, network, time-out and Edge errors fail
   the whole sync.
3. A partial sync updates "Last successful sync". Only a failed sync leaves it unchanged.
4. A file that is not a checklist (missing headers) keeps any old data, like an unreadable file. This covers a
   template that was broken by mistake.
5. Keep the last 20 sync-run records.
6. A store save failure (after the 5 retries) fails the sync with "Your data could not be saved. Close other programs
   that may use it and click Sync now." The old file stays.

## 9. Risks

- ~50 files on the first sync, each download limited to 30 s, against a 3-minute whole-sync limit. If the first sync
  takes too long, it is a reported time-out, and ETags make the next one fast. Slice 1 timings suggest well under 1 s
  per file.
- Antivirus holding `tracker.json` is covered by the ADR-004 retries. The `.bak` copy covers a broken save.
