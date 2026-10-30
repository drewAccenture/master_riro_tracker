"""Import checklist files from the PC (US-13): the same reading rules as a sync (US-02), keyed by owner (ADR-005).

A SharePoint file of the same owner always wins: an import for it is skipped, and a sync retires an older import
(sync_apply.retire_replaced). Called by SyncService.import_files inside the sync lock.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from riro.core.checklist import UnreadableFile, read
from riro.core.models import FileRecord
from riro.services.joiners import (
    LOCAL_PREFIX,
    duplicate_warning,
    is_local,
    local_id,
    match_joiners,
    owner_key,
)
from riro.services.sync_files import UNREADABLE, not_a_checklist
from riro.services.sync_messages import SAVE_FAILED
from riro.store.datafile import SaveFailed

# Re-exported: tests and callers import these from here.
__all__ = [
    "BUSY",
    "IN_SHAREPOINT",
    "LOCAL_PREFIX",
    "MAX_BYTES",
    "NOT_XLSX",
    "TOO_LARGE",
    "ImportResult",
    "import_paths",
    "import_summary",
    "is_local",
    "local_id",
]

MAX_BYTES = 20 * 1024 * 1024
NOT_XLSX = "is not an .xlsx file"
TOO_LARGE = "is too large (over 20 MB)"
IN_SHAREPOINT = "is already in SharePoint. The SharePoint file is used."
BUSY = "A sync is running. Try the import again in a moment."


def _count(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def import_summary(added: int, updated: int, skipped: int) -> str:
    text = f"Import: {_count(added, 'new joiner')}, {updated} updated"
    if skipped:
        text += f", {_count(skipped, 'file')} skipped"
    return text + "."


@dataclass(frozen=True)
class ImportResult:
    state: str  # "ok", "failed" or "busy"
    message: str
    added: int = 0
    updated: int = 0
    skipped: tuple[tuple[str, str], ...] = ()  # (file name, reason), picked order
    warnings: tuple[str, ...] = ()


def _read(path: Path, max_bytes: int) -> tuple[str, object]:
    """("", checklist) or (reason, None) for one picked file."""
    if not path.name.lower().endswith(".xlsx"):
        return NOT_XLSX, None
    try:
        if path.stat().st_size > max_bytes:
            return TOO_LARGE, None
        data = path.read_bytes()
        checklist = read(data)
    except (OSError, UnreadableFile):
        return UNREADABLE, None
    if checklist.headers_missing:
        return not_a_checklist(checklist.headers_missing), None
    return "", checklist


_SKIP_KINDS = {
    NOT_XLSX: "not_xlsx",
    TOO_LARGE: "too_large",
    UNREADABLE: "unreadable",
    IN_SHAREPOINT: "in_sharepoint",
}


def _skip_counts(skipped: Sequence[tuple[str, str]]) -> dict[str, int]:
    """ADR-007: one count per skip reason for the report, never the file name."""
    counts = {f"{kind}_count": 0 for kind in [*_SKIP_KINDS.values(), "not_checklist"]}
    for _, reason in skipped:
        counts[f"{_SKIP_KINDS.get(reason, 'not_checklist')}_count"] += 1
    return {name: n for name, n in counts.items() if n}


def import_paths(
    paths: Sequence[str], repo, diagnostics, now: datetime, max_bytes: int = MAX_BYTES
) -> ImportResult:
    stored = {record.id: record for record in repo.files()}
    in_sharepoint = {
        owner_key(r)
        for r in stored.values()
        if r.present and r.checklist is not None and not is_local(r.id)
    }
    picked: dict[
        str, FileRecord
    ] = {}  # by record id; the last picked file of an owner wins
    skipped: list[tuple[str, str]] = []
    warnings: list[str] = []
    for text in paths:
        path = Path(str(text))
        reason, checklist = _read(path, max_bytes)
        if not reason:
            record = FileRecord(
                "", path.name, "", now.isoformat(), True, checklist, now, None
            )
            key = owner_key(record)
            if key in in_sharepoint:
                reason = IN_SHAREPOINT
        if reason:
            skipped.append((path.name, reason))
            continue
        record_id = local_id(key)
        if record_id in picked:
            warnings.append(duplicate_warning(picked[record_id].name, path.name))
        picked[record_id] = FileRecord(
            record_id, path.name, "", now.isoformat(), True, checklist, now, None
        )
    updated = sum(1 for record_id in picked if record_id in stored)
    added = len(picked) - updated
    error_kind = None
    if picked:
        records = {**stored, **picked}
        before = {j.id: j for j in repo.joiners()}
        match = match_joiners(list(records.values()), list(before.values()))
        # An import is not a sync: a joiner that stays hidden keeps its count for the re-upload window (ADR-005).
        joiners = [
            before[j.id] if j.hidden and j.id in before and before[j.id].hidden else j
            for j in match.joiners
        ]
        try:
            repo.save_import(list(picked.values()), joiners)
        except SaveFailed:
            error_kind = "SaveFailed"
    diagnostics.event(
        "local_import",
        result="failed" if error_kind else "ok",
        files_count=len(paths),
        added_count=0 if error_kind else added,
        updated_count=0 if error_kind else updated,
        skipped_count=len(skipped),
        error_kind=error_kind,
        **_skip_counts(skipped),
    )
    if error_kind:
        return ImportResult("failed", SAVE_FAILED, skipped=tuple(skipped))
    return ImportResult(
        "ok",
        import_summary(added, updated, len(skipped)),
        added=added,
        updated=updated,
        skipped=tuple(skipped),
        warnings=tuple(warnings),
    )
