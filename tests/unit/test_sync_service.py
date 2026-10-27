"""US-01, US-07, ADR-003: services/sync.py with a fake connector and fake diagnostics."""

import threading
import time
from datetime import datetime

import pytest

from riro.connectors.sharepoint import errors
from riro.core.models import HeaderReport
from riro.services.sync import (
    SIGN_IN_NOT_FINISHED,
    SyncResult,
    SyncService,
    message_for,
)

T1 = datetime(2026, 10, 27, 9, 0, 0)
T2 = datetime(2026, 10, 27, 9, 5, 0)
JOIN_S = 5.0


def file_item(file_id, name):
    return {
        "id": file_id,
        "name": name,
        "etag": f"e-{file_id}",
        "modified": "2026-10-20",
        "size": 10,
    }


FILES = [
    file_item("1", "notes.txt"),
    file_item("2", "Synthetic B.XLSX"),
    file_item("3", "synthetic c.xlsx"),
]


class FakeConnector:
    def __init__(self, data, files=FILES):
        self.data = data
        self.files = files
        self.calls = []
        self.fail = {}  # method name -> exception to raise

    def _step(self, name):
        self.calls.append(name)
        if name in self.fail:
            raise self.fail[name]

    def sign_in(self):
        self._step("sign_in")

    def health_ping(self):
        self._step("health_ping")

    def list_files(self):
        self._step("list_files")
        return list(self.files)

    def download(self, file_id):
        self._step("download")
        self.calls.append(("download_id", file_id))
        return self.data

    def close(self):
        self.calls.append("close")


class FakeDiagnostics:
    def __init__(self):
        self.events = []
        self.file_reports = []

    def event(self, step, **fields):
        self.events.append((step, fields))

    def file_report(self, index, total, report):
        self.file_reports.append((index, total, report))


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class Now:
    def __init__(self, *values):
        self.values = list(values)

    def __call__(self):
        return self.values.pop(0) if len(self.values) > 1 else self.values[0]


def make_service(checklist_bytes, now=None, **kwargs):
    connector = FakeConnector(checklist_bytes)
    diagnostics = FakeDiagnostics()
    service = SyncService(
        connector, diagnostics, clock=Clock(), now=now or Now(T1, T2), **kwargs
    )
    return service, connector, diagnostics


def test_us07_initial_last_result_is_not_connected(checklist_bytes):
    service, connector, _ = make_service(checklist_bytes)
    result = service.last_result()
    assert result.state == "not_connected"
    assert result.last_success is None
    assert connector.calls == []


def test_us07_sync_ok_reads_first_xlsx_and_sets_last_success(checklist_bytes):
    service, connector, diagnostics = make_service(checklist_bytes)
    result = service.sync()
    assert isinstance(result, SyncResult)
    assert result.state == "ok"
    assert result.files_listed == 3
    assert result.last_success == T1
    assert isinstance(result.report, HeaderReport)
    assert result.report.row_count == 3
    assert result.report.headers_missing == ()
    assert connector.calls == [
        "health_ping",
        "list_files",
        "download",
        ("download_id", "2"),
    ]
    assert service.last_result() == result
    assert len(diagnostics.file_reports) == 1
    assert diagnostics.file_reports[0][0] == 1
    assert diagnostics.file_reports[0][2] == result.report


@pytest.mark.parametrize(
    "kind", ["NoAccess", "NotFound", "Unreachable", "TimedOut", "EdgeMissing"]
)
@pytest.mark.parametrize("step", ["health_ping", "list_files", "download"])
def test_us07_connector_error_gives_failed_with_plain_message(
    checklist_bytes, step, kind
):
    service, connector, _ = make_service(checklist_bytes)
    error = getattr(errors, kind)()
    connector.fail[step] = error
    result = service.sync()
    assert result.state == "failed"
    assert result.message == message_for(error)
    assert result.last_success is None
    assert service.last_result() == result


def test_us07_needs_sign_in_gives_not_connected(checklist_bytes):
    service, connector, _ = make_service(checklist_bytes)
    connector.fail["list_files"] = errors.NeedsSignIn()
    result = service.sync()
    assert result.state == "not_connected"
    assert result.message == "Your SharePoint sign-in has expired. Click Sign in again."


def test_us07_failed_sync_keeps_last_successful_sync_time(checklist_bytes):
    service, connector, _ = make_service(checklist_bytes, now=Now(T1, T2))
    assert service.sync().last_success == T1
    connector.fail["list_files"] = errors.Unreachable()
    failed = service.sync()
    assert failed.state == "failed"
    assert failed.last_success == T1
    assert service.last_result().last_success == T1


def test_us07_second_sync_now_during_a_sync_returns_syncing_at_once(checklist_bytes):
    service, connector, _ = make_service(checklist_bytes)
    entered = threading.Event()
    release = threading.Event()
    original_list = connector.list_files

    def blocking_list():
        entered.set()
        release.wait(timeout=JOIN_S)
        return original_list()

    connector.list_files = blocking_list
    box = {}
    worker = threading.Thread(
        target=lambda: box.setdefault("r", service.sync()), daemon=True
    )
    try:
        worker.start()
        assert entered.wait(timeout=JOIN_S), "first sync never reached list_files"
        start = time.monotonic()
        second = service.sync()
        elapsed = time.monotonic() - start
        assert second.state == "syncing"
        assert second.message == "Syncing..."
        assert elapsed < 0.5
    finally:
        release.set()
        worker.join(timeout=JOIN_S)
    assert not worker.is_alive()
    assert connector.calls.count("health_ping") == 1
    assert connector.calls.count("list_files") == 1
    assert box["r"].state == "ok"


def test_us07_next_sync_after_a_finished_one_runs_normally(checklist_bytes):
    service, connector, _ = make_service(checklist_bytes)
    connector.fail["health_ping"] = errors.TimedOut()
    assert service.sync().state == "failed"
    del connector.fail["health_ping"]
    assert service.sync().state == "ok"


def test_us07_adr003_whole_sync_limit_closes_connector_and_fails(checklist_bytes):
    connector = FakeConnector(checklist_bytes)
    clock = Clock()
    service = SyncService(
        connector, FakeDiagnostics(), clock=clock, now=Now(T1), limit_s=10.0
    )
    original_list = connector.list_files

    def slow_list():
        files = original_list()
        clock.t += 11.0
        return files

    connector.list_files = slow_list
    result = service.sync()
    assert result.state == "failed"
    assert result.message == message_for(errors.TimedOut())
    assert "close" in connector.calls
    assert "download" not in connector.calls
    assert result.last_success is None


def test_us07_within_whole_sync_limit_is_ok(checklist_bytes):
    connector = FakeConnector(checklist_bytes)
    clock = Clock()
    service = SyncService(
        connector, FakeDiagnostics(), clock=clock, now=Now(T1), limit_s=10.0
    )
    original_list = connector.list_files

    def list_using_some_time():
        clock.t += 9.0
        return original_list()

    connector.list_files = list_using_some_time
    assert service.sync().state == "ok"
    assert "close" not in connector.calls


# --- US-01 connect -------------------------------------------------------------------------------------------


def test_us01_connect_signs_in_then_syncs(checklist_bytes):
    service, connector, _ = make_service(checklist_bytes)
    result = service.connect()
    assert connector.calls[0] == "sign_in"
    assert "list_files" in connector.calls
    assert result.state == "ok"
    assert service.last_result() == result


@pytest.mark.parametrize(
    "kind", ["TimedOut", "Unreachable", "NeedsSignIn", "EdgeMissing"]
)
def test_us01_sign_in_not_finished_changes_nothing(checklist_bytes, kind):
    service, connector, _ = make_service(checklist_bytes)
    before = service.last_result()
    connector.fail["sign_in"] = getattr(errors, kind)()
    result = service.connect()
    assert result.state == "sign_in_not_finished"
    assert result.message == SIGN_IN_NOT_FINISHED
    assert service.last_result() == before
    assert connector.calls == ["sign_in"]


def test_us01_sign_in_not_finished_keeps_earlier_good_result(checklist_bytes):
    service, connector, _ = make_service(checklist_bytes)
    good = service.sync()
    connector.calls.clear()
    connector.fail["sign_in"] = errors.TimedOut()
    result = service.connect()
    assert result.state == "sign_in_not_finished"
    assert service.last_result() == good
    assert service.last_result().last_success == T1
    assert "list_files" not in connector.calls
