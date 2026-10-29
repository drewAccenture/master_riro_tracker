"""Read and change what the app keeps: file records, last successful sync, recent sync runs (ADR-004).

The JSON layout stays inside store/. Services only see the dataclasses from core.models.
"""

import copy
from collections.abc import Iterable
from datetime import date, datetime

from riro.core.models import Checklist, FileRecord, SkippedRow, SyncRun, Task
from riro.store.datafile import MemoryDataFile

MAX_RUNS = 20


def _iso(value: date | datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _task_out(task: Task) -> dict:
    return {
        "row_number": task.row_number,
        "number": task.number,
        "role": task.role,
        "description": task.description,
        "deadline": task.deadline,
        "status": task.status,
        "completion_date": _iso(task.completion_date),
        "assigned_id": task.assigned_id,
        "remarks": task.remarks,
        "note": task.note,
    }


def _task_in(data: dict) -> Task:
    done_on = data["completion_date"]
    return Task(**{**data, "completion_date": done_on and date.fromisoformat(done_on)})


def _checklist_out(checklist: Checklist | None) -> dict | None:
    if checklist is None:
        return None
    return {
        "sheet_name": checklist.sheet_name,
        "owner": checklist.owner,
        "tasks": [_task_out(task) for task in checklist.tasks],
        "skipped_rows": [
            [row.row_number, row.reason] for row in checklist.skipped_rows
        ],
        "headers_missing": list(checklist.headers_missing),
        "unknown_status_rows": checklist.unknown_status_rows,
    }


def _checklist_in(data: dict | None) -> Checklist | None:
    if data is None:
        return None
    return Checklist(
        sheet_name=data["sheet_name"],
        owner=data["owner"],
        tasks=tuple(_task_in(task) for task in data["tasks"]),
        skipped_rows=tuple(
            SkippedRow(number, reason) for number, reason in data["skipped_rows"]
        ),
        headers_missing=tuple(data["headers_missing"]),
        unknown_status_rows=data["unknown_status_rows"],
    )


def _record_out(record: FileRecord) -> dict:
    return {
        "name": record.name,
        "etag": record.etag,
        "modified": record.modified,
        "present": record.present,
        "checklist": _checklist_out(record.checklist),
        "read_at": _iso(record.read_at),
        "problem": record.problem,
    }


def _record_in(file_id: str, data: dict) -> FileRecord:
    read_at = data["read_at"]
    return FileRecord(
        id=file_id,
        name=data["name"],
        etag=data["etag"],
        modified=data["modified"],
        present=data["present"],
        checklist=_checklist_in(data["checklist"]),
        read_at=read_at and datetime.fromisoformat(read_at),
        problem=data["problem"],
    )


def _run_out(run: SyncRun) -> dict:
    return {
        "at": run.at.isoformat(),
        "result": run.result,
        "files_read": run.files_read,
        "updated": run.updated,
        "unchanged": run.unchanged,
        "skipped": [list(pair) for pair in run.skipped],
    }


def _run_in(data: dict) -> SyncRun:
    return SyncRun(
        **{
            **data,
            "at": datetime.fromisoformat(data["at"]),
            "skipped": tuple(tuple(pair) for pair in data["skipped"]),
        }
    )


def check_layout(data: dict) -> None:
    """Decode everything once; raises when the layout is wrong. Passed to DataFile(validate=...)."""
    for file_id, record in data.get("files", {}).items():
        _record_in(file_id, record)
    for run in data.get("sync_runs", []):
        _run_in(run)
    if data.get("last_success") is not None:
        datetime.fromisoformat(data["last_success"])


class Repo:
    def __init__(self, datafile):
        self._datafile = datafile
        self._data, self.load_note = datafile.load()

    @classmethod
    def in_memory(cls) -> "Repo":
        return cls(MemoryDataFile())

    def file(self, file_id: str) -> FileRecord | None:
        data = self._data.get("files", {}).get(file_id)
        return None if data is None else _record_in(file_id, data)

    def files(self) -> tuple[FileRecord, ...]:
        stored = self._data.get("files", {})
        return tuple(_record_in(file_id, stored[file_id]) for file_id in sorted(stored))

    def last_success(self) -> datetime | None:
        value = self._data.get("last_success")
        return None if value is None else datetime.fromisoformat(value)

    def runs(self) -> tuple[SyncRun, ...]:
        return tuple(_run_in(run) for run in self._data.get("sync_runs", []))

    def apply(
        self, records: Iterable[FileRecord], last_success: datetime, run: SyncRun
    ) -> None:
        """One save for a whole sync. On SaveFailed nothing changes, on disk or here."""
        data = copy.deepcopy(self._data)
        files = data.setdefault("files", {})
        for record in records:
            files[record.id] = _record_out(record)
        data["last_success"] = last_success.isoformat()
        self._commit(data, run)

    def add_run(self, run: SyncRun) -> None:
        self._commit(copy.deepcopy(self._data), run)

    def _commit(self, data: dict, run: SyncRun) -> None:
        data["sync_runs"] = [*data.get("sync_runs", []), _run_out(run)][-MAX_RUNS:]
        self._datafile.save(data)
        self._data = data
