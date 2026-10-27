"""ADR-010, ADR-007: a polite close at app exit that does not finish is recorded, with fixed wording only."""

import subprocess
from datetime import datetime

import pytest
from sharepoint_fakes import FakeClock, FakePage

from riro.connectors.sharepoint.client import (
    FOLDER_URL,
    EdgeSession,
    Limits,
    SharePointClient,
)
from riro.connectors.sharepoint.edge_process import EdgeProcess
from riro.services.diagnostics import POLITE_CLOSE_NOT_FINISHED, Diagnostics

SMALL = Limits(
    edge_start_s=0.1, health_ping_s=0.1, request_s=0.1, renewal_s=1.0, sign_in_s=2.0
)
NOW = datetime(2026, 10, 27, 9, 0, 0)


class ClosingProcess:
    """close() answers whether Edge exited in time, or raises."""

    def __init__(self, outcome):
        self.outcome = outcome
        self.kills = 0

    def close(self, timeout_s):
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome

    def kill(self):
        self.kills += 1


def client_with(process):
    events = []
    clock = FakeClock()

    def start_edge(headless, url):
        return EdgeSession(process=process, page=FakePage())

    client = SharePointClient(
        start_edge,
        limits=SMALL,
        clock=clock,
        sleep=clock.sleep,
        on_event=lambda step, **fields: events.append((step, fields)),
    )
    client.health_ping()  # a headless Edge is running
    return client, events


def closing_events(events):
    return [e for e in events if e[0] == "edge_close"]


@pytest.mark.parametrize(
    "outcome", [False, RuntimeError("Test Person A")], ids=["timed_out", "failed"]
)
def test_adr010_polite_close_at_exit_that_does_not_finish_is_recorded(outcome):
    process = ClosingProcess(outcome)
    client, events = client_with(process)
    client.shutdown()
    assert process.kills >= 1  # killed by its handle anyway
    assert closing_events(events) == [
        ("edge_close", {"result": "failed", "note": POLITE_CLOSE_NOT_FINISHED})
    ]


def test_adr010_polite_close_at_exit_that_finishes_records_nothing():
    process = ClosingProcess(True)
    client, events = client_with(process)
    client.shutdown()
    assert closing_events(events) == []


def test_adr007_note_keeps_only_the_fixed_wording():
    diagnostics = Diagnostics(None, versions={"app": "test"}, now=lambda: NOW)
    diagnostics.event("edge_close", result="failed", note=POLITE_CLOSE_NOT_FINISHED)
    diagnostics.event("edge_close", result="failed", note="Test Person A")
    report = diagnostics.report()
    assert POLITE_CLOSE_NOT_FINISHED == "polite close did not finish"
    assert report.count("edge_close") == 2
    assert report.count(POLITE_CLOSE_NOT_FINISHED) == 1
    assert "Test Person A" not in report


class FakePopen:
    def __init__(self, exits):
        self.exits = exits

    def wait(self, timeout):
        if not self.exits:
            raise subprocess.TimeoutExpired("msedge.exe", timeout)

    def kill(self):
        pass


@pytest.mark.parametrize("exits", [True, False])
def test_adr010_edge_process_wait_says_whether_edge_exited(exits):
    process = EdgeProcess(FakePopen(exits), None, kernel32=None)
    assert process.wait(0.1) is exits


# --- after a finished sign-in (ADR-010 case 1) -------------------------------------------------------------------


def sign_in_with(visible_process):
    events = []
    clock = FakeClock()
    pages = [FakePage(urls=[FOLDER_URL]), FakePage()]
    processes = [visible_process, ClosingProcess(True)]

    def start_edge(headless, url):
        return EdgeSession(process=processes.pop(0), page=pages.pop(0))

    client = SharePointClient(
        start_edge,
        limits=SMALL,
        clock=clock,
        sleep=clock.sleep,
        on_event=lambda step, **fields: events.append((step, fields)),
    )
    client.sign_in()
    return events


@pytest.mark.parametrize(
    "outcome", [False, RuntimeError("Test Person A")], ids=["timed_out", "failed"]
)
def test_adr010_polite_close_after_sign_in_that_does_not_finish_is_recorded(outcome):
    visible = ClosingProcess(outcome)
    events = sign_in_with(visible)
    assert visible.kills >= 1
    assert closing_events(events) == [
        ("edge_close", {"result": "failed", "note": POLITE_CLOSE_NOT_FINISHED})
    ]


def test_adr010_polite_close_after_sign_in_that_finishes_records_nothing():
    events = sign_in_with(ClosingProcess(True))
    assert closing_events(events) == []
