"""Read a checklist .xlsx (requirements section 3, US-02): header check and rows -> tasks."""

import re
from collections import Counter
from datetime import date, datetime
from io import BytesIO

from openpyxl import load_workbook

from riro.core.models import Checklist, HeaderReport, SkippedRow, Task

REQUIRED_HEADERS = (
    "Checklist Owner",
    "Role",
    "Task Number",
    "Description",
    "Completion Status",
    "Completion Date",
    "Deadline",
)
OPTIONAL_HEADERS = ("Assigned Enterprise Id", "Remarks (Tracker)")
_CANONICAL = {name.lower(): name for name in REQUIRED_HEADERS + OPTIONAL_HEADERS}
STATUSES = ("Not Started", "In Progress", "Completed", "Not Applicable")
_STATUS_BY_LOWER = {status.lower(): status for status in STATUSES}
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
DATE_UNCLEAR = "completion date unclear"
NO_NUMBER_OR_DESCRIPTION = "no task number or description"


class UnreadableFile(Exception):
    """The bytes are not an .xlsx workbook openpyxl can open."""


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _choose_sheet(names: list[str]) -> tuple[str, bool]:
    for name in names:
        lowered = name.lower()
        if "roll-in" in lowered or "rollin" in lowered:
            return name, True
    return names[0], False


def _load(data: bytes) -> tuple[str, bool, dict[str, int], list[tuple[int, tuple]]]:
    """Open the chosen sheet: (sheet name, matched, header -> column index, non-blank (Excel row, cells))."""
    try:
        workbook = load_workbook(BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises many types for a broken or wrong file
        raise UnreadableFile("not a readable .xlsx file") from exc
    try:
        sheet_name, matched = _choose_sheet(workbook.sheetnames)
        sheet = workbook[sheet_name]
        # Read-only mode stops at the size stored in the file, which some tools write too small (US-05).
        sheet.reset_dimensions()
        rows = sheet.iter_rows(values_only=True)
        columns = {}
        for index, value in enumerate(next(rows, ())):
            canonical = _CANONICAL.get(_text(value).lower())
            if canonical and canonical not in columns:
                columns[canonical] = index
        body = [
            (number, row)
            for number, row in enumerate(rows, start=2)
            if any(_text(value) for value in row)
        ]
    # Read-only mode parses rows lazily, so a broken sheet fails while reading, not when opening.
    except Exception as exc:
        raise UnreadableFile("not a readable .xlsx file") from exc
    finally:
        workbook.close()
    return sheet_name, matched, columns, body


def _cell(row: tuple, columns: dict[str, int], header: str):
    index = columns.get(header)
    return row[index] if index is not None and index < len(row) else None


def check_headers(data: bytes) -> HeaderReport:
    sheet_name, matched, columns, body = _load(data)
    deadlines, statuses = Counter(), Counter()
    for _, row in body:
        for header, counter in (
            ("Deadline", deadlines),
            ("Completion Status", statuses),
        ):
            value = _text(_cell(row, columns, header))
            if value:
                counter[value] += 1
    return HeaderReport(
        sheet_name=sheet_name,
        sheet_matched=matched,
        headers_found=tuple(
            h for h in REQUIRED_HEADERS + OPTIONAL_HEADERS if h in columns
        ),
        headers_missing=tuple(h for h in REQUIRED_HEADERS if h not in columns),
        row_count=len(body),
        deadline_counts=dict(deadlines),
        status_counts=dict(statuses),
    )


def _task_number(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return _text(value)


def _completion_date(value) -> tuple[date | None, str]:
    """(date, note) for a Completed task's Completion Date cell."""
    if isinstance(value, datetime):
        return value.date(), ""
    if isinstance(value, date):
        return value, ""
    text = _text(value)
    if not text:
        return None, ""
    if _ISO_DATE.fullmatch(text):
        try:
            return date.fromisoformat(text), ""
        except ValueError:
            pass
    return None, DATE_UNCLEAR


def read(data: bytes) -> Checklist:
    """All tasks of one checklist file. Missing required headers: no tasks, headers_missing filled."""
    sheet_name, _, columns, body = _load(data)
    missing = tuple(h for h in REQUIRED_HEADERS if h not in columns)
    if missing:
        return Checklist(sheet_name, "", (), (), missing, 0)
    owner = ""
    tasks, skipped = [], []
    unknown = 0
    for row_number, row in body:
        cell = {header: _cell(row, columns, header) for header in columns}
        owner = owner or _text(cell.get("Checklist Owner"))
        number = _task_number(cell.get("Task Number"))
        description = _text(cell.get("Description"))
        if not number and not description:
            skipped.append(SkippedRow(row_number, NO_NUMBER_OR_DESCRIPTION))
            continue
        status = _STATUS_BY_LOWER.get(_text(cell.get("Completion Status")).lower())
        if status is None:
            status = "Not Started"
            unknown += 1
        completion_date, note = None, ""
        if status == "Completed":
            completion_date, note = _completion_date(cell.get("Completion Date"))
        tasks.append(
            Task(
                row_number=row_number,
                number=number,
                role=_text(cell.get("Role")),
                description=description,
                deadline=_text(cell.get("Deadline")),
                status=status,
                completion_date=completion_date,
                assigned_id=_text(cell.get("Assigned Enterprise Id")),
                remarks=_text(cell.get("Remarks (Tracker)")),
                note=note,
            )
        )
    return Checklist(sheet_name, owner, tuple(tasks), tuple(skipped), (), unknown)
