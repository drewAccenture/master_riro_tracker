"""Slice 7a review fixes: one failed sign-in is counted once (US-08); run values are checked (ADR-007)."""

from datetime import date, datetime

from riro.connectors.sharepoint.errors import TimedOut
from riro.core.models import SyncRun
from riro.services.diagnostics import Diagnostics
from riro.services.report_sections import sync_run_lines
from riro.services.signin_summary import summary_lines
from riro.services.sync import SyncService

NOW = datetime(2026, 10, 30, 9, 0, 0)
TODAY = date(2026, 10, 30)
CONNECTOR_FAILED = "2026-10-30 09:00:01 sign_in duration_s=120 result=failed"
SERVICE_FAILED = "2026-10-30 09:00:01 sign_in error_kind=TimedOut result=failed"
SERVICE_EDGE_MISSING = (
    "2026-10-30 09:00:01 sign_in error_kind=EdgeMissing result=failed"
)
CONNECTOR_OK = "2026-10-30 09:05:00 sign_in duration_s=30 result=ok"
CLOSE = "2026-10-30 09:00:01 edge_close note=x result=failed"


def visible(lines):
    [line] = summary_lines(lines, TODAY)
    return line.split(", silent")[0]


def test_us08_connector_and_service_lines_of_one_failed_attempt_count_once():
    assert visible([CONNECTOR_FAILED, SERVICE_FAILED]) == (
        "2026-10-30: visible sign-ins 1 (failed 1)"
    )


def test_us08_other_steps_between_the_two_lines_do_not_split_the_attempt():
    assert visible([CONNECTOR_FAILED, CLOSE, SERVICE_FAILED]).endswith(
        "visible sign-ins 1 (failed 1)"
    )


def test_us08_a_failure_before_edge_started_has_only_the_service_line_and_counts():
    assert visible([SERVICE_EDGE_MISSING]).endswith("visible sign-ins 1 (failed 1)")


def test_us08_two_failed_attempts_then_one_that_worked():
    lines = [CONNECTOR_FAILED, SERVICE_FAILED, CONNECTOR_FAILED, SERVICE_FAILED]
    assert visible([*lines, CONNECTOR_OK]).endswith("visible sign-ins 3 (failed 2)")


def test_us08_edge_missing_after_a_failed_attempt_is_a_new_attempt():
    lines = [CONNECTOR_FAILED, SERVICE_FAILED, SERVICE_EDGE_MISSING]
    assert visible(lines).endswith("visible sign-ins 2 (failed 2)")


class FailingSignIn:
    """A connector whose visible sign-in logs its own failure, then raises (as client.sign_in does)."""

    def __init__(self, diagnostics):
        self._diagnostics = diagnostics

    def sign_in(self):
        self._diagnostics.event("sign_in", result="failed", duration_s=120.0)
        raise TimedOut("sign-in did not finish")

    def shutdown(self):
        pass


def test_us08_one_failed_connect_through_the_service_counts_once():
    diagnostics = Diagnostics(None, versions={"app": "test"}, now=lambda: NOW)
    service = SyncService(FailingSignIn(diagnostics), diagnostics)
    service.connect()
    assert "2026-10-30: visible sign-ins 1 (failed 1)" in diagnostics.report()


class Runs:
    def __init__(self, *runs):
        self._runs = runs

    def runs(self):
        return self._runs


def test_adr007_a_run_result_that_is_not_a_known_word_is_not_shown():
    run = SyncRun(NOW, "Synthetic Person A", 1, 2, 3, ())
    assert sync_run_lines(Runs(run)) == [
        "2026-10-30 09:00 unknown: files read 1, updated 2, unchanged 3, skipped 0"
    ]


def test_adr007_run_counts_that_are_not_numbers_show_as_zero():
    run = SyncRun(NOW, "partial", "Synthetic Person A", True, 4, ())
    assert sync_run_lines(Runs(run)) == [
        "2026-10-30 09:00 partial: files read 0, updated 0, unchanged 4, skipped 0"
    ]
