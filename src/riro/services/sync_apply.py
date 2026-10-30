"""The middle of one sync: read the folder, match joiners, one save (US-02, US-06, US-07, US-09, US-10, ADR-005).

Called by SyncService inside its lock and watchdog. Connector errors pass through to it.
"""

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime

from riro.core.checklist import UnreadableFile, check_headers
from riro.core.models import FileRecord, SyncRun
from riro.services.joiners import is_local, match_joiners, owner_key
from riro.services.sync_files import event_fields, sync_folder
from riro.services.sync_messages import SAVE_FAILED, SyncResult, summary
from riro.store.datafile import SaveFailed


def retire_replaced(records: Sequence[FileRecord]) -> tuple[FileRecord, ...]:
    """US-13, ADR-005: a SharePoint file of the same owner replaces a local import (present = False, data kept)."""
    in_sharepoint = {
        owner_key(r)
        for r in records
        if r.present and r.checklist is not None and not is_local(r.id)
    }
    return tuple(
        replace(r, present=False)
        if is_local(r.id)
        and r.present
        and r.checklist is not None
        and owner_key(r) in in_sharepoint
        else r
        for r in records
    )


def read_folder(
    connector, diagnostics, repo, files: list[dict], now: datetime, check, last_success
) -> tuple[SyncResult, dict]:
    """(result, extra diagnostics counts). On SaveFailed the result is "failed" and keeps last_success."""
    first: dict = {}  # header report of the first downloaded file that opens (slice 1 evidence)

    def download(file_id: str) -> bytes:
        data = connector.download(file_id)
        if not first:
            try:
                first.update(id=file_id, report=check_headers(data))
            except UnreadableFile:
                pass
        return data

    stored = {record.id: record for record in repo.files()}
    folder = sync_folder(files, stored, download, now, check=check)
    report = first.get("report")
    for outcome in folder.outcomes:
        if outcome.file_id == first.get("id"):
            diagnostics.file_report(outcome.index, folder.total, report)
        if outcome.kind != "unchanged":
            diagnostics.event("file_read", **event_fields(outcome))

    records = retire_replaced(folder.records)
    match = match_joiners(records, repo.joiners())
    visible = [j for j in match.joiners if not j.hidden]
    updated_files = {o.file_id for o in folder.outcomes if o.kind == "updated"}
    joiners_updated = sum(1 for j in visible if j.file_id in updated_files)
    counts = {
        "files_read": folder.updated + folder.unchanged,
        "updated": folder.updated,
        "unchanged": folder.unchanged,
        "skipped": folder.skipped,
        "joiners": len(visible),
        "joiners_updated": joiners_updated,
        "warnings": match.warnings,
    }
    extra = {
        "joiners_count": len(visible),
        "waiting_count": sum(1 for j in visible if j.roll_on is None),
        "moved_count": match.moved,
        "duplicate_count": match.duplicates,
    }
    run_counts = {
        k: counts[k] for k in ("files_read", "updated", "unchanged", "skipped")
    }
    run = SyncRun(now, "partial" if folder.skipped else "ok", **run_counts)
    try:
        repo.apply(records, now, run, joiners=match.joiners)
    except SaveFailed:
        failed = SyncResult(
            "failed",
            SAVE_FAILED,
            files_listed=len(files),
            last_success=last_success,
            **counts,
        )
        return failed, extra
    message = summary(len(visible), joiners_updated, len(folder.skipped))
    result = SyncResult(
        "ok",
        message,
        files_listed=len(files),
        report=report,
        last_success=now,
        **counts,
    )
    return result, extra
