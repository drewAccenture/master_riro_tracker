# Plan: Slice 2, reading and rules (US-02, US-04)

Status: Approved 2026-10-29
Date: 2026-10-29
Source: `docs/architecture.md` section 11 phase 2, `docs/workflows.md` US-02 and US-04, original HTML `track()` and
`summarize()` (`reference/html_original/html_original.html` lines 302-326, read only).

## 1. Context and goal

Slice 1 proved the Edge path and reads headers only (`core/checklist.check_headers`). Slice 2 builds the pure rules
that turn one checklist file into tasks and statuses, so later slices (store, joiners, UI) have something to store
and draw. US-05's bug cause (a fixed 96-task list) goes away because tasks come from each file's own rows.

Everything is in `core/`: no files, no network, no clock. The date is passed in.

## 2. Out of scope

- `services/*`, `store/*`, `ui/*`, connectors: unchanged. `services/sync.py` keeps calling `check_headers` for the
  diagnostic report. Wiring `read()` into sync, the sync summary that names skipped files, and the store: slice 3.
- One joiner per file, empty owner -> file name, same owner in two files (newest wins): `services/joiners`, slice 4
  (ADR-005). Core only returns the owner text found in the file.
- Roll-on dates, waiting list, totals across joiners (KPI tiles, "Due within 3 days"): slices 4 and 5.
- No new package, no ADR change.

## 3. Design

### 3.1 `core/checklist.py`: `read(data: bytes) -> Checklist`
- Reuse the sheet choice (`_choose_sheet`), header matching (`_CANONICAL`) and `UnreadableFile` handling that exist
  now. `check_headers` and `read` share one private "open sheet + map columns" helper. `check_headers` behaviour
  stays the same (its tests guard it).
- Missing required headers: return `Checklist` with `headers_missing` filled and no tasks (not an exception).
  Unreadable bytes: `UnreadableFile`, as today.
- Per non-blank row after row 1 -> `Task`: task number (int-like floats as `"3"`, else trimmed text), role,
  description, deadline text, status, completion date, assigned enterprise id, remarks.
- Status: case-insensitive match to Not Started, In Progress, Completed, Not Applicable; anything else -> Not Started
  (US-02). The count of such rows is returned (`unknown_status_rows`) for the summary.
- Completion date: kept only when status is Completed (US-02). Excel date cell -> date (time dropped); text
  `yyyy-mm-dd` -> date; any other text -> no date and the row gets the note "completion date unclear".
- Skipped row (US-05 "never dropped without a message"): a non-blank row with both Task Number and Description empty.
  Returned as `SkippedRow(row_number, reason="no task number or description")`. Fully blank rows are ignored.
- Owner: the first non-empty Checklist Owner cell (raw text, trimmed). Empty -> `""`.

### 3.2 `core/deadlines.py`: `day_offset(text: str) -> int | None`
- `"On Roll On"` -> 0. `"N day(s) Before Roll On"` -> -N, `"N day(s) After Roll On"` -> +N. Any case, extra spaces,
  "Roll On" / "Roll-On" / "RollOn". All 11 texts in requirements section 8 table.
- Anything else (`"Day 0"`, empty, `"Never"`) -> `None` = "deadline unclear".

### 3.3 `core/status.py` (same rules as the HTML)
- `task_status(task, roll_on: date, as_of: date) -> TaskStatus(track, due, days)`:
  - Not Applicable -> `N/A`.
  - Completed: deadline known and completion date after due -> `Completed Late` (days = due - completed), else
    `Completed` (also when no date or deadline unclear).
  - Not Started / In Progress: deadline unclear -> `Deadline unclear`, due and days None. Else days = due - as_of;
    days < 0 -> `Delayed`, else `On Track`.
- `compute(tasks, roll_on, as_of) -> JoinerStatus` (name from `docs/workflows.md` US-04): one `TaskStatus` per task;
  counts for the five tiles plus `Deadline unclear`; applicable = tasks minus N/A; done = Completed + Completed Late;
  percent = round half up of done / applicable * 100 (HTML `Math.round`), 0 when applicable is 0; `delayed` flag and
  `delayed_count`; `warnings` = "N tasks have a deadline the app cannot read" when any task's Deadline text is
  unreadable, whatever its status (Completed and N/A included; decided 2026-10-29 after review).

### 3.4 `core/models.py`
New frozen dataclasses: `Task`, `SkippedRow`, `Checklist`, `TaskStatus`, `JoinerStatus`. `HeaderReport` unchanged.

## 4. Files

| File | Change |
|---|---|
| `src/riro/core/checklist.py` | add `read()`, shared private helper (about 190 lines total) |
| `src/riro/core/deadlines.py` | new content (empty today) |
| `src/riro/core/status.py` | new content (empty today) |
| `src/riro/core/models.py` | 5 dataclasses |
| `tests/unit/test_checklist_read.py` (new) | US-02 rows, statuses, dates, skipped rows, missing headers, owner |
| `tests/unit/test_deadlines.py` (new) | all table texts, variants, unclear cases |
| `tests/unit/test_status.py` (new) | each US-04 rule, boundaries (due == as_of is On Track, completed on due day is Completed) |
| `tests/unit/test_status_joiner.py` (new) | counts, percent, rounding, all N/A, delayed flag, warning |
| `tests/unit/test_read_to_status.py` (new) | end-to-end check (section 6) |
| `tests/conftest.py` | a `task_row(...)` helper for synthetic rows, if the tests need it |
| `docs/plans/plan-slice2-reading-and-rules.md` (new) | this plan |

## 5. Tests first

Written by the `test-writer` subagent from US-02 and US-04, run red (they fail on `ImportError` /
`AttributeError` first), then implementation until green. Synthetic data built in code with `build_xlsx`, invented
names only.

## 6. End-to-end check (core, no UI)

`test_read_to_status.py`: two synthetic files with different owners and statuses -> `read()` -> `compute()` with a
fixed roll-on and as-of date -> each joiner's tile counts and percent match hand-computed numbers and differ from
each other (the core half of US-05). Then `powershell -File tools\check.ps1`, output pasted, then the code-reviewer.

## 7. Defaults I took (change any with a `> NOTE:`)

1. Completion date as text: only `yyyy-mm-dd` is read. `dd/mm/yyyy` vs `mm/dd/yyyy` is ambiguous, so other text is
   "completion date unclear" and the task counts as Completed, not Late. One real file would settle it (requirements
   open question 1).
2. Completed with an unclear deadline -> `Completed` (lateness cannot be shown).
3. A row is skipped only when Task Number and Description are both empty.
4. Deadline-unclear open tasks stay in "applicable", so they lower the percent done.

## 8. Risks

- The October template's Deadline texts are still unknown (requirements open question 2). An unknown text gives
  "deadline unclear" and a warning, never a wrong status.
- Excel cells that look like dates but are stored as text in another format fall under default 1.
