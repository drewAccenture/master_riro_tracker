# Plan: Slice 7b, sign-in window, page-load timing, build info (US-01, US-08, US-16)

Status: Approved 2026-10-30
Date: 2026-10-30
Source: the Day 1 real run (2026-10-30, two diagnostic reports), ADR-003 (visible sign-in 3 min), ADR-007.
Branch `feature/slice7b-sign-in-and-build-info` from `developer` after PR #8 (slice 7a) was merged.

## 1. What Day 1 showed

- 08:04:08 the visible Edge opened, 08:04:39 it was killed: the page-load wait inside the Edge start (30 s, PAGE_S)
  also applies to the visible sign-in. ADR-003 gives a visible sign-in 3 minutes, so this is a bug, not tuning.
- The headless folder page took 22 s to load on the good run (limit 30 s) and more than 30 s three times at 08:02.
  The report could not show this: a page load that times out is logged as `health_ping TimedOut`.
- The report says `app: 0.1.0` for every build, so she cannot tell which build she runs.

## 2. Out of scope

- Raising the 30 s headless page-load limit. That waits for the Day 2 numbers and needs a new ADR (ADR-003).
- Any change to silent renewal (45 s).

## 3. Design

### 3.1 Visible sign-in gets its full 3 minutes (`connectors/sharepoint/edge.py`, `client.py`)
- `EdgeStarter` gets `visible_page_s` (default 180 s, the ADR-003 sign-in limit). A visible start waits up to that
  for the first page; a headless start keeps `page_s` (30 s). The `start_edge(headless, url)` signature is unchanged.
- `SharePointClient.sign_in`: the Edge start moves inside the `try`, so a start that fails also writes the
  connector's `sign_in result=failed duration_s=...` line (the 7a summary already counts that pair once). The
  sign-in deadline stays `started + sign_in_s`, so the whole sign-in is still at most 3 minutes.

### 3.2 Page-load event (`edge.py`, `services/diagnostics.py`)
- `EdgeStarter` writes `page_load result=ok|failed duration_s=... error_kind=TimedOut|Unreachable` for every start,
  from `Page.navigate` until the page is loaded. No URL, no headless flag in free text.
- `page_load` is added to the allowed steps.

### 3.3 Version and build line
- `APP_VERSION` becomes `0.7.0` (matches the slice). The zip name follows it.
- `tools/build_package.ps1` writes `app\riro\build.txt` with one line: `<git short commit> <yyyy-mm-dd>`.
- `__main__.read_build(path) -> str`: the line if it matches `^[0-9a-f]{7,12} \d{4}-\d{2}-\d{2}$`, else
  "unknown"; no file (run from source) gives "source". The report shows `build: <that>` under `app:`.
- `build.txt` is in `.gitignore` (it is made by the build, never committed).

## 4. Tests first (test-writer)
1. A visible start whose page loads after more than `page_s` but within `visible_page_s` succeeds; a headless one
   with the same slow page times out as today.
2. A visible page that never loads ends at `visible_page_s` with TimedOut and Edge killed.
3. `sign_in` with a start that fails: one connector line with `duration_s`, then the service line; the summary
   counts 1 failed sign-in.
4. `page_load` events: ok with duration; failed with TimedOut; failed with Unreachable on a navigation error. The
   real Diagnostics keeps the step name `page_load`.
5. `read_build`: good line, missing file ("source"), junk or a name in the file ("unknown"), extra spaces trimmed.
6. `APP_VERSION == "0.7.0"`; the report shows `build:`.

## 5. Changes to existing tests
- None expected (no test asserts exact event lists or the version). If one does, I stop and ask.

## 6. Done when
- `tools\check.ps1` passes, code-reviewer run, Critical and High fixed test first.
- Real check after Day 2: you build 0.7.0, install, and the report shows `app: 0.7.0`, `build: ...` and
  `page_load` lines.
