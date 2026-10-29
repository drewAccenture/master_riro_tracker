"""US-09 groundwork: a workbook that breaks while its rows are read gives UnreadableFile, not a crash."""

import pytest

from riro.core import checklist


class BrokenSheet:
    def iter_rows(self, values_only=True):
        yield ("Deadline",)
        raise ValueError("broken XML in sheet")


class BrokenWorkbook:
    def __init__(self):
        self.sheetnames = ["Roll-In"]
        self.closed = False

    def __getitem__(self, name):
        return BrokenSheet()

    def close(self):
        self.closed = True


def test_us09_error_while_reading_rows_is_unreadable_file(monkeypatch):
    workbook = BrokenWorkbook()
    monkeypatch.setattr(checklist, "load_workbook", lambda *a, **k: workbook)
    with pytest.raises(checklist.UnreadableFile):
        checklist.check_headers(b"synthetic")
    assert workbook.closed


def test_us09_bytes_that_are_not_xlsx_are_unreadable_file():
    with pytest.raises(checklist.UnreadableFile):
        checklist.check_headers(b"not a workbook")
