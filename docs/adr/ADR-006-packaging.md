# ADR-006: Packaging = embeddable Python + install.bat, per-user, no admin

Status: Accepted
Date: 2026-10-26

## Context
US-15: install by double-click, no admin rights, no Python install by the PMO, data kept on upgrade. The first attempt
used this shape and it installed and passed its self-check on the PMO's laptop (its DECISIONS row 92). Its scripts are
not reused, only the approach.

## Decision
- `tools/build_package.ps1` on the maintainer's PC: downloads `python-3.13.17-embed-amd64.zip` (SHA-256 checked),
  installs the pinned packages into its `Lib\site-packages` (see `docs/constraints.md`), adds `src\riro`, and makes
  `dist\RIROTracker_<version>.zip`.
- `install.bat` copies into `%LOCALAPPDATA%\RIROTracker\app`, adds Start menu and desktop shortcuts
  (`pythonw.exe -m riro`, no console), and starts the app. It never touches `data\`, `edge_profile\` or `logs\`.
- Upgrade: install the new zip the same way. The old `app\` is kept as `app.prev` until the new one starts.
- No Startup shortcut: the app syncs only while open (US-06, out of scope list).

## Alternatives considered
- PyInstaller single exe: an unsigned home-built exe is more often flagged by antivirus and app policies than the
  PSF-signed `python.exe`.
- MSI or MSIX: needs signing or admin rights.

## Consequences
Zip of a few tens of MB. How the PMO receives it (Teams, email, SharePoint) is still open question 5.
