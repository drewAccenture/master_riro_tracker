"""US-07, ADR-003, ADR-007: sync paths not covered elsewhere (unreadable file, ping retry, versions)."""

from datetime import datetime

from riro.connectors.sharepoint import errors
from riro.services.diagnostics import Diagnostics
from riro.services.sync import UNREADABLE_FILE, SyncService, message_for

NOW = datetime(2026, 10, 27, 9, 0, 0)


class Connector:
    def __init__(self, data=b"not an xlsx", ping_failures=0):
        self.data = data
        self.ping_failures = ping_failures
        self.calls = []

    def health_ping(self):
        self.calls.append("health_ping")
        if self.ping_failures:
            self.ping_failures -= 1
            raise errors.TimedOut()

    def list_files(self):
        self.calls.append("list_files")
        return [
            {
                "id": "1",
                "name": "synthetic.xlsx",
                "etag": "e",
                "modified": "",
                "size": 1,
            }
        ]

    def download(self, file_id):
        self.calls.append("download")
        return self.data

    def close(self):
        self.calls.append("close")


def make(connector):
    diagnostics = Diagnostics(None, versions={"app": "test"}, now=lambda: NOW)
    return SyncService(connector, diagnostics, now=lambda: NOW), diagnostics


def test_us07_unreadable_file_fails_in_plain_words_and_keeps_last_success(
    checklist_bytes,
):
    connector = Connector(checklist_bytes)
    service, diagnostics = make(connector)
    assert service.sync().state == "ok"
    connector.data = b"PK\x03\x04 broken synthetic bytes"

    result = service.sync()

    assert result.state == "failed"
    assert result.message == UNREADABLE_FILE
    assert result.last_success == NOW
    assert "error_kind=UnreadableFile" in diagnostics.report()


def test_adr003_health_ping_timeout_is_retried_once_with_a_fresh_edge(checklist_bytes):
    connector = Connector(checklist_bytes, ping_failures=1)
    service, _ = make(connector)
    assert service.sync().state == "ok"
    assert connector.calls[:3] == ["health_ping", "health_ping", "list_files"]


def test_adr003_health_ping_timeout_twice_fails_without_listing(checklist_bytes):
    connector = Connector(checklist_bytes, ping_failures=2)
    service, _ = make(connector)
    result = service.sync()
    assert result.state == "failed"
    assert result.message == message_for(errors.TimedOut())
    assert "list_files" not in connector.calls


def test_us07_is_running_is_false_after_a_sync(checklist_bytes):
    service, _ = make(Connector(checklist_bytes))
    service.sync()
    assert service.is_running() is False


def test_us16_set_version_appears_in_report():
    diagnostics = Diagnostics(None, versions={"app": "test"}, now=lambda: NOW)
    diagnostics.set_version("edge", "Edg/999.0.1")
    assert "edge: Edg/999.0.1" in diagnostics.report()
