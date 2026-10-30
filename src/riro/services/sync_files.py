"""One sync's work on the folder: which files to download, read each, keep last good data (US-06, US-09, US-10).

A file that cannot be read keeps its last good data and its old ETag, so the next sync tries it again.
"""

import warnings
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from riro.connectors.sharepoint.errors import NoAccess, NotFound
from riro.core.checklist import UnreadableFile, read
from riro.core.models import Checklist, FileRecord
from riro.services.joiners import is_local

# openpyxl warns about this on every current-template file. Reading is fine, so it is noise in the log.
warnings.filterwarnings(
    "ignore",
    message="Data Validation extension is not supported",
    category=UserWarning,
)

UNREADABLE = "could not be read. It may be open, broken or not an .xlsx file"
NOT_FOUND = "could not be downloaded: the file was not found"
NO_ACCESS = "could not be downloaded: you do not have access to the file"


def not_a_checklist(missing: Sequence[str]) -> str:
    return "not a checklist: missing headers " + ", ".join(missing)


@dataclass(frozen=True)
class FileOutcome:
    index: int  # position among the checklists in the listing, from 1 (diagnostics: "file 2 of 12")
    file_id: str
    name: str
    kind: (
        str  # "updated", "unchanged", "unreadable", "not_checklist", "download_failed"
    )
    reason: str = ""
    checklist: Checklist | None = None


@dataclass(frozen=True)
class FolderResult:
    records: tuple[FileRecord, ...]
    outcomes: tuple[FileOutcome, ...]
    total: int
    updated: int
    unchanged: int
    skipped: tuple[tuple[str, str], ...]  # (file name, reason), listing order


def _fetch(
    item: dict, download: Callable[[str], bytes], check
) -> tuple[str, str, Checklist | None]:
    """(kind, reason, checklist) for one file that has to be downloaded."""
    try:
        data = download(item["id"])
    except NotFound:
        return "download_failed", NOT_FOUND, None
    except NoAccess:
        return "download_failed", NO_ACCESS, None
    check()
    try:
        checklist = read(data)
    except UnreadableFile:
        return "unreadable", UNREADABLE, None
    if checklist.headers_missing:
        return "not_checklist", not_a_checklist(checklist.headers_missing), None
    return "updated", "", checklist


def sync_folder(
    listing: Sequence[dict],
    stored: Mapping[str, FileRecord],
    download: Callable[[str], bytes],
    now: datetime,
    check: Callable[[], None] = lambda: None,
) -> FolderResult:
    checklists = [
        item for item in listing if str(item["name"]).lower().endswith(".xlsx")
    ]
    records, outcomes = [], []
    for index, item in enumerate(checklists, start=1):
        file_id, name = str(item["id"]), str(item["name"])
        old = stored.get(file_id)
        base = old or FileRecord(file_id, name, "", "", True, None, None, None)
        base = replace(
            base, name=name, modified=str(item.get("modified", "")), present=True
        )
        etag = str(item.get("etag", ""))
        # No ETag means "cannot tell", so the file is read again.
        if etag and old is not None and old.etag == etag and old.checklist is not None:
            records.append(replace(base, problem=None))
            outcomes.append(FileOutcome(index, file_id, name, "unchanged"))
            continue
        kind, reason, checklist = _fetch(item, download, check)
        if kind == "updated":
            records.append(
                replace(base, etag=etag, checklist=checklist, read_at=now, problem=None)
            )
        else:
            records.append(replace(base, problem=reason))
        outcomes.append(FileOutcome(index, file_id, name, kind, reason, checklist))
    listed = {record.id for record in records}
    # A local import (US-13) is never in the listing; it stays as it is until a SharePoint file replaces it.
    records += [
        old if is_local(file_id) else replace(old, present=False)
        for file_id, old in stored.items()
        if file_id not in listed
    ]
    return FolderResult(
        records=tuple(records),
        outcomes=tuple(outcomes),
        total=len(checklists),
        updated=sum(1 for o in outcomes if o.kind == "updated"),
        unchanged=sum(1 for o in outcomes if o.kind == "unchanged"),
        skipped=tuple((o.name, o.reason) for o in outcomes if o.reason),
    )


_ERROR_KINDS = {"unreadable": "UnreadableFile", "not_checklist": "NotAChecklist"}


def event_fields(outcome: FileOutcome) -> dict:
    """Diagnostics fields for one file that was downloaded: position, counts, kind. Never its name (ADR-007)."""
    error_kind = _ERROR_KINDS.get(outcome.kind)
    if outcome.kind == "download_failed":
        error_kind = "NotFound" if outcome.reason == NOT_FOUND else "NoAccess"
    fields = {
        "file_index": outcome.index,
        "result": "ok" if outcome.kind == "updated" else "failed",
        "error_kind": error_kind,
    }
    if outcome.checklist is not None:
        fields["tasks_count"] = len(outcome.checklist.tasks)
        fields["skipped_rows_count"] = len(outcome.checklist.skipped_rows)
        fields["unknown_status_count"] = outcome.checklist.unknown_status_rows
    return fields
