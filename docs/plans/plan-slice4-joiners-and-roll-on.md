# Plan: Slice 4, joiners and roll-on dates (US-02 joiner rules, US-03, US-10, ADR-005)

Status: Approved 2026-10-29
Date: 2026-10-29
Source: `docs/architecture.md` section 11 phase 4, `docs/workflows.md` US-02 (steps 4-5), US-03, US-04, US-10,
ADR-005 (joiner identity), ADR-004 (one atomic save per sync).
Branch `feature/slice4-joiners-and-roll-on` from `developer` after PR #3 (slice 3) was merged.

## 1. Context and goal

Slice 3 keeps one record per **file**. Slice 4 turns files into **joiners** and adds the roll-on date. That date is the
one thing the app keeps that cannot be rebuilt from SharePoint. The date is typed once and must stay with the right
person through owner-name corrections, renames, files leaving and coming back, and delete + re-upload (ADR-005).

After this slice, the services can answer:
- Who are the joiners?
- Who is waiting for a roll-on date?
- What is one joiner's status as of a given date?

The full tracker screens are still slice 5. This slice adds only a minimal list to the slice 1 page, so the date can
be typed and checked by hand.

## 2. Out of scope

- The tracker screens, tiles, sidebar and overview KPIs (US-05, US-11): slice 5. Totals across joiners: slice 5.
- Local import (US-13, keyed by normalized owner): slice 6.
- No new package, no ADR change. ADR-005 is followed as written.

## 3. Design

### 3.1 `core/models.py`
- `Joiner(id, file_id, name, owner_key, roll_on: date | None, hidden: bool, missing_syncs: int)`, frozen.
  - `id` is the joiner's own stable id. It is the UniqueId of the first file seen and never changes, so the page and
    the roll-on date stay attached to it.
  - `file_id` is the file the joiner reads now. It can move on a re-upload.
  - `missing_syncs` counts the syncs since the file left the folder (0 while present). It drives the "same sync or
    the next one" re-upload window.
- `JoinerView(joiner, checklist, status: JoinerStatus | None, problem, read_at)` for the bridge. `status` is None while
  the joiner is waiting for a date.

### 3.2 `services/joiners.py`: identity rules (pure function + small service)
`match_joiners(records, joiners) -> (joiners, warnings, moves)` runs inside each sync, before the one save:
1. **Normalized owner** (ADR-005): Checklist Owner trimmed, lower case, repeated spaces made single. An empty owner
   uses the file name without `.xlsx`, normalized the same way. Display name = the owner text, else the file name
   without `.xlsx`.
2. **Same file id** -> same joiner. The name and owner key are updated from the file, so an owner-name correction
   or a rename keeps the roll-on date (US-03).
3. **File left the folder** (`present = False`) -> joiner hidden, `missing_syncs + 1`, data and date kept (US-10).
   **Back** -> shown, `missing_syncs = 0`.
4. **Re-upload:** a present file with no joiner, whose owner key equals a hidden joiner's with `missing_syncs <= 1`
   (the same sync or the next one). The joiner's `file_id` moves to the new file and the date is kept. A `moves`
   count goes to diagnostics, never names (ADR-005).
5. **Same owner key in two present files** (US-02): one joiner, reading the most recently modified file
   (`TimeLastModified`). If one of the two already has a joiner with a roll-on date, that joiner is kept. The warning
   names both files: "Two files have the same Checklist Owner: A.xlsx and B.xlsx. Using B.xlsx (newest)." The other
   file has no joiner and is not counted.
6. A file never read (no checklist yet): no joiner until it has been read once.

`JoinerService(repo)`:
- `joiners()`
- `waiting()`: joiners with no date
- `joiner(id, as_of) -> JoinerView`
- `set_roll_on(id, text) -> (ok, message)`

Rules for these:
- `set_roll_on` accepts `yyyy-mm-dd` only (what `<input type="date">` sends). Anything else gives "Type the roll-on
  date as a date, for example 2026-11-02."
- It saves at once. A changed date shows in the next `joiner(...)` call (US-03 "update right away").
- Status always comes from `core.status.compute` (status rules only there).

### 3.3 `store/repo.py`
- A `joiners` section in the data file: `joiners()`, `set_roll_on(id, date)` (one save), and `apply(records,
  last_success, run, joiners=None)` (still one save per sync).
- `check_layout` also checks joiners.
- `schema_version` stays 1. Older files simply have no `joiners` key yet, so no upgrade step is needed (no real
  data file exists yet).

### 3.4 `services/sync.py`
- Before `repo.apply`, run `match_joiners(...)`. Its warnings are added to the summary after the skipped files.
- The diagnostics `sync` event gets `joiners_count`, `waiting_count`, `moved_count` and `duplicate_count`.
- The summary says "N joiners updated" (the US-07 wording) and no longer counts files, now that joiners exist. For
  example: "Sync OK: 12 joiners (3 updated, 9 unchanged)."

### 3.5 Bridge and page (minimal, needs your yes, section 7)
- New bridge methods:
  - `joiners()`: the list of `{id, name, roll_on, waiting, percent, delayed_count}`. Hidden joiners are
    left out.
  - `joiner(id, as_of)`: one joiner's tiles, percent, warnings and tasks.
  - `set_roll_on(id, date)`.
- Plain data only. `as_of` comes from the page (Assumption 7).
- The slice 1 page gets:
  - a "Waiting for a roll-on date" list, each with a date box and Confirm
  - a "Joiners" list showing name, roll-on date, percent and delayed count
- No other screens.

## 4. Files

| File | Change |
|---|---|
| `src/riro/core/models.py` | `Joiner`, `JoinerView` |
| `src/riro/services/joiners.py` | new content: `normalize_owner`, `match_joiners`, `JoinerService` (about 200 lines) |
| `src/riro/store/repo.py` | joiners section, `set_roll_on`, `apply(..., joiners)`; split into `repo.py` + `codec.py` (the JSON <-> dataclass functions) to stay under 300 |
| `src/riro/services/sync.py`, `sync_messages.py` | call `match_joiners`, joiner wording, warnings in the summary |
| `src/riro/services/diagnostics.py` | new count fields only |
| `src/riro/ui/bridge.py`, `ui/web/*` | 3 new methods, the two minimal lists |
| `src/riro/__main__.py` | wire `JoinerService` |
| `tests/unit/test_joiner_identity.py` (new) | each ADR-005 rule: correction, rename, hidden and back, re-upload in the same and next sync, too late = new joiner, duplicates |
| `tests/unit/test_joiner_service.py` (new) | waiting list, `set_roll_on` good and bad input, date survives sync and restart, status from `core.status` |
| `tests/unit/test_repo_joiners.py` (new) | round trip, one save per sync, `check_layout` |
| `tests/unit/test_bridge_joiners.py` (new) | the 3 methods, plain JSON data, hidden joiners not listed |
| existing tests | see section 7 |

## 5. Tests first

The `test-writer` writes them from US-02, US-03, US-10 and ADR-005, and they are run red first. They use synthetic
files and invented names only, with a fake connector and a repo on `tmp_path`.

## 6. End-to-end check (no Edge, no window)

Sync through `SyncService` with a fake folder and a real repo on `tmp_path`:
1. Two files appear. Both joiners are waiting.
2. A date is set for A.
3. A's owner text is corrected. A keeps the date.
4. A's file is deleted and re-uploaded with a new id in the next sync. Same joiner, date kept.
5. B's file leaves. B is hidden and comes back with its data.
6. A new `Repo` (an app restart) keeps all of it.

`joiner(A, as_of)` tiles match hand-computed counts. Then `tools\check.ps1` and the code-reviewer.

## 7. Changes to existing test assertions (your yes needed)

1. `test_bridge.py::test_page_sees_only_the_four_methods` and
   `test_sync_summary_bridge.py::test_page_still_sees_only_the_four_methods_with_auto_sync`: the allowed set grows to
   7 (`joiners`, `joiner`, `set_roll_on`). The architecture diagram's "the 4 bridge methods" is updated to 7 in the
   same change. Recommended: yes.
2. The slice 3 summary texts ("Sync OK: N files read (...)", "Sync partly worked: N of M files read...") change to
   the joiner wording in section 3.4. The tests in `test_sync_store.py`, `test_sync_summary.py` and
   `test_sync_more.py` that assert those texts change with it. Recommended: yes. US-07 says "how many joiners were
   updated", and slice 3 only counted files because joiners did not exist yet.

## 8. Defaults I took (change any with a `> NOTE:`)

1. The joiner id is the UniqueId of the first file seen, and it never changes.
2. Duplicate owners: the joiner that already has a roll-on date is kept, else the newest file's. The other file is
   named in the warning only.
3. The re-upload window is the same sync or the next one (ADR-005). Later = a new waiting joiner, as ADR-005 accepts.
4. A file that has never been read has no joiner. It shows up in the skipped list only.
5. `set_roll_on` takes `yyyy-mm-dd` only. A date can be changed later but not cleared, so a joiner never goes back to
   waiting.
6. No new `schema_version`: no real data file exists yet.

## 9. Risks

- Two different joiners with exactly the same name: treated as duplicates (newest wins, with a warning), as ADR-005
  accepts.
- `TimeLastModified` comes from the SharePoint listing as text. It is compared as ISO text, and a missing value
  counts as oldest.
