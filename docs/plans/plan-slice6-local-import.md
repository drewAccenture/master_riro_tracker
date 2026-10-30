# Plan: Slice 6, local import (US-13, ADR-005 local import rule)

Status: Approved 2026-10-30 (with section 5 test changes and no remove button)
Date: 2026-10-30
Source: `docs/architecture.md` section 11 phase 6, `docs/workflows.md` US-13, `docs/requirements.md` US-13,
ADR-005 (local import keyed by normalized owner, SharePoint wins, roll-on date kept), ADR-004 (one save).
Branch `feature/slice6-local-import` from `developer` after PR #6 (slice 5b) was merged.

## 1. Context and goal

US-13 lets the PMO add joiners from `.xlsx` files on her PC: before a file is in SharePoint, or as the fallback when
the Edge sign-in is blocked (she downloads the files herself). The same reading rules as US-02 apply, each file
becomes a joiner, and she types the roll-on date in the waiting list as in US-03. When the same joiner later shows
up in SharePoint, the SharePoint file wins and the roll-on date is kept.

## 2. Out of scope

- No "Add new joiner by hand" (US-13 says so).
- No folder import, no drag and drop. One file dialog, one or more files.
- No "remove an import" button. A replaced import is kept as data (present = False), like a file that left (US-10).
- No new package, no ADR change.

## 3. Design

### 3.1 Records for imports (`services/local_import.py`, new)
- An import is a `FileRecord` like a SharePoint one. Its id is `local-` + the first 12 hex of the SHA-256 of the
  normalized owner (ADR-005: keyed by normalized owner; no name in ids, so none can reach the diagnostics log).
  Importing the same owner again replaces that record (newer data, same joiner, date kept).
- `etag` is "", `modified` is the import time, `name` is the file's base name, `read_at` is the import time.
- `is_local(file_id)` helper: id starts with `local-`.
- `import_paths(paths, repo, diagnostics, now)`:
  - Per path: only `.xlsx` (else "not an .xlsx file"), at most 20 MB (else "is too large"), read bytes; a read error
    gives the US-09 reason `UNREADABLE`. Then `core.checklist.read`; missing headers give `not_a_checklist(...)`.
    These reuse the sync texts in `sync_files.py`.
  - A present SharePoint record with the same normalized owner: skipped with "is already in SharePoint. The
    SharePoint file is used." (SharePoint wins, US-13 criterion 2.)
  - Two picked files with the same owner: the last one wins, a duplicate warning like US-02.
  - Then `match_joiners(all records + new ones, repo.joiners())` and one save (`repo.save_import`, below).
  - Diagnostics event `local_import`: files_count, added_count, skipped_count, error kinds. Never names or paths.
  - Returns `ImportResult(added, updated, skipped: tuple[(name, reason)], warnings, message)`.

### 3.2 Sync keeps imports and replaces them (`sync_files.py`, `sync_apply.py`)
- `sync_folder`: a stored `local-` record is never marked "left the folder" (it is not in the listing by design).
- `sync_apply.read_folder`: before `match_joiners`, a pure `retire_replaced(records)` sets `present = False` on every
  local record whose normalized owner matches a present SharePoint record. `match_joiners` then moves the joiner to
  the SharePoint file through its existing "returning" rule, so the roll-on date is kept (ADR-005). No duplicate
  warning for that pair.
- The owner-key helper in `joiners.py` becomes public (`owner_key(record)`) so both use the same rule.

### 3.3 Store (`store/repo.py`)
- `save_import(records, joiners)`: one save, same roll-on protection as `apply`, but it does not touch
  `last_success` or `sync_runs` (an import is not a sync).

### 3.4 One thing at a time (`services/sync.py`)
- `SyncService.import_files(paths)` takes the same non-blocking lock as a sync. While a sync runs it returns at once
  with "A sync is running. Try the import again in a moment." So a sync never overwrites an import's joiners.

### 3.5 Bridge and page
- New bridge method `import_files()` (no arguments). Python opens the pywebview file dialog (multiple, `*.xlsx`), so
  the page never sends a path. Cancel returns `{"ok": true, "cancelled": true}`. Otherwise plain data:
  `ok, message, added, updated, skipped [{name, reason}], warnings`.
  - Difference from `docs/workflows.md` ("bridge import_files(paths)"): the dialog runs in Python. I update the doc.
- `joiner()` gains `"imported": bool`. The joiner page shows "Imported from this PC" under the head when true.
- Sidebar: an "Import checklist files" button under the sync box. It works with SharePoint off. The result message
  and skipped files show in the existing notice area. New joiners appear in the waiting list as today.
- `__main__.py`: wires a `pick_files` callable (window file dialog) into the bridge.

## 4. Tests first (test-writer, synthetic data only, `tests/unit/`)
1. A good `.xlsx` (built in code) becomes one waiting joiner; reading rules as US-02 (skipped rows kept).
2. Not `.xlsx`, too large, broken bytes, missing headers: skipped with the exact reason; nothing saved for them.
3. Re-import of the same owner replaces the record; the joiner and its roll-on date stay.
4. Owner already in SharePoint: skipped with the SharePoint-wins reason.
5. A sync keeps a local record present; a sync with a same-owner SharePoint file retires it, moves the joiner, keeps
   the date, and gives no duplicate warning.
6. A sync with no matching file leaves the import and its joiner visible.
7. Import while a sync runs: the "sync is running" message, nothing saved.
8. `save_import` keeps `last_success` and `sync_runs`; SaveFailed changes nothing and gives the save message.
9. Diagnostics `local_import` event has counts only: no file names, paths or owner text.
10. Bridge: cancel, a result, `imported` flag; the page sees nine methods.

## 5. Changes to existing tests (need your ok)
- `tests/unit/test_bridge_screens.py::test_page_sees_only_the_eight_methods_with_screens`: the expected set gains
  `"import_files"` (and the name says nine). Same change in any other test that lists the public methods.

## 5b. Review decisions (accepted 2026-10-30)
- A joiner already synced from SharePoint cannot be re-imported by hand ("already in SharePoint"), also when Edge
  stops working later. Its last synced data stays.
- An owner-name typo fixed and imported again gives a second joiner; no remove button for now.
- Re-importing an owner whose import was replaced (and whose SharePoint file left) counts as "updated".
- Diagnostics: the `local_import` event counts each skip reason, never names or paths.

## 6. Done when
- `tools\check.ps1` passes, code-reviewer run, Critical and High fixed test first.
- Visual check (your yes first): demo mode, import a synthetic `.xlsx` written by a small tool step, see it waiting,
  type a date, see it on the overview.
