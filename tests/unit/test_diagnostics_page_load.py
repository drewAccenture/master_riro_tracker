"""Slice 7b, US-16, US-08: page_load is an allowed step, and a sign-in whose Edge start fails is counted once.

The real Diagnostics without a log folder; a real SharePointClient with a fake start_edge; synthetic data only.
"""

from datetime import datetime

from riro.connectors.sharepoint.client import Limits, SharePointClient
from riro.connectors.sharepoint.errors import EdgeNotStarted, TimedOut
from riro.services.diagnostics import STEPS, Diagnostics
from riro.services.sync import SyncService

NOW = datetime(2026, 10, 30, 9, 0, 0)
SMALL = Limits(
    edge_start_s=0.1, health_ping_s=0.1, request_s=0.1, renewal_s=1.0, sign_in_s=2.0
)


def diagnostics():
    return Diagnostics(None, versions={"app": "test"}, now=lambda: NOW)


def recent(report):
    lines = report.splitlines()
    start = lines.index("Recent steps:") + 1
    return lines[start : lines.index("", start)]


# --- page_load step -------------------------------------------------------------------------------------------


def test_us16_page_load_is_an_allowed_step():
    assert "page_load" in STEPS


def test_us16_page_load_ok_keeps_its_step_name_and_duration():
    diag = diagnostics()
    diag.event("page_load", result="ok", duration_s=22.0)
    assert "page_load duration_s=22 result=ok" in diag.report()
    assert "other" not in " ".join(recent(diag.report()))


def test_us16_page_load_failed_timed_out_shows_error_kind():
    diag = diagnostics()
    diag.event("page_load", result="failed", error_kind="TimedOut", duration_s=30.0)
    assert (
        "2026-10-30 09:00:00 page_load duration_s=30 error_kind=TimedOut result=failed"
        in recent(diag.report())
    )


def test_us16_page_load_failed_unreachable_shows_error_kind():
    diag = diagnostics()
    diag.event("page_load", result="failed", error_kind="Unreachable", duration_s=0.25)
    assert (
        "2026-10-30 09:00:00 page_load duration_s=0.25 error_kind=Unreachable result=failed"
        in recent(diag.report())
    )


def test_adr007_page_load_still_drops_a_url_field_of_another_site():
    diag = diagnostics()
    diag.event(
        "page_load",
        result="ok",
        duration_s=1.0,
        url="https://example.invalid/path?who=Test%20Person%20A",
    )
    assert "Test" not in diag.report()


# --- a failed Edge start during Connect ------------------------------------------------------------------------


class FailingStart:
    def __init__(self, error):
        self.error = error

    def __call__(self, headless, url):
        raise self.error


def connect_with(error):
    diag = diagnostics()
    client = SharePointClient(FailingStart(error), limits=SMALL, on_event=diag.event)
    result = SyncService(client, diag).connect()
    return diag, result


def test_us08_failed_edge_start_during_connect_counts_one_failed_sign_in():
    diag, result = connect_with(TimedOut("page did not finish loading"))
    assert result.state == "sign_in_not_finished"
    assert "2026-10-30: visible sign-ins 1 (failed 1)" in diag.report()


def test_us08_failed_edge_start_writes_connector_line_then_service_line():
    diag, _ = connect_with(TimedOut("page did not finish loading"))
    sign_ins = [line for line in recent(diag.report()) if " sign_in " in line]
    assert len(sign_ins) == 2
    connector, service = sign_ins
    assert "duration_s=" in connector
    assert "result=failed" in connector
    assert "duration_s=" not in service
    assert "error_kind=TimedOut" in service
    assert "result=failed" in service


def test_us08_edge_not_started_during_connect_counts_one_failed_sign_in():
    diag, _ = connect_with(EdgeNotStarted("Edge could not be started"))
    report = diag.report()
    assert "2026-10-30: visible sign-ins 1 (failed 1)" in report
    assert any(
        " sign_in duration_s=" in line and "result=failed" in line
        for line in recent(report)
    )
