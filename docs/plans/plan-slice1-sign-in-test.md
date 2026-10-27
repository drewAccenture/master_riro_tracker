# Plan: Slice 1, the sign-in test and package

Status: Draft, notes addressed, waiting for approval
Date: 2026-10-27
Source: `docs/architecture.md` section 10 (first vertical slice) and section 11 phase 1. ADR-001, 002, 003, 006, 007,
009.

## 1. Goal

Prove on the PMO's laptop, with real code that stays, that:
1. The package installs by double-click without admin rights and a pywebview window opens (US-15, ADR-001, ADR-006).
2. Day 1: Connect opens Edge, she signs in, the Edge window closes by itself, and a sync lists the folder and reads
   the headers of one real file (US-01, Assumption 2).
3. Day 2, after a normal shutdown: the app syncs on start with no visible Edge window (US-08 target, Assumption 2).
4. Both days, "Copy diagnostic report" gives the maintainer the evidence, with nothing personal in it (US-16, ADR-007).

Before any of that: two guard tests that fix how pytest finds `src` and enforce the layer rules from now on.

## 2. Out of scope for this slice

- Task reading beyond headers and counts, deadlines, statuses (US-02, US-04). `core/deadlines.py`, `core/status.py`
  stay empty.
- The store and the data file (`store/*` stays empty). Nothing is remembered between starts except the Edge sign-in
  inside Edge's own profile. "Connected" is decided by trying a sync on start (`NeedsSignIn` means not connected).
- Joiners, roll-on dates, identity (US-03, ADR-005). `services/joiners.py` stays empty.
- The 5-minute timer (US-06). Slice 1 syncs on start and on "Sync now" only.
- Silent renewal tuning (US-08). Slice 1 measures it; the 45 s limit from ADR-003 is used as is.
- Tracker screens, look of the original (US-05, US-11). One plain page only.
- Local import (US-13), Disconnect (US-01 last criterion), upgrade keeping data (US-15 second criterion).

## 3. Tests written first (step 0, before any application code)

### 3.1 Import smoke test: `tests/unit/test_imports.py`

What it proves: every Python module under `src/riro/` imports cleanly under pytest, using the same path setup that
`tools\check.ps1` uses.

How pytest finds `src`:
- New `pyproject.toml` with only `[tool.pytest.ini_options]`: `pythonpath = ["src"]`, `testpaths = ["tests"]`.
  Built into pytest since 7.0, no plugin, no editable install, no `conftest.py` path hacks.
- No `[project]` or `[build-system]` table: the app is not pip-installed anywhere (ADR-006 copies `src\riro` into the
  embeddable runtime), and an editable install would need a build backend in the venv.

Discovery:
- Walk the file system: every `*.py` under `src/riro/` becomes a dotted name (`src/riro/core/status.py` ->
  `riro.core.status`). Not `pkgutil.walk_packages`: checked 2026-10-27, with no `__init__.py` files it finds only
  `riro.__main__` and misses the other 14 modules.
- Assert the discovered set contains the 15 modules listed in `docs/architecture.md` section 4 (plus any new ones),
  so a missing or renamed file fails, and an empty or wrong path cannot pass with zero modules.
- One parametrized case per module: `importlib.import_module(name)`, so a failure names the module.
- `riro.__main__` is imported too. `__main__.py` is the composition root (architecture section 5): wiring only, start-up
  inside `main()` behind `if __name__ == "__main__":`, nothing at top level that opens a window, starts Edge, starts a
  thread or touches `%LOCALAPPDATA%`. An unguarded start would hang the test; the 120 s pytest timeout in
  `tools\check.ps1` (ADR-008) would end it.

Red step: run it before `pyproject.toml` exists. Expected failure: `ModuleNotFoundError: No module named 'riro'`
(checked 2026-10-27: `.venv\Scripts\python.exe -c "import riro"` fails today). Then add `pyproject.toml`: green.

### 3.2 Dependency-rule test: `tests/unit/test_layers.py`

What it proves: no module imports a layer it may not use (`docs/architecture.md` section 5, as updated 2026-10-27).
Standard library `ast` and pytest only.

How it reads imports:
- Parse every `*.py` under `src/riro/` with `ast`. Collect `import x`, `from x import y` and relative imports
  (`from ..services import sync`, resolved against the module's own package). Imports inside functions and under
  `if TYPE_CHECKING:` count the same.
- `importlib.import_module("riro....")` and `__import__("riro....")` with a literal string count as imports. The same
  calls with a non-literal argument are reported as "cannot check" and fail.
- Only `riro.*` targets are checked. Standard library and third-party imports are ignored here (package rules belong
  to `docs/constraints.md` and review).

Layers (by the importing and the imported module's name):

| Layer | Modules |
|---|---|
| entry | `riro.__main__` |
| ui | `riro.ui.*` |
| services | `riro.services.*` |
| core | `riro.core.*` (`riro.core.models` is the only core module store may use) |
| store | `riro.store.*` |
| connectors | `riro.connectors.*` |

Allowed (anything else fails):

| From | May import |
|---|---|
| ui | ui, services |
| services | services, core, store, connectors |
| core | core |
| store | store, `riro.core.models` |
| connectors | connectors |
| entry | any layer |
| any | never `riro.__main__`, never the bare `riro` package, never a `riro.*` name outside the table |

The last row catches a new top-level folder (for example `riro/utils/`) that has no rule yet.

Failure message, one line per violation:
`src/riro/core/status.py:3: core imports riro.services.sync (core may import: core)`

Red step: the tree is empty today, so the real-tree test would pass with nothing to check. To prove the test works:
- The checker is a function `find_violations(root: Path) -> list[str]` inside the test file (test code, not app code).
- Synthetic trees are written to `tmp_path` (a few lines of Python each, so not in `tests/fixtures/`):
  core -> services (absolute), core -> services (relative `..`), store -> `riro.core.status`, ui -> core,
  connectors -> core, services -> `importlib.import_module("riro.ui.bridge")`, a dynamic non-literal import,
  services -> `riro.__main__`, and an unknown `riro.utils`. Each must give exactly one violation with file and line.
- Allowed cases (core.status -> core.deadlines, ui -> services, services -> connectors, store -> core.models,
  entry -> ui, entry -> store) must give none.
- First run with `find_violations` returning `[]`: the violation cases fail with "expected 1, got 0". Then implement
  the checker: green. The real-tree case then runs on every `tools\check.ps1` run.

### 3.3 DevTools port test (ADR-009): `tests/connector/test_edge_port.py`

Against a fake HTTP server (`http.server` in a thread on `127.0.0.1`) and a fake Edge launcher, with small injected
limits:
- answers with a valid `/json/version` -> returns its `webSocketDebuggerUrl`
- never answers -> after 3 attempts, job killed each time, `TimedOut` ("Edge could not be started"), total time within
  the injected limit
- answers, but `Browser` is not `Edg/...` or the websocket address is on another port -> counts as "port not ours",
  new port, next attempt
- port taken on the first attempt, free on the second -> success on attempt 2, launcher called twice with two ports
- no file under the fake profile folder is opened (the fake profile folder holds a `DevToolsActivePort` file that the
  test checks was never read, by making it unreadable or by watching `open`)

Note: `tools\check.ps1` runs `tests\unit` only. These run with the full suite, `.venv\Scripts\python.exe -m pytest -q`,
which the build step runs and pastes.

### 3.4 Other tests for this slice (written first, per story, by the test-writer subagent)

| Story / ADR | Test |
|---|---|
| constraints.md "Python" | dev venv minor equals 3.13 (`sys.version_info[:2] == (3, 13)`) |
| US-07, ADR-003 | each connector limit raises `TimedOut` against a fake transport that never answers (limits injected small) |
| US-07, ADR-003 | on time-out the Edge job is killed, and the next call starts a fresh Edge (fake Edge launcher) |
| US-07 | a second "Sync now" during a sync returns "Syncing..." at once and starts nothing |
| US-07 | each connector error maps to its plain-word message (`NeedsSignIn`, `NoAccess`, `NotFound`, `Unreachable`, `TimedOut`) |
| US-01 | sign-in not finished in 3 min, or window closed: plain-word "did not finish" result, nothing else changes |
| ADR-002 | every request the client sends is a GET to `ts.accenture.com/sites/WFR-USTEAM/`; anything else is refused |
| US-16, ADR-007 | known names, enterprise ids, a cookie, a token and a URL with a query string go through events; none reach the report or the log |
| US-16 | report holds versions, steps with durations, "file 1 of N", header names, distinct Deadline and Status values with counts |
| arch. section 10 | header check on a synthetic `.xlsx` in `tests/fixtures/`: sheet choice ("roll-in"/"rollin", else first), headers found and missing (any case), row count |

## 4. Files to create or change

Done while addressing the notes (2026-10-27, not committed):
- `docs/architecture.md` section 5: same-layer imports, new per-layer wording, `__main__.py` as composition root.
  Section 6 step 1: port chosen by the app (ADR-009) instead of `--remote-debugging-port=0`.
- `docs/adr/ADR-009-devtools-port.md` (new).
- `docs/requirements.md`: Status line only, "Approved 2026-10-27".

Build:

| File | Why |
|---|---|
| `pyproject.toml` (new) | pytest `pythonpath` and `testpaths` only (3.1) |
| `tests/unit/test_imports.py`, `tests/unit/test_layers.py` (new) | the two guard tests |
| `tests/connector/test_edge_port.py` (new) | ADR-009 test (3.3) |
| `tests/unit/test_*.py`, `tests/connector/test_*.py`, `tests/fixtures/*` (new) | tests in 3.4, synthetic only |
| `src/riro/connectors/sharepoint/errors.py` | the six error types |
| `src/riro/connectors/sharepoint/cdp.py` | DevTools client over `websocket-client`, every send has a time limit, transport injectable for tests |
| `src/riro/connectors/sharepoint/edge.py` | find `msedge.exe`, pick a free port, start visible or headless with the app profile, poll `/json/version` (ADR-009), Job Object through `ctypes`, kill |
| `src/riro/connectors/sharepoint/client.py` | `sign_in`, `list_files`, `download`, `renew`, health ping; GET only, host and site check |
| `src/riro/core/checklist.py` | header check only: bytes -> sheet name, headers found and missing, row count, distinct Deadline and Status values |
| `src/riro/core/models.py` | dataclasses for the file listing and the header report |
| `src/riro/services/sync.py` | minimal: connect, sync on start, Sync now, one sync at a time, plain-word errors |
| `src/riro/services/diagnostics.py` | allowed-field events, redaction on write, in-memory recent events, rotating log in `logs\` |
| `src/riro/ui/bridge.py` | `connect`, `sync_now`, `last_result`, `copy_report` |
| `src/riro/ui/web/index.html`, `app.js`, `styles.css` | one page: Connect, Sync now, last result, Copy diagnostic report |
| `src/riro/__main__.py` | `main()`: logging, data folder, services, window; wiring only, guarded |
| `tools/build_package.ps1`, `tools/package/install.bat`, `tools/package/uninstall.bat` | package per ADR-006 |
| `requirements.txt` (new) | exact versions of the runtime packages, read by `build_package.ps1` (constraints.md lock file) |
| `CLAUDE.md` | only if the "Run app" command still fails at the end (section 7, step 3) |

No `__init__.py` files: the tree stays as architecture section 4 lists it (namespace packages). The smoke test does
not need them.

## 5. Data flow (slice 1)

1. Start: `__main__.main()` sets up logging and `%LOCALAPPDATA%\RIROTracker\`, builds the connector and services,
   opens the window. Services try a sync at once.
2. Sync: `services/sync` -> `client` health ping (5 s) -> `list_files()` -> `download(id)` of the first `.xlsx`
   -> `core.checklist` header check -> result to diagnostics and to the bridge. `NeedsSignIn` -> page shows Connect.
3. Connect: page -> `bridge.connect()` -> `services/sync.connect()` -> `client.sign_in()` (visible Edge, 3 min) ->
   kill visible Edge, start headless -> sync as in step 2.
4. Edge start (any of the above): free port -> start Edge in the job -> poll `/json/version` -> websocket address.
   Up to 3 attempts in 30 s (ADR-003, ADR-009).
5. Report: page -> `bridge.copy_report()` -> `services/diagnostics` builds text -> page copies it to the clipboard
   and shows "Copied".

## 6. Acceptance criteria covered (from `docs/requirements.md`)

- US-01: "Not connected" plus Connect button with the folder filled in; Edge opens, window closes by itself once the
  folder is reached, "Connected", first sync starts; closed or 3 minutes: "did not finish", nothing else changes.
- US-07: Sync now starts at once or shows "Syncing..."; plain-word failure messages; never hangs; on time-out Edge is
  closed and the next sync starts clean. ("Last successful sync" needs the store: in memory only for this slice.)
- US-15: installs by double-click, no admin rights, no Python install, opens the app.
- US-16: one click copies the report and confirms; timestamps, steps, error reasons; never tokens, cookies, joiner
  names or enterprise ids.

## 7. End-to-end check

1. Maintainer's laptop: `powershell -File tools\build_package.ps1`, install from the zip, run Day 1 and Day 2 against
   the real folder. Paste both diagnostic reports.
2. PMO's laptop: the same Day 1 and Day 2 (architecture section 10). Pass = Day 2 syncs on start with no visible Edge.
   Day 1 fails: stop, US-13 becomes the main path, you decide. Day 2 fails: read the report before building more.
3. Last build step: run the CLAUDE.md "Run app" command `.venv\Scripts\python.exe -m riro` exactly as written and
   paste the result. It fails today (`No module named 'riro'`: `pyproject.toml` fixes the path for pytest only). If
   it still fails, remove that line from CLAUDE.md and say so. A way to make it work is a separate decision.

## 8. Decisions taken from the notes (2026-10-27)

1. Same-layer imports allowed; core -> core only; store -> store and `core.models`; connectors -> connectors only.
   Done in architecture section 5 and in the table in 3.2.
2. `__main__.py` is the composition root: any layer, wiring only, no import-time side effects, nothing imports it.
3. Edge port: chosen by the app, found through `/json/version`, at most 3 attempts. ADR-009. Nothing in the Edge
   profile is read.
4. `docs/requirements.md` approved 2026-10-27.
5. Runtime packages: all 11 from `docs/constraints.md`, exact pins, installed in `.venv` on 2026-10-27.
6. "Run app": must work after the build, or the line is removed (7.3).

## 9. Risks

- Policy blocks app-launched or headless Edge on her laptop (architecture section 9). That is what this slice tests.
- pythonnet or WebView2 fails inside the embeddable Python. Fallback in ADR-001, needs a new ADR.
- ADR-009: about 10 s per Edge start attempt is a guess. A slow first start of a fresh profile could use up an
  attempt. Slice 1 reports record each attempt.
- The AST test cannot see imports built from computed strings beyond the cases in 3.2, or `sys.modules` tricks.
  Review still checks those.
- The smoke test imports real modules, so the unit suite needs the runtime packages in `.venv`.
- `proxy-tools` 0.1.0 is sdist only (constraints.md). Installing it builds a wheel in pip's temporary build folder;
  that downloads a build backend for the build only, not into `.venv`.

## 10. Open questions

1. Answered 2026-10-27: all 11 runtime packages from `docs/constraints.md`, exact pins, installed in `.venv`.

Defaults taken where the notes said nothing (change any with a note):
2. No `__init__.py` files (was open question 3). Recommended before was to add them; the default here keeps the tree
   as architecture section 4 lists it.
3. Slice 1 keeps nothing on disk, "connected" = a sync on start works (was open question 4).
4. Lock file = `requirements.txt` with exact runtime pins; dev pins stay in constraints.md for now (was open
   question 5).
