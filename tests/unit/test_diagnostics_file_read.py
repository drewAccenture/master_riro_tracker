"""US-16, ADR-007, US-07: the file_read step and sync counts in the report. File names never appear."""

from datetime import datetime

import pytest
from store_sync_fakes import Clock, Folder

from riro.connectors.sharepoint import errors
from riro.core.checklist import OPTIONAL_HEADERS, REQUIRED_HEADERS
from riro.services.diagnostics import ERROR_KINDS, STEPS, Diagnostics
from riro.services.sync import SyncService

NOW = datetime(2026, 10, 29, 9, 0, 0)
SECRET = "Zz Secret Joiner"
BROKEN = b"PK\x03\x04 broken synthetic bytes"


def make_diagnostics():
    return Diagnostics(None, versions={"app": "test"}, now=lambda: NOW)


def lines_with(text, *parts):
    return [line for line in text.splitlines() if all(p in line for p in parts)]


def test_adr007_file_read_step_and_new_error_kinds_are_allowed():
    assert "file_read" in STEPS
    assert {"NotAChecklist", "SaveFailed"} <= ERROR_KINDS


def test_adr007_file_read_event_keeps_index_counts_and_kind():
    diag = make_diagnostics()
    diag.event(
        "file_read",
        file_index=2,
        result="ok",
        error_kind=None,
        tasks_count=5,
        skipped_rows_count=1,
        unknown_status_count=0,
    )
    diag.event("file_read", file_index=3, result="failed", error_kind="NotAChecklist")
    diag.event("sync", result="failed", error_kind="SaveFailed")
    text = diag.report()
    assert lines_with(
        text, "file_read", "file_index=2", "tasks_count=5", "skipped_rows_count=1"
    )
    assert lines_with(text, "file_read", "file_index=3", "error_kind=NotAChecklist")
    assert lines_with(text, "sync", "error_kind=SaveFailed")


@pytest.mark.parametrize("value", ["zzq-name.xlsx", True, 2.5])
def test_adr007_file_index_must_be_an_int(value):
    diag = make_diagnostics()
    diag.event("file_read", file_index=value, result="ok")
    text = diag.report()
    assert "file_index" not in text
    assert "zzq" not in text


@pytest.fixture
def mixed_folder(make_checklist, make_row):
    header = [h for h in REQUIRED_HEADERS + OPTIONAL_HEADERS if h != "Deadline"]
    folder = Folder()
    folder.put(
        "id-1", f"{SECRET} One.xlsx", make_checklist([make_row(1, "Invented task one")])
    )
    folder.put("id-2", f"{SECRET} Two.xlsx", BROKEN)
    folder.put(
        "id-3",
        f"{SECRET} Three.xlsx",
        make_checklist([make_row(1, "x")], header=header),
    )
    folder.put("id-4", f"{SECRET} Four.xlsx", b"never downloaded")
    folder.download_fail["id-4"] = errors.NoAccess("synthetic")
    return folder


def run_sync(folder):
    diag = make_diagnostics()
    service = SyncService(folder, diag, clock=Clock(), now=lambda: NOW)
    return service, diag


def test_us16_file_read_events_per_file_without_file_names(mixed_folder):
    service, diag = run_sync(mixed_folder)
    service.sync()
    text = diag.report()
    assert lines_with(text, "file_read", "file_index=1", "result=ok", "tasks_count=1")
    assert lines_with(
        text,
        "file_read",
        "file_index=1",
        "skipped_rows_count=0",
        "unknown_status_count=0",
    )
    assert lines_with(
        text, "file_read", "file_index=2", "result=failed", "error_kind=UnreadableFile"
    )
    assert lines_with(
        text, "file_read", "file_index=3", "result=failed", "error_kind=NotAChecklist"
    )
    assert lines_with(
        text, "file_read", "file_index=4", "result=failed", "error_kind=NoAccess"
    )
    assert SECRET not in text
    assert ".xlsx" not in text


def test_us16_not_found_download_is_reported_by_kind(make_checklist, make_row):
    folder = Folder()
    folder.put("id-1", f"{SECRET}.xlsx", b"x")
    folder.download_fail["id-1"] = errors.NotFound("synthetic")
    service, diag = run_sync(folder)
    service.sync()
    assert lines_with(diag.report(), "file_read", "file_index=1", "error_kind=NotFound")


def test_us07_sync_event_has_updated_unchanged_and_skipped_counts(mixed_folder):
    service, diag = run_sync(mixed_folder)
    service.sync()
    assert lines_with(
        diag.report(), "sync", "updated_count=1", "unchanged_count=0", "skipped_count=3"
    )


def test_us06_unchanged_files_get_no_file_read_event(make_checklist, make_row):
    folder = Folder()
    folder.put(
        "id-1", f"{SECRET}.xlsx", make_checklist([make_row(1, "Invented task one")])
    )
    service, diag = run_sync(folder)
    service.sync()
    service.sync()
    text = diag.report()
    assert len(lines_with(text, "file_read")) == 1
    assert lines_with(
        text, "sync", "updated_count=0", "unchanged_count=1", "skipped_count=0"
    )
