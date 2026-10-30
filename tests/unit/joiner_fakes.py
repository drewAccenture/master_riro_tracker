"""Builders for the slice 4 joiner tests (US-02, US-03, US-10, ADR-005). Synthetic data only, invented names."""

from datetime import date, datetime

from riro.core.models import Checklist, FileRecord, Joiner, SkippedRow, SyncRun, Task

T1 = datetime(2026, 10, 29, 9, 0, 0)
D1 = date(2026, 11, 2)
D2 = date(2026, 11, 9)


def checklist(owner="Test Person A", tasks=(), skipped=()):
    return Checklist(
        sheet_name="Roll-In Checklist",
        owner=owner,
        tasks=tuple(tasks),
        skipped_rows=tuple(skipped),
        headers_missing=(),
        unknown_status_rows=0,
    )


def rec(
    file_id,
    owner="Test Person A",
    name=None,
    modified="2026-10-20T08:00:00Z",
    present=True,
    read=True,
    tasks=(),
    problem=None,
    read_at=T1,
    skipped=(),
):
    """A FileRecord. read=False: never read (no checklist)."""
    return FileRecord(
        id=file_id,
        name=name or f"Synthetic {file_id}.xlsx",
        etag=f"e-{file_id}",
        modified=modified,
        present=present,
        checklist=checklist(owner, tasks, skipped) if read else None,
        read_at=read_at if read else None,
        problem=problem,
    )


def joiner(
    joiner_id,
    file_id=None,
    name="Test Person A",
    owner_key=None,
    roll_on=None,
    hidden=False,
    missing_syncs=0,
):
    return Joiner(
        id=joiner_id,
        file_id=file_id or joiner_id,
        name=name,
        owner_key=owner_key
        if owner_key is not None
        else " ".join(name.lower().split()),
        roll_on=roll_on,
        hidden=hidden,
        missing_syncs=missing_syncs,
    )


def run(at=T1):
    return SyncRun(at, "ok", 1, 1, 0, ())


def task(number, deadline, status, completion_date=None, description=None):
    return Task(
        row_number=int(number) + 1,
        number=str(number),
        role="PMO",
        description=description or f"Invented task {number}",
        deadline=deadline,
        status=status,
        completion_date=completion_date,
    )


# Six tasks, one per track, for roll-on D1 = 2026-11-02 and as of 2026-11-05.
SIX_TASKS = (
    task(1, "On Roll On", "Completed", date(2026, 11, 2)),  # Completed
    task(2, "1 days After Roll On", "Not Started"),  # due 11-03 -> Delayed, days -2
    task(3, "10 days After Roll On", "In Progress"),  # due 11-12 -> On Track, days 7
    task(4, "On Roll On", "Not Applicable"),  # N/A
    task(5, "On Roll On", "Completed", date(2026, 11, 5)),  # Completed Late, days -3
    task(6, "whenever it suits", "Not Started"),  # Deadline unclear, warning
)
SKIPPED = (SkippedRow(9, "no task number or description"),)


def by_id(joiners, joiner_id):
    return next(j for j in joiners if j.id == joiner_id)
