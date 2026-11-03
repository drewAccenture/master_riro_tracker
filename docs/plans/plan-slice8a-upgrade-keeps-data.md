# Plan: Slice 8a, an upgrade keeps her data (US-15)

Status: Approved 2026-11-03 (with ADR-013 and the install test)
Date: 2026-11-03
Source: US-15 (second criterion), ADR-004 (schema_version, "a newer app upgrades the file on load and keeps a copy of
the old one first"), ADR-006 (install.bat never touches `data\`, `edge_profile\`, `logs\`). Day 2 real run passed.
Branch `feature/slice8a-upgrade-keeps-data` from `developer` after the 7b PR is merged. Hardening is slice 8b, own plan.

## 1. What is missing today

- `store/datafile.py` accepts only `schema_version == 1`. Any other number counts as a broken file: it is renamed
  `tracker.json.broken-<time>` and the app starts with no data. Not hit yet (every version so far writes 1), but:
  - the first layout change would hide all her data on upgrade (ADR-004 promises an upgrade step, none exists);
  - going back to `app.prev` after a newer version saved a higher number would do the same.
- `install.bat` has no automated test. "data, edge_profile and logs are never touched" is checked by hand only.

## 2. Out of scope

- Any real layout change. `SCHEMA_VERSION` stays 1; the upgrade path is built and tested with test-only steps.
- Hardening (slice 8b), uninstall changes, how the zip reaches her (open question 5).

## 3. Design

### 3.1 Upgrade on load (`store/datafile.py`)
- `UPGRADES: dict[int, Callable[[dict], dict]]`: step from version n to n+1. Empty for now. `DataFile` takes
  `schema_version=` and `upgrades=` so tests can pass their own.
- Older file: first a copy `tracker.json.v<n>-<yyyymmdd-HHMMSS>` (never overwritten), then the steps in order, then
  the layout check. The upgraded data is returned; it is written at the next normal save. A step that raises: the
  file counts as broken, as today (backup, then empty), and the copy stays.
- `.bak` is read the same way, so an older backup is upgraded too.

### 3.2 A file from a newer version (ADR-013)
- The file is not renamed and not overwritten. The app opens with that data if this version can read it, else empty,
  in read-only mode: every save raises `SaveFailed`, which the page already shows as a plain message.
- Load note: "Your data was saved by a newer version of the tracker. Install the newer version again; nothing was
  changed."

### 3.3 Install test (`tests/package/test_install_bat.py`, new)
- Runs `tools\package\install.bat` with `RIRO_INSTALL_TEST=1` and `LOCALAPPDATA` set to a pytest temp folder, on a
  synthetic package (a dummy `app\pythonw.exe` text file). No real app, no Edge, no shortcuts.
- Checks: `data\`, `edge_profile\`, `logs\` byte-for-byte unchanged; `app\` is the new one; the old one is `app.prev`;
  a second install replaces `app.prev`; a missing `pythonw.exe` changes nothing.

### 3.4 Version
- `APP_VERSION = "0.8.0"`.

## 4. Tests first (test-writer)
1. Older file with two test steps: copy made first, steps run in order, data returned, version now current.
2. A failing step: copy kept, file treated as broken (backup used), as today.
3. Older `.bak` with a broken main file: the backup is upgraded and used.
4. Newer file: not renamed, `save` raises `SaveFailed`, the note is shown, the file is byte-for-byte unchanged.
5. Current file: no copy made (no change to today).
6. Install test as in 3.3.

## 5. Changes to existing tests
- `test_datafile.py` may assert that another schema number gives an empty start. If so, I stop and ask.

## 6. Decisions for you
- ADR-013 "a data file from a newer version is opened read-only" (adds to ADR-004, does not change it).
- The install test runs `install.bat` (cmd and PowerShell, no app, no Edge) inside a pytest temp folder.

## 7. Done when
- `tools\check.ps1` passes, code-reviewer run, Critical and High fixed test first.
- Real check: she installs 0.8.0 over 0.7.0 and the report shows the same joiners and roll-on dates.
