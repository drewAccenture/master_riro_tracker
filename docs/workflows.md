# Workflows (version 1 MVP stories)

For each story: what the PMO does (user flow) and what moves between layers (data flow).
Layers: UI, bridge, services, core, connector, store. See `docs/architecture.md`.

## US-01 Connect to SharePoint

User flow: opens the app, sees "SharePoint: Not connected", clicks "Connect to SharePoint", signs in in the Edge
window, the window closes and a first sync starts. The box says "Connected" once a sync has worked; if that first
sync fails, it says in plain words what went wrong (US-07).

Data flow:
1. UI -> bridge `connect()` -> `services/sync.connect()`.
2. Connector `sign_in()`: starts visible Edge on the app profile, opens the folder page, waits up to 3 minutes for a
   URL on the site that is not a sign-in page.
3. Success: close the visible Edge politely (at most 5 s, so it saves the sign-in), then kill it by its handle
   (ADR-010). Start headless Edge. Store saves `connected = true`. Sync starts (US-06 flow).
4. Window closed or 3 minutes passed: connector raises `Unreachable` or `TimedOut`. Store unchanged. UI shows "The
   sign-in did not finish".
5. Disconnect: connector kills Edge and deletes `edge_profile\`. Store sets `connected = false`. Roll-on dates and data
   stay.

## US-02 Read the checklists into the tracker

User flow: none. Joiners appear after a sync.

Data flow:
1. Sync service gets bytes for each changed file (US-06 flow).
2. `core/checklist.read(bytes)`: picks the sheet (name contains "roll-in" or "rollin", else first), checks required
   headers, returns rows and skipped rows with reasons. Unknown status -> Not Started. Completion date on a task that
   is not Completed -> ignored.
3. Missing headers: file skipped, reason added to the sync summary.
4. `services/joiners`: one joiner per file; empty Checklist Owner -> file name; two files with the same normalized
   owner -> newest wins, warning names both (ADR-005).
5. Store saves rows per file.

## US-03 Roll-on date typed once

User flow: a new joiner is in "Waiting for a roll-on date". She types the date and confirms. The joiner moves to the
normal list.

Data flow: UI -> bridge `set_roll_on(joiner_id, date)` -> `services/joiners` -> store saves the date on the joiner
(not on the file). `core/status` recomputes at once. Joiners without a date are excluded from totals by
`core/status`. The date survives syncs, restarts, owner-name corrections and re-uploads (ADR-005).

## US-04 Status of each task and joiner

User flow: reads statuses.

Data flow: bridge asks `services/joiners` for a joiner -> `core/status.compute(tasks, roll_on, status_as_of)`.
`core/deadlines` turns the Deadline text into a day offset or "deadline unclear". Result (task statuses, counts,
percent, delayed flag, warnings) goes back to the UI to draw. "Status as of" is held by the UI for the session only
(Assumption 7) and passed in on each call.

## US-05 Status tiles follow the selected joiner

User flow: clicks a joiner, sees their own tiles; clicks a tile to filter, again to clear; switching joiner clears the
filter.

Data flow: same call as US-04, always with the selected joiner's id. Counts come from that joiner's own rows. The tile
filter lives in the UI only. Skipped-row count and reasons come from the store record of that file.

## US-06 Automatic sync

User flow: none.

Data flow: see `docs/architecture.md` section 7. Timer at start and every 5 minutes, one sync at a time, ETag check so
unchanged files are not downloaded. App closed: nothing runs; next start syncs first.

## US-07 Sync now, last sync time, plain-word errors

User flow: clicks "Sync now"; reads "Last successful sync"; on failure reads the message and, when offered, clicks
"Sign in again".

Data flow:
1. UI -> bridge `sync_now()`. Running already: returns "Syncing...".
2. Connector errors map to messages in `services/sync`: `NeedsSignIn` (expired), `NoAccess` (403), `NotFound` (404),
   `Unreachable` (network), `TimedOut` (ADR-003, Edge killed, next sync clean).
3. On failure the store keeps the last good data and the last successful sync time. A sync run record (time, result,
   counts, skipped files and reasons) is saved for the summary and diagnostics.

## US-08 Sign-in lasts as long as possible

User flow: ideally none; at most about one visible sign-in per working day.

Data flow: connector gets 401 or a redirect -> navigates the headless page to the folder page -> back on the site
within 45 s: retry once. Not back: `NeedsSignIn`; services stop the timer and the UI shows "Sign in again". Each
renewal (silent or visible, and its duration) goes to the diagnostics log, so the target can be measured.

## US-09 A file that cannot be read keeps its last good data

Data flow: download or `core/checklist.read` fails for one file -> services keep the stored rows for it, add "File
could not be read: <reason>, showing data from <date>" to the joiner, and continue with the other files.

## US-10 A file that leaves the folder

Data flow: a stored file id missing from the listing -> joiner marked hidden (not deleted), excluded from lists and
totals. Same id back later -> joiner shown again with its data and roll-on date. Deleted and re-uploaded (new id, same
normalized owner, same or next sync) -> same joiner (ADR-005).

## US-11 Look and layout of the original HTML

User flow: the same screens as the original.

Data flow: UI only. HTML and CSS take their look from `reference/html_original/html_original.html` (ideas and styles,
no code reused blindly). All numbers come from Python through the bridge. Checklist fields are read-only.

## US-13 Import a local checklist file

User flow: clicks Import, picks one or more `.xlsx` files, then types roll-on dates for new joiners.

Data flow: pywebview file dialog -> bridge `import_files(paths)` -> services read bytes from disk -> same
`core/checklist.read` and joiner rules as US-02, source "local", keyed by normalized owner. When a SharePoint file
with the same normalized owner appears, the SharePoint file replaces the local import and the roll-on date is kept
(ADR-005).

## US-15 Install and run

User flow: double-clicks `install.bat` from the zip. The app opens. Later versions installed the same way keep her data.

Data flow: `install.bat` copies `app\` into `%LOCALAPPDATA%\RIROTracker\app`, adds Start menu and desktop shortcuts
(`pythonw.exe -m riro`), never touches `data\` or `edge_profile\`. On first start of a new version the store upgrades
`tracker.json` by `schema_version` (ADR-004, ADR-006).

## US-16 Diagnostics

User flow: clicks "Copy diagnostic report", sees "Copied", pastes it into an email or Teams.

Data flow: every service and connector step writes an event (time, step, duration, result, error kind) to
`services/diagnostics`. Redaction happens when the event is written, not only when the report is made (ADR-007).
Bridge `copy_report()` builds text from recent events and puts it on the clipboard.
