# Master RIRO Tracker: Architecture (version 1)

Status: Accepted
Date: 2026-10-26
Source: `docs/requirements.md`. Decisions: `docs/adr/`. Stack and limits: `docs/constraints.md`.

## 1. In one paragraph

One Python program on the PMO's laptop. It shows the tracker in a desktop window (pywebview, HTML and CSS with the
look of the original). Behind it, a small sync service reads the SharePoint folder through a copy of Microsoft Edge
that the app starts and owns, with its own profile. Checklist files are turned into joiners and tasks by pure Python
rules. Everything the app must remember (roll-on dates, last good data, file versions) is kept in one JSON file in the
PMO's user folder.

## 2. Diagram

```
 +-------------------------------- RIRO Tracker (one Python process) --------------------------------+
 |                                                                                                  |
 |  UI: pywebview window (HTML/CSS/JS, look of the original)                                        |
 |        |  calls Python through one JS function: api.call(name, args)                            |
 |        v                                                                                         |
 |  ui/bridge.py   thin: turns UI calls into service calls, returns plain data                      |
 |        |                                                                                         |
 |        v                                                                                         |
 |  services/   sync (timer, one sync at a time, summary)   joiners (roll-on dates)   diagnostics    |
 |        |                     |                                   |                               |
 |        v                     v                                   v                               |
 |  core/ (pure rules, no I/O)  connectors/sharepoint/              store/ (the only layer that      |
 |   checklist reading,         Edge process + DevTools +            touches the data file)          |
 |   deadlines, status          SharePoint REST calls                                               |
 +------------------------------------|-------------------------------------------------------------+
                                      v
                       msedge.exe (app's own profile)  --->  SharePoint Online (ts.accenture.com), GET only
```

## 3. Layers and why each exists

| Layer | Folder | Job | Why it exists |
|---|---|---|---|
| UI | `src/riro/ui/web/` | Draws screens, sends clicks to Python, shows what Python returns | Keeps the original look. Holds no business rules |
| Bridge | `src/riro/ui/bridge.py` | The list of things the page may ask for | One small door between page and Python. Swapping pywebview for the fallback (ADR-001) changes only this file |
| Services | `src/riro/services/` | Runs the steps of a feature: sync, roll-on dates, diagnostics | The place where order and timing live (timer, one sync at a time, what to keep on failure) |
| Core | `src/riro/core/` | Reads a checklist, turns deadline text into days, computes statuses | Pure rules, no files, no network, no clock (the date is passed in). Easiest to test |
| SharePoint connector | `src/riro/connectors/sharepoint/` | Starts and kills Edge, signs in, lists the folder, downloads files | External system behind one interface. Knows nothing about joiners |
| Store | `src/riro/store/` | Loads and saves the data file safely | Only layer that touches storage (ADR-004) |

Layers dropped on purpose:
- No web server and no HTTP API: pywebview calls Python directly.
- No database server or ORM: the data is small (ADR-004).
- No cache layers: the store keeps each file's ETag and its last good rows. Nothing else.
- No built-in task template: each file is the truth for its own tasks (US-02).

## 4. Folder tree

```
src/riro/
  __main__.py             start: logging, data folder, window, sync service
  ui/
    bridge.py             methods the page can call
    web/                  index.html, styles.css, app.js (look of the original HTML)
  services/
    sync.py               timer (at start, then every 5 min), one sync at a time, summary, plain-word errors
    joiners.py            roll-on dates, waiting list, hidden and returning joiners, identity rules (ADR-005)
    diagnostics.py        redacted event log, "Copy diagnostic report" (ADR-007)
  core/
    checklist.py          xlsx bytes -> rows + skipped rows with reasons (openpyxl)
    deadlines.py          "10 days Before Roll On" -> -10, otherwise "deadline unclear"
    status.py             task and joiner status, tile counts, percent done
    models.py             plain dataclasses shared by all layers
  connectors/sharepoint/
    edge.py               start Edge (visible or headless), Job Object, kill
    cdp.py                small DevTools client: send a command, wait with a time limit
    client.py             sign_in, list_files, download, renew
    errors.py             NeedsSignIn, NoAccess, NotFound, Unreachable, TimedOut, EdgeMissing
  store/
    datafile.py           atomic save, .bak copy, lock, schema_version and upgrades
    repo.py               read and change joiners, tasks, files, roll-on dates, sync runs
tests/
  unit/                   core rules, store, services with a fake connector
  connector/              client.py against a fake DevTools endpoint; one opt-in live test
  fixtures/               synthetic checklists only (no real files in git)
tools/
  build_package.ps1       embeddable Python + packages + src -> dist\RIROTracker_<version>.zip
  package/                install.bat, uninstall.bat
docs/
  requirements.md  architecture.md  constraints.md  workflows.md  glossary.md  adr/
```

Rule: a file over about 300 lines is split.

## 5. Dependency rules (who may call whom)

```
ui  ->  services  ->  core
                  ->  store       ->  core.models
                  ->  connectors  (own error types only)
```

- Imports inside the same layer are allowed.
- `ui` imports `ui` and `services` only.
- `services` may import `services`, `core`, `store` and `connectors`.
- `core` imports `core` only.
- `store` imports `store` and `core.models` only.
- `connectors` import `connectors` only. They return plain data (file id, name, ETag, modified, size, bytes).
- `__main__.py` is the composition root: it may import any layer and holds wiring only, with no side effects at
  import time. Nothing imports `riro.__main__`.
- Nothing calls upward. Services see the connector through a small interface (`list_files()`, `download(id)`), so
  tests use a fake, and local import (US-13) feeds the same reading path.
- Status rules exist only in `core/status.py`. The page never recomputes them.

## 6. The SharePoint connector (ADR-002, ADR-003)

1. **Edge is owned by the app.** `edge.py` starts `msedge.exe` with `--user-data-dir=%LOCALAPPDATA%\RIROTracker\edge_profile`
   and `--remote-debugging-port=<port>`, a free port the app picks and then finds through `/json/version` (ADR-009).
   Python keeps the process handle and puts the process in a Windows Job Object.
   Killing the job ends Edge and all its child processes at once. If the app exits or crashes, Windows ends the job.
2. **Sign-in (US-01).** Edge starts visible on the folder page. The PMO signs in (SSO, MFA). When the page URL is on
   the site and not a sign-in page, the app kills the visible Edge and starts a headless one on the same profile.
   Limit 3 minutes.
3. **Reading.** A headless page sits on the SharePoint site. Each call runs `fetch()` inside that page with
   `redirect: "manual"`. Cookies stay inside Edge. Our code never reads, copies or logs them.
   - List: `GetFolderByServerRelativePath(...)/Files?$select=Name,UniqueId,ETag,TimeLastModified,Length`
   - Download, only when the ETag changed: `GetFileById('<UniqueId>')/$value`, returned as base64 (files are under 10 MB)
4. **Expired sign-in (US-08).** A 401 or a redirect means expired. The page goes to the folder page once. If it is back
   on the site within 45 s, the call is retried once. Otherwise: "Sign in again", auto-sync stops.
5. **Never stuck (US-07).** Health ping before each sync (5 s). Every call has a limit (ADR-003). On any time-out the
   job is killed. Nobody waits on a lock: one sync worker, and "Sync now" during a sync only shows "Syncing...".
6. **Kept open while the app runs.** Edge is started about once per app start, not once per sync.

Why this will not fail like the first attempt: see ADR-002.

## 7. Example flow: US-06 automatic sync

1. The timer in `services/sync.py` fires (or app start, or Sync now). If a sync is running, nothing happens.
2. Health ping to Edge. No answer in 5 s: kill the job, start headless Edge again.
3. `client.list_files()` returns id, name, ETag, modified time and size for each `.xlsx`.
   Expired sign-in: silent renewal (45 s), retry once, or stop with "Sign in again".
4. For each file whose ETag differs from the one in the store: `client.download(id)` returns bytes.
5. `core.checklist.read(bytes)` returns rows and skipped rows. A file that cannot be read keeps its last good data,
   with the reason (US-09). Other files go on.
6. `services/joiners.py` matches files to joiners (ADR-005). Files gone from the folder: joiner hidden (US-10).
7. `store` saves everything in one atomic write. "Last successful sync" changes only if the sync succeeded.
8. The bridge tells the page "data changed". The page asks for the selected joiner. `core.status` computes the tiles
   from that joiner's own tasks and roll-on date (US-04, US-05).

## 8. Where the app keeps things

```
%LOCALAPPDATA%\RIROTracker\
  app\            code and embedded Python (replaced on upgrade)
  data\           tracker.json, tracker.json.bak (kept on upgrade)
  edge_profile\   the app's own Edge profile, holds the sign-in (deleted on Disconnect, never read by our code)
  logs\           rotating log, redacted (ADR-007)
```

## 9. Risks

| Risk | What we do |
|---|---|
| Policy blocks app-launched or headless Edge on the PMO's laptop | Slice 1 tests it first. Fallback: US-13 local import |
| The sign-in does not survive a night and a shutdown | Slice 1 day 2 measures it. If it fails, the user decides before more is built |
| pywebview does not run from the embeddable Python on her laptop | Slice 1 runs in a pywebview window. Fallback in ADR-001 |
| The DevTools port is reachable by other programs of the same Windows user | Random port, 127.0.0.1 only. Those programs could already read her browser data. Accepted in ADR-002 |
| Oversized files | Split above about 300 lines, checked at review |
| Rules duplicated in JS and Python | Status rules only in `core/status.py` |
| Lock-in to Edge | Accepted: the requirements name Edge and her laptop has it |

## 10. First vertical slice: the sign-in test (Assumption 2)

Real code that stays, not a throwaway: `connectors/sharepoint/*`, a minimal `services/sync.py`, a header check in
`core/checklist.py`, `services/diagnostics.py`, a one-page pywebview window, and the package.

The window has: Connect, Sync now, the last result, and "Copy diagnostic report". No tracker screens yet.

On the PMO's laptop:
- **Install:** double-click, no admin rights. The window opens. This proves pywebview runs from the embeddable Python.
- **Day 1:** Connect. Edge opens, she signs in, the window closes by itself. Sync lists the folder and reads one real
  file.
- **Day 2**, after a normal shutdown: she opens the app. It syncs on start. Pass = sync OK and no visible Edge window.
- Both days she clicks "Copy diagnostic report" and sends it to the maintainer.

The report holds:
- App version, Python version, pywebview version and the renderer it used, WebView2 runtime version, Edge version.
- Each step with time and duration: Edge start, sign-in (visible or silent renewal, and how long), list, download.
- Number of files listed, file size, headers found, number of rows. The file is called "file 1 of N", never by name.
- The distinct Deadline texts and the distinct Completion Status values in the file, with counts. Template wording
  only. No names, ids, remarks or task descriptions.

If day 1 fails: stop. US-13 import becomes the main path and the user decides. If day 2 fails: read the report before
building anything else.

## 11. Implementation phases

1. Slice 1: sign-in test and package (above).
2. Reading and rules: full `core/checklist.py` (US-02), `deadlines.py`, `status.py` (US-04), with synthetic fixtures.
3. Store and full sync: ETags, last good data, hidden joiners, partial-sync summary, error messages (US-06, 07, 09, 10).
4. Roll-on dates, waiting list, identity rules (US-03, ADR-005).
5. UI port: sidebar, overview, joiner page, tiles fix (US-05, US-11).
6. Local import (US-13).
7. Renewal tuning from slice 1 data, full diagnostics report (US-08, US-16).
8. Upgrade keeps data (US-15), then hardening.
