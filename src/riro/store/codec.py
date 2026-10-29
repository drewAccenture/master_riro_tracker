"""JSON <-> dataclasses for the data file. Only store/ uses it; the JSON layout never leaves store/."""

from datetime import date, datetime

from riro.core.models import Checklist, FileRecord, Joiner, SkippedRow, SyncRun, Task


def iso(value: date | datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def task_out(task: Task) -> dict:
    return {
        "row_number": task.row_number,
        "number": task.number,
        "role": task.role,
        "description": task.description,
        "deadline": task.deadline,
        "status": task.status,
        "completion_date": iso(task.completion_date),
        "assigned_id": task.assigned_id,
        "remarks": task.remarks,
        "note": task.note,
    }


def task_in(data: dict) -> Task:
    done_on = data["completion_date"]
    return Task(**{**data, "completion_date": done_on and date.fromisoformat(done_on)})


def checklist_out(checklist: Checklist | None) -> dict | None:
    if checklist is None:
        return None
    return {
        "sheet_name": checklist.sheet_name,
        "owner": checklist.owner,
        "tasks": [task_out(task) for task in checklist.tasks],
        "skipped_rows": [
            [row.row_number, row.reason] for row in checklist.skipped_rows
        ],
        "headers_missing": list(checklist.headers_missing),
        "unknown_status_rows": checklist.unknown_status_rows,
    }


def checklist_in(data: dict | None) -> Checklist | None:
    if data is None:
        return None
    return Checklist(
        sheet_name=data["sheet_name"],
        owner=data["owner"],
        tasks=tuple(task_in(task) for task in data["tasks"]),
        skipped_rows=tuple(
            SkippedRow(number, reason) for number, reason in data["skipped_rows"]
        ),
        headers_missing=tuple(data["headers_missing"]),
        unknown_status_rows=data["unknown_status_rows"],
    )


def record_out(record: FileRecord) -> dict:
    return {
        "name": record.name,
        "etag": record.etag,
        "modified": record.modified,
        "present": record.present,
        "checklist": checklist_out(record.checklist),
        "read_at": iso(record.read_at),
        "problem": record.problem,
    }


def record_in(file_id: str, data: dict) -> FileRecord:
    read_at = data["read_at"]
    return FileRecord(
        id=file_id,
        name=data["name"],
        etag=data["etag"],
        modified=data["modified"],
        present=data["present"],
        checklist=checklist_in(data["checklist"]),
        read_at=read_at and datetime.fromisoformat(read_at),
        problem=data["problem"],
    )


def run_out(run: SyncRun) -> dict:
    return {
        "at": run.at.isoformat(),
        "result": run.result,
        "files_read": run.files_read,
        "updated": run.updated,
        "unchanged": run.unchanged,
        "skipped": [list(pair) for pair in run.skipped],
    }


def run_in(data: dict) -> SyncRun:
    return SyncRun(
        **{
            **data,
            "at": datetime.fromisoformat(data["at"]),
            "skipped": tuple(tuple(pair) for pair in data["skipped"]),
        }
    )


def joiner_out(joiner: Joiner) -> dict:
    return {
        "file_id": joiner.file_id,
        "name": joiner.name,
        "owner_key": joiner.owner_key,
        "roll_on": iso(joiner.roll_on),
        "hidden": joiner.hidden,
        "missing_syncs": joiner.missing_syncs,
    }


def joiner_in(joiner_id: str, data: dict) -> Joiner:
    roll_on = data["roll_on"]
    return Joiner(
        id=joiner_id,
        file_id=data["file_id"],
        name=data["name"],
        owner_key=data["owner_key"],
        roll_on=roll_on and date.fromisoformat(roll_on),
        hidden=data["hidden"],
        missing_syncs=data["missing_syncs"],
    )
