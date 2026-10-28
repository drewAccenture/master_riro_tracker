# Master RIRO Checklist Tracker: Requirements (version 1)

Status: Approved 2026-10-27
Changed 2026-10-27: US-01 "Connected" wording (slice 1 build, plan section 11).
Changed 2026-10-28: US-01 the Connect button shows "Connected" and cannot be clicked while connected.
Date: 2026-10-26

## 1. Problem statement

A PMO follows the onboarding of employees who are rolling in ("joiners"). Each joiner keeps their own checklist
file (Excel) in a SharePoint folder. Today the PMO uses a single HTML page that reads these files, but it does not
stay up to date by itself, and every joiner often shows the same numbers because rows from the current checklist
template are not recognized. A first Python rebuild tried to sync from SharePoint and never worked reliably.

Version 1 is a Python app, installed on the PMO's laptop, that reads the checklists straight from SharePoint, keeps
itself up to date, says clearly when it could not sync and why, and keeps the look of the original HTML.

Words used here:
- **Joiner**: an employee who is rolling in.
- **Checklist file**: the joiner's `.xlsx` file in the SharePoint folder.
- **Roll-on date** (also "Onboarding date"): the joiner's start date. Every task deadline counts from it.
- **Sync**: the app reads the SharePoint folder and takes over any changed files.
- **Status as of**: the date used to decide if a task is late. Default: today.

## 2. Users and roles

| Role | Who | What they do |
|---|---|---|
| PMO | One PMO, on her own Accenture laptop. Basic computer level. | Installs the app by double-click, signs in to SharePoint, types each joiner's roll-on date once, reads the tracker, exports, drafts emails. |
| Maintainer | The developer (not a user of the app day to day) | Builds the app, packages it, sends new versions to the PMO. |
| Joiners | Employees rolling in | Never use the app. They update their own checklist file in SharePoint. |

There is no login inside the app and no other roles. Only one person uses one copy.

## 3. Source of data

- SharePoint site: `WFR-USTEAM` on `ts.accenture.com` (checked 2026-10-26: this is SharePoint Online on an Accenture
  address, not an on-premises server).
- Folder: `Shared Documents / Repo / 00 ASSETS / AKN / PMOCC RIRO CHECKLIST / ROLL-IN CHECKLIST / In Progress Onboarding`
- One level only. Subfolders are not read.
- Files: `.xlsx`. The sheet used is the first one whose name contains "roll-in" or "rollin", else the first sheet.
- Row 1 holds the headers. Required (any letter case): Checklist Owner, Role, Task Number, Description,
  Completion Status, Completion Date, Deadline. Optional: Assigned Enterprise Id, Remarks (Tracker).
- Access: the PMO's own Accenture sign-in in Microsoft Edge ("PULSE style"). No Azure/Entra app registration,
  no Power Automate, no OneDrive synced folder.

## 4. MVP features (user stories)

### US-01 Connect to SharePoint
As the PMO, I want to connect the tracker to the checklist folder once, so that it can read the files for me.

- Given the app is installed and not connected, When I open it, Then I see "SharePoint: Not connected" and a
  "Connect to SharePoint" button, with the folder already filled in.
- Given I click "Connect to SharePoint", When an Edge window opens and I sign in with my Accenture account (and MFA
  if asked), Then the window closes by itself once the folder is reached and a first sync starts. The box says
  "SharePoint: Connected" once a sync has worked. If that first sync fails, the box says in plain words what went
  wrong (US-07). While connected, the button shows "Connected" and cannot be clicked.
- Given I close the sign-in window or do not finish within 3 minutes, Then the box says, in plain words, that the
  sign-in did not finish, and nothing else changes.
- Given I click "Disconnect", Then the app forgets the sign-in, and my roll-on dates and last data stay.

### US-02 Read the checklists into the tracker
As the PMO, I want every checklist in the folder to appear as a joiner, so that I see everyone's progress.

- Given the folder has N checklist files, When a sync finishes, Then each file with a different Checklist Owner is
  one joiner in the sidebar.
- Given a file, Then the joiner's tasks are exactly the rows in that file (task number, role, description, deadline,
  completion status, completion date, assigned owner). There is no built-in fixed task list.
- Given a file's Checklist Owner is empty, Then the file name is used as the joiner's name.
- Given a completion status that is not one of Not Started, In Progress, Completed, Not Applicable, Then it is read as
  Not Started.
- Given a completion date on a task that is not Completed, Then the date is ignored.
- Given a file that is not a checklist (missing required headers), Then it is skipped and the sync summary names it
  with the reason.
- Given two files with the same Checklist Owner, Then the most recently modified one is used, and a warning names both
  files.

### US-03 Roll-on date typed once
As the PMO, I want to type a new joiner's roll-on date once, so that deadlines can be computed.

- Given a new joiner appears and has no roll-on date, Then they are listed under "Waiting for a roll-on date" and do
  not count in any totals yet.
- Given I type the date and confirm, Then the joiner moves into the normal list and keeps that date after every sync
  and app restart.
- Given I change a joiner's roll-on date later, Then all their deadlines and statuses update right away.
- Given the Checklist Owner text in a file is corrected, Then the joiner keeps their roll-on date.

### US-04 Status of each task and joiner (same rules as the original HTML)
As the PMO, I want each task and joiner to get a status, so that I see who is late.

- Due date of a task = roll-on date + the task's day offset, read from its Deadline text (for example
  "10 days Before Roll On" = minus 10 days, "On Roll On" = 0).
- Given Completion Status is Not Applicable, Then the task is **N/A**.
- Given Completed with a completion date after the due date, Then **Completed Late**. Completed otherwise: **Completed**.
- Given Not Started or In Progress and the due date is before "Status as of", Then **Delayed**, otherwise **On Track**.
- Per joiner: done = Completed + Completed Late; applicable = all tasks minus N/A; percent = done / applicable.
- Given any task of a joiner is Delayed, Then the joiner's banner says "Delayed" and the sidebar pill shows the count
  of delayed tasks. Otherwise "On track".
- Given a Deadline text the app cannot turn into a day offset, Then the task shows "deadline unclear", is not counted
  as Delayed or On Track, and the joiner shows a warning.

### US-05 Status tiles follow the selected joiner (bug fix)
As the PMO, I want the status tiles and counts to match the joiner I click, so that I can trust the numbers.

Bug today: every joiner shows the same tile counts. Most likely cause (from reading the original HTML, not yet
checked against real files): rows are matched against a fixed 96-task list, rows from the current template are
dropped, and all joiners fall back to the same "Not Started" tasks. US-02 removes that cause.

- Given two joiners whose files have different statuses, When I click each one in the sidebar, Then the five tiles
  (Delayed, On Track, Completed, Completed Late, Not applicable) show counts from that joiner's own file.
- Given I click a tile, Then the task table shows only that joiner's tasks with that status. Clicking it again clears
  the filter.
- Given I switch to another joiner, Then the tile filter resets and the tiles show the new joiner's counts.
- Given a file had rows the app could not read, Then the joiner page says how many rows were skipped and why.
  Rows are never dropped without a message.

### US-06 Automatic sync
As the PMO, I want the tracker to pick up joiners' changes without me doing anything.

- Given the app is open and connected, Then it syncs when it starts and then every 5 minutes.
- Given a joiner saved a change in SharePoint, Then the tracker shows it within 5 minutes (plus the sync's own time).
- Given a file did not change since the last sync, Then it is not downloaded again.
- Given a sync is already running, Then no second sync starts.
- Given the app is closed, Then nothing syncs. On the next start it catches up first.

### US-07 Sync now, last sync time, and plain-word errors
As the PMO, I want a "Sync now" button and clear feedback, so that I know whether the data is fresh.

- Given I click "Sync now", Then a sync starts at once (unless one is running, then the button shows "Syncing...").
- The sync box always shows "Last successful sync: <date and time>" (or "Never").
- Given a sync fails, Then the box shows what went wrong in plain words and what to do, for example:
  - "Your SharePoint sign-in has expired. Click Sign in again." (with a button)
  - "You do not have access to the folder. Ask the folder owner for read access."
  - "The folder was not found. It may have been moved or renamed."
  - "SharePoint could not be reached. Check your network or VPN."
  - "SharePoint did not answer in time. The app will try again in 5 minutes."
- Given a sync fails, Then the last good data stays on screen and the last successful sync time does not change.
- Given the sync partly worked (some files could not be read), Then the summary says how many joiners were updated
  and lists each skipped file with its reason.
- A sync never hangs forever: after a time limit it stops and reports a failure.
- Given a sync times out, Then the stuck Edge window or process is closed and the next sync starts clean, not
  waiting on "Connecting".

### US-08 Sign-in lasts as long as possible
As the PMO, I want to sign in as rarely as possible.

- Given the SharePoint sign-in has expired but the longer Microsoft sign-in is still valid, Then the app renews it
  without showing anything.
- Given renewal is not possible, Then the app shows "Sign in again" and stops auto-sync until she signs in.
- Given silent renewal takes longer than a short time limit or fails, Then the app shows "Sign in again" instead of
  waiting. The limit is decided in Phase 2.
- Target: at most about one visible sign-in per working day. To be measured on the PMO's laptop.

### US-09 A file that cannot be read keeps its last good data
- Given a joiner's file cannot be read (open and locked, broken, or wrong format), Then the joiner keeps the last
  good data, marked "File could not be read: <reason>, showing data from <date>".
- Other files in the same sync are still processed.

### US-10 A file that leaves the folder
- Given a joiner's file is moved out of the folder or deleted, Then the joiner is hidden from the lists and totals.
- The app keeps their last data and roll-on date. If the file comes back, the joiner comes back with them.

### US-11 Look and layout of the original HTML
As the PMO, I want the same screens, colors and wording as the original tracker.

- Sidebar (272 px): "Master RIRO Tracker", "Roll-in checklist progress for every new joiner", "All joiners" with the
  delayed total, the "New joiners" list ("Roll-on dd Mon yyyy · N% done" and the delayed pill), the sync box, actions.
- Overview "All joiners": Status as of chip, KPI tiles (Joiners, Delayed tasks, Due within 3 days, Average
  completed), "Open tasks by joiner and deadline" heatmap with Done %, "Needs attention" (8, then "Show all").
- Joiner page: "Back to all joiners", name, Onboarding date and Status as of chips, actions menu, Delayed / On track
  banner with meter, five tiles, deadline ladder, search "Search tasks, owners, deadlines", "All roles", "Clear
  filters", task table (# / Task / Owner / Deadline / Completion status / Completed on / Tracking / Days to due /
  Remarks) with rows that expand to "Full task" and "Guidelines".
- Same colors (light and dark mode), font (Segoe UI), and "ACCENTURE CONFIDENTIAL" footer.
- Given I compare a screen side by side with the original HTML using the same data, Then layout, colors and
  wording match, except for the changes listed in this document (sync box, waiting list, read-only fields).
- The app is read-only for checklist data: completion status, completion date and remarks are shown, not edited.
  The joiner name comes from the file and is not edited either.

### US-13 Import a local checklist file
As the PMO, I want to add a joiner from an `.xlsx` on my PC, for example before their file is in SharePoint.

This is also the fallback if the Edge sign-in is blocked on the PMO's laptop: she downloads the files from
SharePoint herself and imports them.

- Given I pick one or more `.xlsx` checklist files, Then the same reading rules as US-02 apply and each becomes a
  joiner (asking for the roll-on date as in US-03).
- Given the same joiner later appears in SharePoint, Then the SharePoint file wins and the local import is replaced.
- There is no "Add new joiner by hand".

### US-15 Install and run
- Given the PMO gets the package from the maintainer, When she double-clicks to install, Then it installs without
  admin rights and without installing Python herself, and opens the tracker.
- Given a newer package is installed over an older one, Then her roll-on dates and data are kept.
- The app runs only on her laptop and can be reached only from her laptop.

### US-16 Diagnostics
As the maintainer, I want the PMO to copy a diagnostic report with one click, so I can find sync problems on her
laptop.

- Given I click "Copy diagnostic report", Then a text report is copied to the clipboard and a message confirms it.
- The report has timestamps, the steps of recent syncs and sign-ins, and the error reasons.
- The report never contains tokens, cookies, joiner names or enterprise ids.

## 5. Later (version 1.1)

Kept from the original HTML, but not built in version 1.

### US-12 Exports and email drafts
- Per joiner: Export checklist (.xlsx, original 12-column layout, sheet "ROLL-IN CHECKLIST"), Export CSV,
  Export joiner file.
- Email drafts: to the joiner, to the manager, and an all-joiners manager update. Copy text or open in the mail app.
  Contacts come from the file's Assigned Enterprise Id.
- Given I export or draft, Then the content matches what is on screen for that "Status as of" date.

### US-14 Save a backup snapshot
- Given I click "Save tracker file", Then a file is saved with all joiners, their data and their roll-on dates.
- Given I pick a saved snapshot, Then only the roll-on dates in it can be restored. It never replaces data that came
  from SharePoint.

## 6. Out of scope for version 1

- Automatic app updates from SharePoint (wanted later).
- Editing task status, dates, remarks or names in the app. Joiners update their own file.
- Adding a joiner by hand without a file.
- Opening a saved tracker file to replace data (only roll-on dates can be restored).
- Writing anything to SharePoint. The app only reads.
- OneDrive synced folder as a source.
- Azure/Entra app registration, Microsoft Graph, Power Automate.
- Reading subfolders, or other folders such as a "Completed" folder.
- Sync while the app is closed or at Windows start.
- More than one user, shared PCs, phones.
- The first attempt's sync code (not reused).

## 7. Assumptions (please correct)

1. Security: there is no formal ISA approval for using the PMO's own sign-in through Edge. You accept this because
   the PULSE app already works this way. The app never reads, copies or logs cookies or tokens.
2. The PMO's laptop has Microsoft Edge, and Accenture policy lets an app open Edge for her (it worked in the first
   attempt's test on the maintainer's laptop; not yet proven on hers). Before the rest is built, a small test on the
   PMO's own laptop must prove three things: she can sign in, the app reads one real checklist file, and a second
   sync the next day works without a visible sign-in. Phase 2 plans this test as the first slice.
3. Deadline texts follow a small set of patterns ("N days Before Roll On", "On Roll On", "N days After Roll On").
4. The folder holds at most about 50 checklist files, each under 10 MB.
5. A 5-minute auto-sync interval is fine and does not need to be a setting in version 1.
6. "In Progress" counts the same as "Not Started" for status, as in the original HTML.
7. "Status as of" can be changed by the PMO, as in the original, and is not saved between app starts.
8. Data the app keeps on the laptop (joiner names, enterprise ids, task data) is acceptable on the PMO's company
   laptop, in her own user folder.
9. The joiner's display name is the Checklist Owner cell. Joiners are matched in a way that survives an owner-name
   correction (decided in Phase 2).

## 8. Open questions

1. Can you share one or two real checklist files (with names removed) so the reading rules and the bug cause can be
   checked against them? Real files will never go into git.
2. What are all the Deadline texts used in the current template? (Needed for US-04.)

   Checked on 2026-10-26 in `reference/first_attempt/src/riro/core/template.json` (96 tasks) and
   `reference/first_attempt/tests/golden/synthetic/*.xlsx`. This list may be out of date: the checklist template
   changed in October, and the template.json comes from the original HTML, which is older. The synthetic files were
   generated by the first attempt's own tool, not taken from real checklists.

   | Deadline text | Found in | Day offset | US-04 can read it |
   |---|---|---|---|
   | 10 days Before Roll On | template (2), synthetic | -10 | yes |
   | 1 days Before Roll On | template (1), synthetic | -1 | yes |
   | On Roll On | template (5), synthetic | 0 | yes |
   | 1 days After Roll On | template (24), synthetic | 1 | yes |
   | 2 days After Roll On | template (3), synthetic | 2 | yes |
   | 3 days After Roll On | template (13), synthetic | 3 | yes |
   | 5 days After Roll On | template (25), synthetic | 5 | yes |
   | 10 days After Roll On | template (13), synthetic | 10 | yes |
   | 15 days After Roll On | template (4), synthetic | 15 | yes |
   | 30 days After Roll On | template (5), synthetic | 30 | yes |
   | 42 days After Roll On | template (1), synthetic | 42 | yes |
   | Day 0 | synthetic only (1) | | no, "deadline unclear" |
   | (empty) | synthetic only (1) | | no, "deadline unclear" |
   | Never | synthetic only (1) | | no, "deadline unclear" |

   Still open: the Deadline texts in the current (October) template. One real file answers this.
3. Is a visible sign-in about once per working day acceptable to the PMO, or must it be rarer? This is your call to
   check with her after the first real test.
4. Should the app tell the PMO when a joiner's file has not changed for a long time (for example 7 days)?
5. Where does the PMO get the package (Teams, email, SharePoint folder)? Needed for the install steps.
