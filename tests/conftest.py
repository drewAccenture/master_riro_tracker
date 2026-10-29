"""Shared test helpers. Synthetic data only: invented names, never real checklist files."""

from io import BytesIO

import pytest
from openpyxl import Workbook

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


def build_xlsx(sheets):
    """Build .xlsx bytes. sheets: list of (sheet_name, rows); each row is a list of cell values."""
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets:
        ws = wb.create_sheet(title=name)
        for row in rows:
            ws.append(list(row))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def synthetic_checklist_rows(owner="Test Person A"):
    """A small synthetic roll-in checklist: header row plus three task rows."""
    header = list(REQUIRED_HEADERS) + list(OPTIONAL_HEADERS)
    return [
        header,
        [owner, "PMO", 1, "Invented task one", "Completed", None, "On Roll On", "", ""],
        [
            owner,
            "PMO",
            2,
            "Invented task two",
            "Not Started",
            None,
            "1 days After Roll On",
            "",
            "",
        ],
        [
            owner,
            "PMO",
            3,
            "Invented task three",
            "Completed",
            None,
            "On Roll On",
            "",
            "",
        ],
    ]


CHECKLIST_HEADER = list(REQUIRED_HEADERS) + list(OPTIONAL_HEADERS)


def task_row(
    number,
    description,
    status="Not Started",
    completion_date=None,
    deadline="On Roll On",
    owner="Test Person A",
    role="PMO",
    assigned_id="",
    remarks="",
):
    """One synthetic data row in CHECKLIST_HEADER order (required headers, then optional)."""
    return [
        owner,
        role,
        number,
        description,
        status,
        completion_date,
        deadline,
        assigned_id,
        remarks,
    ]


@pytest.fixture
def make_xlsx():
    """Factory fixture: make_xlsx([(sheet_name, rows), ...]) -> bytes."""
    return build_xlsx


@pytest.fixture
def make_row():
    """Factory fixture: make_row(number, description, status=..., ...) -> one row (see task_row)."""
    return task_row


@pytest.fixture
def make_checklist():
    """Factory fixture: make_checklist(rows, sheet="Roll-In Checklist", header=CHECKLIST_HEADER) -> bytes.
    rows are data rows only; the header row is added as row 1."""

    def _make(rows, sheet="Roll-In Checklist", header=None):
        head = list(CHECKLIST_HEADER if header is None else header)
        return build_xlsx([(sheet, [head] + [list(r) for r in rows])])

    return _make


@pytest.fixture
def checklist_bytes():
    """One synthetic checklist file with a "Roll-In Checklist" sheet and three task rows."""
    return build_xlsx([("Roll-In Checklist", synthetic_checklist_rows())])
