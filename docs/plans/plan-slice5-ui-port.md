# Plan: Slice 5, the tracker screens (US-05, US-11, US-03 totals)

Status: Approved 2026-10-29 (part 5a first)
Date: 2026-10-29
Source: `docs/requirements.md` US-03, US-05, US-11, `docs/workflows.md` US-04, US-05, US-11, `docs/architecture.md`
section 11 phase 5. The original HTML (`reference/html_original/html_original.html`, read only) was mapped by a
read-only agent; line numbers below are from that file.
Branch: `feature/slice5-ui-port` from `developer` (slices 1-4 merged).

## 1. Context and goal

Slices 1-4 have the data: joiners, roll-on dates, statuses, sync. The page is still the slice 1 test page. Slice 5
replaces it with the screens of the original tracker: sidebar, "All joiners" overview, and joiner page. They have the
same look and wording, and the US-05 fix makes the tiles follow the selected joiner.

The original computes everything in JS: statuses, KPIs, buckets, the attention list and date text. Here **all numbers
and all date text come from Python**. The page only draws and filters rows it was given. The only state the page holds
is UI state: the selected joiner, the tile/column/role/search filters, expanded rows, and "Status as of".

**Recommended: two PRs.**
- **5a: screen data in Python.** Pure rules plus the bridge, fully unit-tested, with no visible change.
- **5b: the HTML, CSS and JS.** A visual check needs a window (section 6).

This plan covers both, and each part ends with its own gate.

## 2. Out of scope (the original has these; v1 does not)

- **Editing** (US-11: read-only for checklist data): name, onboarding date chip as an inline field, status, completion
  date and remarks inputs (original lines 417-419, 476-480, 525-541). The roll-on date is still typed in the waiting
  list (slice 4), and the joiner page can change it (section 3.4).
- **Add new joiner, Import checklists, Save tracker file, Open saved file, Delete joiner** (lines 236-246, 515,
  547-651).
- **Exports and email drafts:** v1.1, US-12 (lines 801-960, 1070-1077).
- **The original's own folder sync, localStorage and IndexedDB** (lines 844-864, 963-1068).
- **The embedded 96-task template** (line 275, has real enterprise ids): never copied. Tasks come from each file
  (US-02).
- **Local import (US-13):** slice 6.

## 3. Design

### 3.1 New pure rules: `core/overview.py` (no clock; `as_of` passed in)
Same rules as the original, from the agent's map.
- **`bucket_of(days)`:**
  - `days < 0` -> `overdue`
  - `0` -> `today`
  - `<= 3` -> `soon`
  - `<= 7` -> `week`
  - otherwise `later`
- **Only open tasks** are bucketed: tracks Delayed and On Track.
- **`overview(joiners: [(name, id, roll_on, JoinerStatus)], as_of)`** returns:
  - **KPIs:**
    - Joiners: count.
    - Delayed tasks: sum of Delayed.
    - Due within 3 days: open tasks with days 0..3.
    - Average completed: round-half-up of the mean of each joiner's rounded percent, as in the original.
  - **Heatmap rows:** per joiner, the 5 bucket counts, the Done %, and the "since" value, i.e. days from roll-on to
    as-of. It gives the "day N" / "N days to go" sub-line.
  - **Needs attention:** every open task with days <= 0, sorted by days ascending. Ties keep joiner order, then file
    order.
- **US-03 (new rule, not in the original):** waiting joiners (no roll-on date) and hidden joiners are left out of all
  of the above. The original had no such joiners, because a date was always required.
- **`ladder(tasks, statuses, roll_on, as_of)`:**
  - columns = the distinct day offsets in *this file*, sorted;
  - squares in each column are sorted Delayed, On Track, Completed, Completed Late, N/A;
  - the as-of marker goes before the first column whose due date >= as_of.
  - Tasks with an unclear deadline go in one extra column at the end, "Deadline unclear".
- **`meter(status, total)`:** segment widths are count / total tasks, in the order Completed, Completed Late, On Track,
  Delayed. The original divided by 96; here the total is the file's own task count.

### 3.2 Display text: `services/screens.py` (presentation, plain dicts)
Builds the screen data from `JoinerService` and `core`, so the bridge stays thin.
- **Dates:** `dd Mon yyyy` (e.g. "05 Nov 2026") and short `d Mon` (e.g. "5 Nov"), in fixed English month names.
  Python gives "Sep". The original in Edge gave "Sept" for September (see section 8).
- **"Days to due" text:**
  - "3 left", "3 overdue", "Due today", "2 late" (Completed Late).
  - Class `neg` for overdue and late, `soon` for On Track with days <= 2.
- **Attention badge:**
  - "1 day late" / "N days late" with class Delayed.
  - "Today" with the amber class.
- **Banner:**
  - Delayed: "Delayed" + "N task is past deadline" / "N tasks are past deadline".
  - Otherwise: "On track" + "No open task is past its deadline".
  - Then " · {done} of {applicable} applicable tasks completed ({pct}%)".
- **Heatmap column date lines:**
  - "before 5 Nov"
  - "5 Nov"
  - "6-8 Nov" or "30 Oct-1 Nov" when it crosses a month
  - "after 12 Nov"
- **Owner column:** a Team Member task shows the joiner's name. Any other role shows the task's Assigned Enterprise Id
  when the file has one. The role is shown muted.
- **Task title and full text:** title = the first line of Description; "Full task" = the whole Description;
  "Guidelines" = the file's Guidelines column (3.3).
- **Skipped rows (US-05):** "N rows could not be read: no task number or description (rows 9, 14)."
- **File problem (US-09):** "File could not be read: {reason}, showing data from {dd Mon yyyy}".
- **Deadline warnings:** passed through from `core.status`.

### 3.3 `core/checklist.py`: read the Guidelines column
- Optional header "Guidelines" (the real file has it, requirements question 1). It becomes `Task.guidelines`, default
  `""`. This is a new field with a default, so existing Task tests still pass.

### 3.4 Bridge (needs your yes, section 7)
- **`overview(as_of)`** (new) returns the sidebar, KPIs, heatmap, column date lines and attention list.
- **`joiner(id, as_of)`** gains the banner, meter, tiles, ladder, task display fields, skipped-row text and problem
  text. The existing keys stay.
- **`joiners`, `set_roll_on`, `connect`, `sync_now`, `last_result`, `copy_report`:** unchanged.
- **Methods:** 8 in total.

### 3.5 Page: `ui/web/index.html`, `styles.css`, `app.js` (5b)
- **Layout:** the original's (272 px sidebar; one column below 860 px; overview grid 5fr/3fr).
  - **Colors:** its light and dark variables (dark via `prefers-color-scheme`).
  - **Font:** Segoe UI.
  - **Tile, badge, heatmap and ladder colors:** the same as the original.
  - **Footer:** "ACCENTURE CONFIDENTIAL".
- **Sidebar:**
  - brand
  - "All joiners" with the delayed total pill
  - "New joiners" list: "Roll-on dd Mon yyyy · N% done" + delayed pill
  - **new:** "Waiting for a roll-on date" list with a date box
  - **new:** the sync box from slices 1-3 (status, Sync now, Connect / Sign in again, last successful sync, skipped
    files, warnings, data note) and "Copy diagnostic report"
- **Overview:**
  - head with the "Status as of" chip and the actions menu, which has only "Reset status date to today"
  - KPI row
  - heatmap: a joiner name opens the joiner; a number opens it with that bucket filter
  - "Needs attention": 8, then "Show all N" / "Show fewer"
  - empty state: "No joiners yet. Joiners appear here after a sync."
- **Joiner page:**
  - "← Back to all joiners", name, the "Onboarding date" and "Status as of" chips, the actions menu
  - the menu has "Reset status date to today" and "Change roll-on date", which calls `set_roll_on`
  - banner + meter, five tiles, deadline ladder
  - search "Search tasks, owners, deadlines"
  - "All roles", "Clear filters", active-filter chips
  - task table with the original's 9 columns; the status, completed-on and remarks cells are text, not inputs
  - rows expand to "Full task" and "Guidelines"
  - skipped-row and file-problem lines above the table
- **US-05:**
  - a tile click filters to that track and a second click clears it;
  - switching joiner resets every filter and the expanded rows;
  - the tiles always come from `joiner(id, as_of)` for the selected id.
- **Filtering in the page:** search, role, tile, ladder column and bucket, ANDed, as in the original. It only hides
  rows by fields Python sent. No status is computed in the page.
- **"Status as of":**
  - held by the page, today by default (Assumption 7);
  - changing it re-asks Python for the sidebar and the current screen;
  - the refresh every 2 s only redraws when the data changed, so typing is not lost.
- **Safety:**
  - DOM built with `textContent` only, never `innerHTML` with data;
  - no inline scripts or styles, no external resources;
  - links in task text are shown as plain text, not clickable (section 8).

## 4. Files

| File | Change |
|---|---|
| `src/riro/core/overview.py` (new) | `bucket_of`, `overview`, `ladder`, `meter` (pure) |
| `src/riro/core/checklist.py`, `core/models.py` | optional Guidelines column -> `Task.guidelines` |
| `src/riro/store/codec.py` | store `guidelines` (old data without it loads as `""`) |
| `src/riro/services/screens.py` (new) | screen dicts and all display text (about 250 lines; split if needed) |
| `src/riro/ui/bridge.py` | `overview()`, richer `joiner()` |
| `src/riro/ui/web/index.html`, `styles.css`, `app.js` | the screens (5b); `app.js` split into a few files if over 300 lines |
| `tests/unit/test_overview_rules.py`, `test_ladder_meter.py`, `test_screens_text.py`, `test_screens_overview.py`, `test_bridge_screens.py` (new) | rules, text, waiting/hidden left out of totals, US-05 per-joiner counts |
| `tests/unit/test_checklist_guidelines.py` (new) | Guidelines column read, missing column -> "" |

## 5. Tests first

The `test-writer` writes them from US-03, US-05 and US-11 and the rules in 3.1 and 3.2. They are run red first. The
data is synthetic, with invented names. The page JS has no unit tests (no JS test runner is approved). It is kept to
drawing and filtering only.

## 6. Checks

- **5a:** `tools\check.ps1`, then the code-reviewer.
- **5b visual check:** this needs the app window, so **your yes is needed** (CLAUDE.md).
  - **Recommended:** a dev-only switch, `RIRO_DATA_DIR`, makes the app use a data folder in the scratchpad. That
    folder holds a synthetic `tracker.json` (two invented joiners, different statuses). The window opens with no
    Connect and no Edge.
  - You or I compare it side by side with the original HTML.
  - Pass: the US-11 layout, colors and wording, and US-05 (each joiner's tiles differ and the filter resets on switch).

## 7. Changes to existing tests and docs (your yes needed)

1. The bridge method set grows from 7 to 8 (`overview`) in `test_bridge.py` and `test_sync_summary_bridge.py`. The
   architecture text gets "8 bridge methods".
2. `test_bridge_joiners.py::test_us04_joiner_with_a_date_has_tiles_percent_warnings_and_tasks` compares the whole
   `joiner()` dict. It gains the new keys (banner, meter, ladder, task text fields), and the old keys keep their
   values.
3. ADR-012 says "the four bridge methods" in its context text. Recommended: leave it. The decision (the page server)
   is unchanged, and the method list is in `architecture.md`.

## 8. Defaults I took (change any with a `> NOTE:`)

1. Two PRs (5a data, 5b page).
2. Waiting and hidden joiners are left out of every total and of the heatmap and attention list. They still show in
   the sidebar: waiting joiners in their own list, hidden joiners nowhere.
3. Months use fixed English abbreviations, so September is "Sep", not the "Sept" Edge showed in the original.
4. The meter divides by the file's own task count (the original used 96).
5. Links in task text are plain text. Opening them would need a new bridge method that opens the system browser.
6. Task title = the first line of Description (the current template has no separate title column).
7. "Deadline unclear" tasks get their own last ladder column and their own track badge.
8. Joiner order: by name, the same as `JoinerService.views` (the original used file order).
9. A dev-only `RIRO_DATA_DIR` switch, only for the visual check; documented, off by default.
10. Added in 5a: "1 day to go" in the singular (the original always wrote "N days to go"); task rows also carry
    Remarks (the 9th column); `joiner()` says `hidden` so the page can go back to the overview when the last sync
    hid the selected joiner (US-10).

Note on section 7 item 2: the Bridge's `screens` part is optional, so the existing whole-dict test in
`test_bridge_joiners.py` did not need to change; the "screens given" case is tested in `test_bridge_screens.py`.

## 9. Risks

- Pixel-close matching of a 221-line stylesheet is subjective. The visual check is the gate, and differences are
  listed rather than chased forever.
- Large files (~100 tasks) times about 50 joiners means the overview call computes about 5,000 task statuses. That's
  cheap in Python, but the page must redraw only when the data changed.
