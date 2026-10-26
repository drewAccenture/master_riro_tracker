# ADR-005: Joiner identity

Status: Accepted
Date: 2026-10-26

## Context
The roll-on date is typed once and must stay with the right joiner (US-03). The Checklist Owner text can be corrected
(Assumption 9). Two files can have the same owner (US-02). A file can leave and come back (US-10), or be deleted and
uploaded again, which gives it a new SharePoint id. Local imports must be replaced by the SharePoint file later (US-13).

## Decision
- **Normalized owner** = Checklist Owner trimmed, lower case, repeated spaces made single. Empty owner: the file name
  without extension, normalized the same way.
- **A SharePoint joiner is keyed by the file's UniqueId.** An owner-name correction or a rename keeps the same
  UniqueId, so the joiner keeps the roll-on date. The display name is updated from the file.
- **Same owner in two files:** the most recently modified file is used, a warning names both files (US-02).
- **File left the folder:** the joiner is hidden, data and roll-on date kept. Same UniqueId back: joiner shown again
  (US-10).
- **Deleted and re-uploaded:** if a file disappears and a file with a new UniqueId and the same normalized owner
  appears in the same sync or the next one, it is the same joiner. The joiner's key moves to the new UniqueId and the
  roll-on date is kept. The diagnostics log records the move (without names).
- **Local import (US-13):** keyed by normalized owner. When a SharePoint file with the same normalized owner appears,
  the SharePoint file replaces the import and the roll-on date is kept.

## Alternatives considered
- Key on normalized owner only: simple, but an owner-name correction would lose the roll-on date.
- Key on an enterprise id column: the current template's owner cell is a name, and Assigned Enterprise Id is per task,
  not per joiner.

## Consequences
- The window counts syncs, not days. If the app was closed for a week, the first sync after that is still "the next
  sync", so the re-upload is matched. If the new file first appears two or more syncs after the old one disappeared,
  it is a new joiner in "Waiting for a roll-on date" and the PMO types the date again.
- Two different joiners with exactly the same name in one sync are treated as duplicates (newest wins, with a
  warning). Rare, visible, accepted.
