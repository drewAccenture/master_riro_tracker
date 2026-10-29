"""Read a checklist .xlsx. Slice 1: header check only (requirements section 3, architecture section 10)."""

from collections import Counter
from io import BytesIO

from openpyxl import load_workbook

from riro.core.models import HeaderReport

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


def check_headers(data: bytes) -> HeaderReport:
    try:
        workbook = load_workbook(BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises many types for a broken or wrong file
        raise UnreadableFile("not a readable .xlsx file") from exc
    try:
        sheet_name, matched = _choose_sheet(workbook.sheetnames)
        rows = workbook[sheet_name].iter_rows(values_only=True)
        header_row = next(rows, ())
        columns = {}
        for index, value in enumerate(header_row):
            canonical = _CANONICAL.get(_text(value).lower())
            if canonical and canonical not in columns:
                columns[canonical] = index
        row_count = 0
        deadlines, statuses = Counter(), Counter()
        for row in rows:
            if not any(_text(value) for value in row):
                continue
            row_count += 1
            for header, counter in (
                ("Deadline", deadlines),
                ("Completion Status", statuses),
            ):
                index = columns.get(header)
                if index is not None and index < len(row) and _text(row[index]):
                    counter[_text(row[index])] += 1
    # Read-only mode parses rows lazily, so a broken sheet fails while reading, not when opening.
    except Exception as exc:
        raise UnreadableFile("not a readable .xlsx file") from exc
    finally:
        workbook.close()
    return HeaderReport(
        sheet_name=sheet_name,
        sheet_matched=matched,
        headers_found=tuple(
            h for h in REQUIRED_HEADERS + OPTIONAL_HEADERS if h in columns
        ),
        headers_missing=tuple(h for h in REQUIRED_HEADERS if h not in columns),
        row_count=row_count,
        deadline_counts=dict(deadlines),
        status_counts=dict(statuses),
    )
