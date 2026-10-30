"""US-01, US-07, ADR-007: any error during Connect gives a plain-word message; the report gets the class name only."""

from datetime import datetime

from riro.services.diagnostics import Diagnostics
from riro.services.sync import UNEXPECTED, SyncService

NOW = datetime(2026, 10, 27, 9, 0, 0)


class BrokenSignIn:
    def __init__(self):
        self.calls = []

    def sign_in(self):
        self.calls.append("sign_in")
        raise KeyError(
            "Test Person A"
        )  # not a ConnectorError, and its text is personal

    def list_files(self):
        self.calls.append("list_files")
        return []


def test_us07_unexpected_error_during_connect_is_plain_words_and_changes_nothing():
    connector = BrokenSignIn()
    diagnostics = Diagnostics(None, versions={"app": "test"}, now=lambda: NOW)
    service = SyncService(connector, diagnostics, now=lambda: NOW)
    before = service.last_result()

    result = service.connect()

    assert result.state == "failed"
    assert result.message == UNEXPECTED
    assert service.last_result() == before  # nothing else changes (US-01)
    assert connector.calls == ["sign_in"]
    assert service.is_running() is False
    report = diagnostics.report()
    assert "sign_in" in report
    assert "error_kind=Unexpected" in report
    assert "exception=KeyError" in report
    assert "Test Person A" not in report
