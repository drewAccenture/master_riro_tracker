"""Helpers for the slice 6 local import tests (US-13, ADR-005). Synthetic data only, invented names.

Files are written to pytest's tmp_path only. Never real checklist files.
"""

from datetime import datetime
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook

from riro.store.datafile import MemoryDataFile, SaveFailed

T_IMPORT = datetime(2026, 10, 30, 10, 15, 0)

HEADER = [
    "Checklist Owner",
    "Role",
    "Task Number",
    "Description",
    "Completion Status",
    "Completion Date",
    "Deadline",
    "Assigned Enterprise Id",
    "Remarks (Tracker)",
]
BROKEN = b"PK\x03\x04 broken synthetic bytes"


def row(number, description, owner="Test Person A", status="Not Started"):
    """One data row in HEADER order."""
    return [owner, "PMO", number, description, status, None, "On Roll On", "", ""]


def default_rows(owner="Test Person A"):
    """Two tasks and one row that is skipped (no task number, no description; US-02 / US-05)."""
    return [
        row(1, "Invented task one", owner=owner),
        row(2, "Invented task two", owner=owner, status="Completed"),
        [owner, "PMO", None, None, "Not Started", None, "On Roll On", "", ""],
    ]


def checklist_bytes(owner="Test Person A", rows=None, header=None):
    wb = Workbook()
    ws = wb.active
    ws.title = "Roll-In Checklist"
    ws.append(list(HEADER if header is None else header))
    for r in default_rows(owner) if rows is None else rows:
        ws.append(list(r))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def write_file(folder: Path, name: str, data: bytes) -> str:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(data)
    return str(path)


def write_checklist(
    folder: Path, name: str, owner="Test Person A", rows=None, header=None
) -> str:
    return write_file(folder, name, checklist_bytes(owner, rows, header))


class SwitchDataFile:
    """MemoryDataFile that counts saves and can be told to refuse them (ADR-004 SaveFailed)."""

    def __init__(self):
        self.inner = MemoryDataFile()
        self.saves = 0
        self.fail = False

    def load(self):
        return self.inner.load()

    def save(self, data):
        if self.fail:
            raise SaveFailed("synthetic: data file held by another program")
        self.saves += 1
        self.inner.save(data)
