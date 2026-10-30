"""ADR-003, ADR-009, US-07: the whole-sync limit really stops a stuck sync, Edge start failures, unexpected errors,
and the connected state."""

import threading
import time
from datetime import datetime

from riro.connectors.sharepoint import errors
from riro.services.diagnostics import Diagnostics
from riro.services.sync import (
    EDGE_NOT_STARTED,
    UNEXPECTED,
    SyncService,
    message_for,
)

NOW = datetime(2026, 10, 27, 9, 0, 0)
FILES = [{"id": "1", "name": "synthetic.xlsx", "etag": "e", "modified": "", "size": 1}]


class Connector:
    def __init__(self, data=b""):
        self.data = data
        self.calls = []
        self.fail = {}
        self.killed = threading.Event()

    def _step(self, name):
        self.calls.append(name)
        if name in self.fail:
            raise self.fail[name]

    def health_ping(self):
        self._step("health_ping")

    def list_files(self):
        self._step("list_files")
        return list(FILES)

    def download(self, file_id):
        self._step("download")
        return self.data

    def close(self):
        self.calls.append("close")
        self.killed.set()

    def shutdown(self):
        self.calls.append("shutdown")


def make(connector, **kwargs):
    diagnostics = Diagnostics(None, versions={"app": "test"}, now=lambda: NOW)
    return SyncService(connector, diagnostics, now=lambda: NOW, **kwargs), diagnostics


def test_adr003_stuck_call_is_ended_by_the_whole_sync_limit():
    connector = Connector()

    def stuck_list():
        connector.calls.append("list_files")
        connector.killed.wait(timeout=5)  # a call that only ends when Edge is killed
        raise errors.Unreachable("DevTools connection lost")

    connector.list_files = stuck_list
    service, _ = make(connector, limit_s=0.2)
    start = time.monotonic()
    result = service.sync()
    assert time.monotonic() - start < 2.0
    assert "close" in connector.calls
    assert result.state == "failed"
    assert result.message == message_for(errors.TimedOut())


def test_adr009_edge_not_started_has_its_own_message_and_is_not_retried():
    connector = Connector()
    connector.fail["health_ping"] = errors.EdgeNotStarted("Edge could not be started")
    service, _ = make(connector)
    result = service.sync()
    assert result.state == "failed"
    assert result.message == EDGE_NOT_STARTED
    assert message_for(errors.EdgeNotStarted()) == EDGE_NOT_STARTED
    assert connector.calls.count("health_ping") == 1


def test_adr009_edge_not_started_is_a_timed_out_kind():
    assert issubclass(errors.EdgeNotStarted, errors.TimedOut)
    assert errors.EdgeNotStarted.kind == "TimedOut"


def test_us16_unexpected_error_fails_in_plain_words_and_is_in_the_report():
    connector = Connector()
    connector.fail["list_files"] = KeyError("Test Person A")
    service, diagnostics = make(connector)
    result = service.sync()
    assert result.state == "failed"
    assert result.message == UNEXPECTED
    assert service.last_result() == result
    report = diagnostics.report()
    assert "error_kind=Unexpected" in report
    assert "exception=KeyError" in report
    assert "Test Person A" not in report


def test_us01_connected_only_after_a_sync_has_worked(checklist_bytes):
    connector = Connector(checklist_bytes)
    service, _ = make(connector)
    assert service.is_connected() is False
    connector.fail["list_files"] = errors.Unreachable()
    service.sync()
    assert service.is_connected() is False  # never worked yet: not connected
    del connector.fail["list_files"]
    service.sync()
    assert service.is_connected() is True
    connector.fail["list_files"] = errors.Unreachable()
    service.sync()
    assert service.is_connected() is True  # worked before, failed now: still connected
    connector.fail["list_files"] = errors.NeedsSignIn()
    service.sync()
    assert service.is_connected() is False


def test_adr002_shutdown_closes_the_connector_politely():
    connector = Connector()
    service, _ = make(connector)
    service.shutdown()
    assert connector.calls == ["shutdown"]
