# ADR-002: SharePoint access = app-owned Edge through DevTools, kept open while the app runs

Status: Accepted. Refined by ADR-009 and ADR-010.
Date: 2026-10-26

## Context
Access must use the PMO's own Accenture sign-in in Edge. No app registration, no Graph, no cookie extraction
(requirements section 3, Assumption 1). The first attempt (`reference/first_attempt/src/riro/sharepoint/edge.py`) used
Playwright for Python, which runs a Node.js driver, to start a headless Edge, make the REST calls and close Edge on
every sync. It failed like this (its DECISIONS rows 94, 108):
1. Closing headless Edge sometimes never finished. A profile lock stayed held, so every later sync and sign-in waited
   forever ("Connecting..."). The patch waited 60 s, then searched processes by command line with PowerShell to kill
   them, and limited the lock wait to 4 minutes.
2. Two layers (Playwright, Node driver) between our code and Edge, each able to hang.
3. About 288 Edge start and close cycles per day, so a rare hang became a daily one.
4. Renewal of the expired SharePoint sign-in worked once; it was never tested over days on the PMO's laptop.

## Decision
- The app starts `msedge.exe` itself with its own profile and `--remote-debugging-port=0`, keeps the process handle,
  and puts it in a Windows Job Object.
- It talks to Edge with a small DevTools client (`websocket-client`). Requests run as `fetch()` inside a page on the
  SharePoint site, with `redirect: "manual"`. Cookies never leave Edge. GET only.
- Headless Edge stays open while the app is open. It is started about once per app start.
- Every step has a time limit (ADR-003). On a time-out the job is killed: Edge and all its children end at once, no
  graceful close to wait for. The next sync starts a fresh Edge.
- No lock that anyone waits on. One sync worker; a second request during a sync is refused, not queued.
- Sign-in uses the same profile in a visible Edge window.

## Why it will not fail the same way
The hang was in closing Edge through Playwright and then waiting on a lock. Here there is no Playwright or Node,
"close" is killing a process we own by its handle, nothing waits on a lock, and the number of start and close cycles
drops from about 288 per day to about one per app start. What this does not settle: whether policy and Accenture
sign-in rules allow it on the PMO's laptop day after day. Slice 1 tests exactly that.

## Alternatives considered
- Playwright per sync (first attempt): failed as above.
- Use the PMO's existing everyday Edge session (her normal profile): no second sign-in, but the app would attach to
  the browser she is working in. Attaching needs her Edge restarted with a debugging port, a hang could only be ended
  by closing her own browser and tabs, and her profile is locked while she uses it. Rejected: the app must own the
  Edge it can kill.
- Copy cookies from Edge into Python requests: breaks Assumption 1 (a live credential in our process and on disk).
- WebView2 (inside pywebview) for sign-in and reading: one engine less, but untested with Accenture conditional access
  and MFA. Kept as an idea if Edge is blocked.
- Start and close Edge per sync without Playwright: fewer layers, but keeps the many close cycles.
- Local import only (US-13): always available as the fallback, not the main path.

## Consequences
- Edge uses some memory (about 150 to 300 MB) while the app is open.
- The DevTools port is on 127.0.0.1 with a random number. Another program of the same Windows user could connect to
  it. Accepted: such a program can already read her browser data.
- Hard to reverse: the connector interface (`sign_in`, `list_files`, `download`, `renew`) keeps the rest of the app
  independent of this choice.
- Her everyday Edge profile (`%LOCALAPPDATA%\Microsoft\Edge\User Data`) is never opened, read or changed by the app.
  Both that profile and the app's own `edge_profile` are on Claude Code's deny list in `.claude/settings.json`.
